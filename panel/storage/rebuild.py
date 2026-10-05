#
# MCServer by Derpchees - almacenamiento: rehacer un disco
#
# Para discos que ya tienen particiones pero poco contenido (por ejemplo un
# disco de 1 TB con una sola particion casi vacia). Rehace el disco con una
# particion del tamano elegido para MCServer y, si se pide, otra con el resto
# (por ejemplo para camaras), sin perder lo que habia:
#
#   1. copia el contenido de cada particion montada al disco del sistema y
#      verifica la copia por checksum
#   2. desmonta, quita sus lineas de /etc/fstab (antes lo respalda) y crea
#      la tabla de particiones nueva
#   3. los respaldos de cada servidor van a la particion de MCServer; lo
#      demas, a la otra particion (o a una carpeta "otros")
#
# Solo se ofrece para respaldos, en discos que no son el del sistema ni
# tienen los mundos, cuyo contenido es conocido y cabe en el disco del sistema.
#

import os
import shutil
import subprocess
import time

import mcpanel_core as core

from . import disks, spaces, system
from .jobs import start_job, step
from .status import ROLES
from .system import GB, MIN_GB, StorageError

MARGIN = 2 * GB
IGNORED = {"lost+found"}


def disk_contents(node):
    # [(particion, punto de montaje, bytes usados)] o None si no se puede rehacer
    table = system.mounts()
    contents = []

    for part in node.get("children", []):
        if part.get("children"):
            return None

        fstype = part.get("fstype")
        mount = next((t for t, (s, _) in table.items() if os.path.realpath(s) == os.path.realpath(part["path"])), None)

        if not fstype:
            # Particion sin formato (ej. la reservada de Windows): no hay nada que conservar
            if (part.get("size") or 0) > GB:
                return None
            continue

        if fstype not in system.FILESYSTEMS or not mount:
            return None

        if mount == "/" or mount.startswith("/boot"):
            return None

        u = system.usage(mount)
        contents.append((part["path"], mount, u["used"] if u else 0))

    return contents


def rebuildable_disks():
    found = []
    system_disk = disks.system_disk()
    data_disk = disks.physical_disk_of_path(core.data_root())
    space = system.usage(core.STATE_ROOT if os.path.isdir(core.STATE_ROOT) else "/")

    for node in disks.flat_devices():
        if node.get("type") != "disk" or node["name"].startswith(("loop", "zram", "sr", "ram")):
            continue

        if node["name"] == system_disk or (data_disk and node["name"] == data_disk["name"]):
            continue

        if not node.get("children") or node.get("fstype"):
            continue

        contents = disk_contents(node)

        if contents is None:
            continue

        used = sum(c[2] for c in contents)

        if not space or used + MARGIN > space["free"]:
            continue

        found.append({"disk": disks.disk_info(node), "size": node.get("size") or 0,
                      "content": used, "mounts": [c[1] for c in contents]})

    return found


def copy_verified(source, dest):
    # Copia y comprueba por checksum que no falte ni cambie nada
    os.makedirs(dest, exist_ok=True)
    args = ["rsync", "-aHAX", "--exclude=/lost+found", source.rstrip("/") + "/", dest.rstrip("/") + "/"]
    system.run(*args)
    check = system.run(*(["rsync", "-aHAXcn", "--itemize-changes"] + args[2:]))

    if check.strip():
        raise StorageError("La copia de %s no coincide con el original" % source)


def remove_fstab_mounts(mounts):
    with open("/etc/fstab", "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    keep = [l for l in lines if not (len(l.split()) >= 2 and not l.lstrip().startswith("#")
                                    and os.path.normpath(l.split()[1]) in mounts)]

    if len(keep) != len(lines):
        shutil.copy2("/etc/fstab", "/etc/fstab.bak-mcserver-" + time.strftime("%Y%m%d-%H%M%S"))

        with open("/etc/fstab", "w", encoding="utf-8") as f:
            f.write("\n".join(keep) + "\n")

        system.run("systemctl", "daemon-reload", check=False)


