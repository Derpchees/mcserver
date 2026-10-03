#
# MCServer by Derpchees - almacenamiento: lectura del sistema
#
# Funciones pequenas que consultan discos, montajes y LVM. Los demas
# modulos las llaman como system.x() para poder simularlas en pruebas.
#

import json
import os
import shutil
import subprocess

FILESYSTEMS = ("ext4", "ext3", "xfs", "btrfs")
MIN_GB = 5
GB = 1024 ** 3
MIB = 1024 ** 2

# Donde se montan los espacios nuevos
MOUNT_BASE = "/mnt"


class StorageError(Exception):
    pass


def run(*args, check=True):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True)

    if check and result.returncode != 0:
        raise StorageError((result.stderr or result.stdout).strip() or "Falló: " + " ".join(map(str, args)))

    return result.stdout


def lsblk():
    out = run("lsblk", "-J", "-b", "-o",
              "NAME,PATH,TYPE,SIZE,FSTYPE,MOUNTPOINT,LABEL,UUID,MODEL,PKNAME,RM,PTTYPE", check=False)

    try:
        return json.loads(out).get("blockdevices", [])
    except ValueError:
        return []


def mounts():
    # Sistemas de archivos montados: {punto: (origen, tipo)}
    found = {}

    try:
        with open("/proc/self/mounts", "r") as f:
            for line in f:
                source, target, fstype = line.split()[:3]
                found[target.replace("\\040", " ")] = (source, fstype)
    except OSError:
        pass

    return found


def volume_groups():
    out = run("vgs", "--reportformat", "json", "--units", "b", "--nosuffix",
              "-o", "vg_name,vg_size,vg_free,pv_name", check=False)

    groups = {}

    try:
        for row in json.loads(out)["report"][0]["vg"]:
            group = groups.setdefault(row["vg_name"], {
                "name": row["vg_name"], "size": int(row["vg_size"]), "free": int(row["vg_free"]), "pvs": []
            })
            group["pvs"].append(row.get("pv_name", ""))
    except (ValueError, KeyError, IndexError):
        pass

    return list(groups.values())


def logical_volume(device):
    # Datos LVM de un dispositivo (None si no es un volumen logico)
    out = run("lvs", "--reportformat", "json", "--units", "b", "--nosuffix",
              "-o", "lv_name,vg_name,lv_size,lv_path", device, check=False)

    try:
        rows = json.loads(out)["report"][0]["lv"]
        return rows[0] if rows else None
    except (ValueError, KeyError, IndexError):
        return None


def loop_backing_file(device):
    name = os.path.basename(os.path.realpath(device))

    try:
        with open("/sys/block/%s/loop/backing_file" % name, "r") as f:
            return f.read().strip()
    except OSError:
        return ""


def free_segments(disk):
    # Huecos sin particionar de un disco: [(inicio, fin, tamano)] en bytes
    out = run("parted", "-m", "-s", disk, "unit", "B", "print", "free", check=False)
    segments = []

    for line in out.splitlines()[2:]:
        parts = line.rstrip(";").split(":")

        if len(parts) >= 5 and parts[4] == "free":
            start, end, size = (int(p.rstrip("B")) for p in parts[1:4])
            segments.append((start, end, size))

    return segments


def usage(path):
    try:
        u = shutil.disk_usage(path)
        return {"total": u.total, "used": u.total - u.free, "free": u.free}
    except OSError:
        return None


def is_mount(path):
    return os.path.ismount(path)


def udev_settle():
    run("udevadm", "settle", check=False)
