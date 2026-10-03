#
# MCServer by Derpchees - almacenamiento: discos fisicos
#
# A que disco fisico pertenece una ruta o un dispositivo, siguiendo
# particiones, volumenes LVM y archivos de disco.
#

import os

from . import system


def flat_devices():
    out = []

    def walk(nodes, parent):
        for node in nodes:
            node["_parent"] = parent
            out.append(node)
            walk(node.get("children", []), node)

    walk(system.lsblk(), None)
    return out


def disk_info(node):
    return {"name": node["name"], "path": node.get("path"), "model": (node.get("model") or "").strip(),
            "size": node.get("size"), "removable": bool(node.get("rm"))}


def physical_disk(device):
    # Disco fisico (tipo "disk") donde vive un dispositivo
    real = os.path.realpath(device)

    if os.path.basename(real).startswith("loop"):
        backing = system.loop_backing_file(real)
        return physical_disk_of_path(os.path.dirname(backing)) if backing else None

    for node in flat_devices():
        path = node.get("path") or ""

        if path != device and os.path.realpath(path) != real:
            continue

        current = node

        while current and current.get("type") != "disk":
            current = current["_parent"]

        if current:
            return disk_info(current)

    return None


def mount_of(path):
    # Punto de montaje, origen y tipo del sistema de archivos que contiene una ruta
    table = system.mounts()
    path = os.path.realpath(path)

    while path not in table and os.path.dirname(path) != path:
        path = os.path.dirname(path)

    source, fstype = table.get(path, ("", ""))
    return path, source, fstype


def physical_disk_of_path(path):
    while not os.path.exists(path) and os.path.dirname(path) != path:
        path = os.path.dirname(path)

    _, source, _ = mount_of(path)
    return physical_disk(source) if source.startswith("/dev/") else None


def system_disk():
    disk = physical_disk_of_path("/")
    return disk["name"] if disk else ""


def label(disk):
    if not disk:
        return ""

    return disk["model"] or disk["name"]