def under(path, root):
    path, root = os.path.normpath(path), os.path.normpath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def rebuild(disk_path, size_gb, extra_name=""):
    option = next((d for d in rebuildable_disks() if d["disk"]["path"] == disk_path), None)

    if not option:
        raise StorageError("Ese disco ya no se puede rehacer")

    size_gb = int(size_gb or 0)
    max_gb = option["size"] // GB - (MIN_GB if extra_name else 1)

    if not MIN_GB <= size_gb <= max_gb:
        raise StorageError("El tamaño debe estar entre %d y %d GB" % (MIN_GB, max_gb))

    def work():
        temp = os.path.join(core.STATE_ROOT, "rebuild-%d" % int(time.time()))
        mounts = option["mounts"]
        copies = {}
        agent_stopped = False

        core.set_setting("storage_busy", "1")

        try:
            # Sin respaldos ni arranques mientras el disco no existe
            subprocess.run(["systemctl", "stop", "mcpanel-agent"], capture_output=True)
            agent_stopped = True

            for n, mount in enumerate(mounts):
                step("rebuild_copy", None, mount=mount, n=n + 1, total=len(mounts))
                copies[mount] = os.path.join(temp, str(n))
                copy_verified(mount, copies[mount])

            step("rebuild_unmount")
            for mount in mounts:
                system.run("umount", mount)

            remove_fstab_mounts({os.path.normpath(m) for m in mounts})

            step("rebuild_table", None, disk=disk_path)
            for part in [c["path"] for n in disks.flat_devices() if n.get("path") == disk_path
                         for c in n.get("children", [])]:
                system.run("wipefs", "-aq", part, check=False)

            # Disco vacio (sin tabla): create_partitions crea la tabla GPT y las particiones
            system.run("wipefs", "-aq", disk_path)
            system.run("partprobe", disk_path, check=False)
            system.udev_settle()

            name = ROLES["backups"]["name"]
            new_mount = spaces.create_partitions(disk_path, None, size_gb, name,
                                                 spaces.clean_name(extra_name, "datos") if extra_name else "")
            extra_mount = None

            if extra_name:
                extra_mount = next((t for t, (s, _) in system.mounts().items()
                                    if os.path.basename(t).startswith(spaces.clean_name(extra_name, "datos"))
                                    and t != new_mount), None)

            new_root = os.path.join(new_mount, ROLES["backups"]["folder"])
            os.makedirs(new_root, exist_ok=True)

            # Respaldos: la carpeta general y las fijas de cada servidor
            old_root = core.backup_root()
            moved = set()

            for srv in core.list_servers():
                source = srv.backup_dir
                mount = next((m for m in mounts if under(source, m)), None)

                if not mount:
                    continue

                inside = os.path.relpath(source, mount)
                temp_path = os.path.join(copies[mount], inside)

                if os.path.isdir(temp_path):
                    step("rebuild_restore", None, server=srv.name)
                    copy_verified(temp_path, os.path.join(new_root, srv.slug))
                    moved.add(temp_path)

                core.execute("UPDATE servers SET backup_dir = '' WHERE id = ?", (srv.id,))

            general = next((m for m in mounts if under(old_root, m)), None)

            if general:
                temp_root = os.path.join(copies[general], os.path.relpath(old_root, general))

                if os.path.isdir(temp_root):
                    for entry in os.listdir(temp_root):
                        path = os.path.join(temp_root, entry)
                        if path not in moved and os.path.isdir(path):
                            copy_verified(path, os.path.join(new_root, entry))
                            moved.add(path)
                    moved.add(temp_root)

            # Lo demas que hubiera en el disco no se pierde
            others = extra_mount or os.path.join(new_mount, "otros")

            for mount, copy in copies.items():
                for root, dirs, files in os.walk(copy, topdown=True):
                    dirs[:] = [d for d in dirs if os.path.join(root, d) not in moved and d not in IGNORED]

                    for file in files:
                        source = os.path.join(root, file)
                        target = os.path.join(others, os.path.basename(mount.rstrip("/")),
                                              os.path.relpath(source, copy))
                        step("rebuild_others", None, mount=others)
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        shutil.copy2(source, target)

            subprocess.run(["chown", "-R", "%d:%d" % (core.MC_UID, core.MC_GID), new_root], capture_output=True)

            if extra_mount:
                os.chown(extra_mount, core.MC_UID, core.MC_GID)

            step("save")
            core.set_config({"BACKUP_ROOT": new_root, "BACKUP_MOUNT": new_mount})
            core.set_setting("backups_paused", "")

            for srv in core.list_servers():
                srv.write_env()

            for mount in mounts:
                try:
                    os.rmdir(mount)
                except OSError:
                    pass

            shutil.rmtree(temp, ignore_errors=True)
            step("done", 100)
        except Exception as error:
            # La copia se conserva: nada de lo que habia en el disco se pierde
            if copies:
                raise StorageError("%s (la copia del contenido del disco esta en %s)" % (error, temp))
            raise
        finally:
            core.set_setting("storage_busy", "")

            if agent_stopped:
                subprocess.run(["systemctl", "start", "mcpanel-agent"], capture_output=True)

    start_job("rebuild:backups", work)
    return {"ok": True, "message": "Tarea iniciada"}
