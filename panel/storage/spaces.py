#
# MCServer by Derpchees - almacenamiento: crear y montar espacios
#
# Todo se monta por UUID en /etc/fstab con "nofail" (se respalda fstab
# antes de tocarlo), para que el equipo arranque aunque falte el disco.
#

import os
import re
import shutil
import time

from . import disks, system
from .jobs import step
from .system import StorageError


def free_mount_point(name):
    base = os.path.join(system.MOUNT_BASE, name)
    path, n = base, 2

    while os.path.exists(path) and (system.is_mount(path) or os.listdir(path)):
        path = "%s-%d" % (base, n)
        n += 1

    return path


def add_fstab(line):
    shutil.copy2("/etc/fstab", "/etc/fstab.bak-mcserver-" + time.strftime("%Y%m%d-%H%M%S"))

    with open("/etc/fstab", "a", encoding="utf-8") as f:
        f.write(line + "\n")

    system.run("systemctl", "daemon-reload", check=False)


def mount_new(source, fstype, mount, extra_options=""):
    os.makedirs(mount, exist_ok=True)

    if source.startswith("/dev/"):
        what = "UUID=" + system.run("blkid", "-s", "UUID", "-o", "value", source).strip()
    else:
        what = source

    options = "defaults,nofail,x-systemd.device-timeout=10s" + extra_options
    add_fstab("%s %s %s %s 0 2" % (what, mount, fstype, options))
    system.run("mount", mount)

    if not system.is_mount(mount):
        raise StorageError("No se pudo montar " + mount)


def clean_name(text, default):
    return re.sub(r"[^A-Za-z0-9_-]", "", text or "")[:16] or default


# ------------------------------------------------------------
# Particion nueva en espacio libre
# ------------------------------------------------------------

def partitions_of(disk_path):
    for node in disks.flat_devices():
        if node.get("path") == disk_path:
            return {c["path"] for c in node.get("children", []) if c.get("type") == "part"}, node.get("pttype")

    raise StorageError("No se encontró el disco " + disk_path)


def prepare_empty_disk(disk_path):
    parts, pttype = partitions_of(disk_path)

    if parts or pttype:
        raise StorageError("El disco ya no está vacío")

    node = next(n for n in disks.flat_devices() if n.get("path") == disk_path)

    if node.get("fstype"):
        raise StorageError("El disco tiene datos")

    step("gpt", disk=disk_path)
    system.run("parted", "-s", disk_path, "mklabel", "gpt")
    system.udev_settle()


def new_partition(disk_path, start, end, name):
    # Crea una particion de "start" a "end" (bytes), le da formato y la monta
    before, pttype = partitions_of(disk_path)
    first = -(-max(start, system.MIB) // system.MIB)
    last = end // system.MIB

    if last - first < system.MIN_GB * 1024:
        raise StorageError("No hay espacio suficiente para la partición " + name)

    step("partition", name=name, gb=(last - first) // 1024, disk=disk_path)
    # En discos MBR el campo es el tipo de particion, no el nombre
    label = name if pttype == "gpt" else "primary"
    system.run("parted", "-s", "-a", "optimal", disk_path, "mkpart", label, "ext4",
               "%dMiB" % first, "%dMiB" % last)
    system.run("partprobe", disk_path, check=False)
    system.udev_settle()

    created = sorted(partitions_of(disk_path)[0] - before)

    if len(created) != 1:
        raise StorageError("No se encontró la partición nueva en " + disk_path)

    device = created[0]
    step("format", device=device)
    system.run("mkfs.ext4", "-q", "-L", name, device)

    mount = free_mount_point(name)
    step("mount", mount=mount)
    mount_new(device, "ext4", mount)
    return mount, last * system.MIB


def create_partitions(disk_path, start, size_gb, name, extra_name=""):
    # Particion para MCServer y, si se pide, otra con el resto del hueco
    hole = None

    if start is None:
        prepare_empty_disk(disk_path)

    for seg_start, seg_end, seg_size in system.free_segments(disk_path):
        if start is None or seg_start <= start <= seg_end:
            if hole is None or seg_size > hole[2]:
                hole = (seg_start, seg_end, seg_size)

    if not hole:
        raise StorageError("El espacio libre ya no está disponible")

    begin = max(hole[0], system.MIB)
    end = min(hole[1], begin + size_gb * system.GB)

    if size_gb * system.GB > hole[1] - begin:
        raise StorageError("No caben %d GB en ese espacio libre" % size_gb)

    mount, used_end = new_partition(disk_path, begin, end, name)

    if extra_name:
        extra_mount, _ = new_partition(disk_path, used_end, hole[1], clean_name(extra_name, "datos"))
        step("extra_ready", mount=extra_mount)

    return mount


# ------------------------------------------------------------
# Particion existente, volumen LVM y archivo reservado
# ------------------------------------------------------------

def mount_partition(device):
    node = next((n for n in disks.flat_devices() if n.get("path") == device), None)

    if not node or node.get("fstype") not in system.FILESYSTEMS or node.get("mountpoint"):
        raise StorageError("La partición no está disponible")

    mount = free_mount_point(clean_name(node.get("label"), os.path.basename(device)))
    step("mount_existing", device=device, mount=mount)
    mount_new(device, node["fstype"], mount)
    return mount


def create_lvm(group, size_gb, name):
    existing = set(system.run("lvs", "--noheadings", "-o", "lv_name", group, check=False).split())
    lv, n = name, 2

    while lv in existing:
        lv = "%s-%d" % (name, n)
        n += 1

    step("lvm", lv=lv, gb=size_gb, vg=group)
    system.run("lvcreate", "-y", "-n", lv, "-L", "%dG" % size_gb, group)
    device = "/dev/%s/%s" % (group, lv)

    step("format", device=device)
    system.run("mkfs.ext4", "-q", "-L", lv[:16], device)

    mount = free_mount_point(lv)
    step("mount", mount=mount)
    mount_new(device, "ext4", mount)
    return mount


def create_image(host, size_gb, name):
    folder = host if host != "/" else "/srv"
    image = os.path.join(folder, name + ".img")
    n = 2

    while os.path.exists(image):
        image = os.path.join(folder, "%s-%d.img" % (name, n))
        n += 1

    step("image", gb=size_gb, file=image)
    system.run("fallocate", "-l", "%dG" % size_gb, image)

    try:
        os.chmod(image, 0o600)
        step("format", device=image)
        system.run("mkfs.ext4", "-q", "-F", "-L", name[:16], image)

        mount = free_mount_point(name)
        step("mount", mount=mount)
        # El archivo vive en otro disco: se monta despues de el
        mount_new(image, "ext4", mount, ",loop,x-systemd.requires-mounts-for=" + folder)
    except Exception:
        try:
            os.remove(image)
        except OSError:
            pass
        raise

    return mount
