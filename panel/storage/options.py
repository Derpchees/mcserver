#
# MCServer by Derpchees - almacenamiento: destinos posibles
#
# Para servidores o respaldos se puede elegir:
#   newpart    particion nueva en espacio libre (o en un disco vacio)
#   partition  particion existente sin montar (se monta, no se formatea)
#   lvm        volumen nuevo en un grupo LVM con espacio libre
#   folder     carpeta en un disco ya montado; con tamano, archivo reservado
#   rebuild    rehacer un disco con poco contenido (solo respaldos, rebuild.py)
#

import os

from . import disks, system
from .rebuild import rebuildable_disks
from .status import role_status


def mounted_filesystems():
    found = []

    for target, (source, fstype) in sorted(system.mounts().items()):
        if fstype not in system.FILESYSTEMS or not source.startswith("/dev/"):
            continue

        if target.startswith(("/boot", "/snap", "/var/lib/docker", "/run")):
            continue

        if os.path.basename(source).startswith("loop"):
            continue

        u = system.usage(target)

        if u:
            found.append({"mount": target, "source": source, "fstype": fstype,
                          "disk": disks.physical_disk(source), **u})

    return found


def unmounted_partitions():
    found = []
    mounted = {os.path.realpath(s) for s, _ in system.mounts().values()}

    for node in disks.flat_devices():
        if node.get("type") not in ("part", "lvm") or node.get("fstype") not in system.FILESYSTEMS:
            continue

        if node.get("mountpoint") or os.path.realpath(node.get("path") or "") in mounted:
            continue

        found.append({"device": node["path"], "fstype": node["fstype"], "size": node.get("size"),
                      "label": node.get("label") or "", "disk": disks.physical_disk(node["path"])})

    return found


def free_space():
    # Discos vacios y huecos sin particionar
    found = []

    for node in disks.flat_devices():
        if node.get("type") != "disk" or node["name"].startswith(("loop", "zram", "sr", "ram")):
            continue

        if node.get("fstype"):
            continue

        disk = disks.disk_info(node)

        if not node.get("children") and not node.get("pttype"):
            if (node.get("size") or 0) >= system.MIN_GB * system.GB:
                found.append({"disk": disk, "start": None, "size": node["size"], "empty": True})
            continue

        for start, end, size in system.free_segments(node["path"]):
            if size >= system.MIN_GB * system.GB:
                found.append({"disk": disk, "start": start, "size": size, "empty": False})

    return found


def storage_options(role):
    current = role_status(role)
    other = role_status("backups" if role == "data" else "data")
    system_disk = disks.system_disk()

    def about(disk):
        name = disk["name"] if disk else ""
        return {"disk": disks.label(disk), "disk_name": name,
                "same_as_other": bool(name and name == other["disk_name"]),
                "system_disk": bool(name and name == system_disk)}

    options = []

    for hole in free_space():
        options.append({"kind": "newpart", "target": hole["disk"]["path"], "start": hole["start"],
                        "free": hole["size"], "empty_disk": hole["empty"], "disk_size": hole["disk"]["size"],
                        **about(hole["disk"])})

    if role == "backups":
        for item in rebuildable_disks():
            options.append({"kind": "rebuild", "target": item["disk"]["path"], "free": item["size"],
                            "content": item["content"], "mounts": item["mounts"], **about(item["disk"])})

    for part in unmounted_partitions():
        options.append({"kind": "partition", "target": part["device"], "free": part["size"],
                        "label": part["label"], "fstype": part["fstype"], **about(part["disk"])})

    for group in system.volume_groups():
        if group["free"] >= system.MIN_GB * system.GB:
            disk = disks.physical_disk(group["pvs"][0]) if group["pvs"] else None
            options.append({"kind": "lvm", "target": group["name"], "free": group["free"], **about(disk)})

    for fs in mounted_filesystems():
        options.append({"kind": "folder", "target": fs["mount"], "free": fs["free"], "total": fs["total"],
                        "current": bool(current["available"] and current.get("mount") == fs["mount"]),
                        **about(fs["disk"])})

    return {"role": role, "current": current, "options": options}
