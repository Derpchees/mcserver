#
# MCServer by Derpchees - almacenamiento: estado de las ubicaciones
#

import os

import mcpanel_core as core

from . import disks, jobs, system

ROLES = {
    "data": {"key": "DATA_ROOT", "root": core.data_root, "folder": "servers", "name": "mcserver-servers"},
    "backups": {"key": "BACKUP_ROOT", "root": core.backup_root, "folder": "backups", "name": "mcserver-backups"},
}


def space_info(mount, source):
    # Que tipo de espacio es el sistema de archivos montado en "mount"
    if mount == "/":
        return {"kind": "system"}

    if os.path.basename(source).startswith("loop"):
        return {"kind": "image", "file": system.loop_backing_file(source), "device": source}

    lv = system.logical_volume(source) if source.startswith("/dev/") else None

    if lv:
        return {"kind": "lvm", "vg": lv["vg_name"], "lv": lv["lv_name"], "device": lv.get("lv_path") or source}

    return {"kind": "partition", "device": source}


def role_status(role):
    path = ROLES[role]["root"]()
    available = core.path_available(path)

    info = {
        "role": role,
        "path": path,
        "mount": core.expected_mount(path),
        "available": available,
        "kind": None,
        "disk": "",
        "disk_name": "",
        "total": None,
        "used": None,
        "free": None,
        "can_grow": 0
    }

    if not available:
        return info

    mount, source, _ = disks.mount_of(path)
    space = space_info(mount, source)
    disk = disks.physical_disk(source) if source.startswith("/dev/") else disks.physical_disk_of_path(path)

    info.update(space)
    info.update(system.usage(mount) or {})
    info["mount"] = mount
    info["disk"] = disks.label(disk)
    info["disk_name"] = disk["name"] if disk else ""
    info["removable"] = bool(disk and disk["removable"])

    # Cuanto se puede agrandar el espacio reservado
    if space["kind"] == "lvm":
        group = next((g for g in system.volume_groups() if g["name"] == space["vg"]), None)
        info["can_grow"] = group["free"] if group else 0
    elif space["kind"] == "image" and space.get("file"):
        host = system.usage(os.path.dirname(space["file"]))
        info["can_grow"] = max(0, host["free"] - system.GB) if host else 0

    return info


def backups_state(status=None):
    # ok, missing (pausados solos) o paused (el administrador los desactivo
    # hasta que vuelva el disco)
    status = status or role_status("backups")

    if status["available"]:
        return "ok"

    return "paused" if core.get_setting("backups_paused") else "missing"


def storage_status():
    data = role_status("data")
    backups = role_status("backups")
    same = bool(data["disk_name"] and data["disk_name"] == backups["disk_name"])
    data["same_disk"] = backups["same_disk"] = same

    return {
        "data": data,
        "backups": backups,
        "backups_state": backups_state(backups),
        "busy": bool(core.get_setting("storage_busy")),
        "job": jobs.job_status()
    }
