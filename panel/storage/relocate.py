#
# MCServer by Derpchees - almacenamiento: mover datos y agrandar
#
# Mover los servidores apaga todos, copia cada carpeta, cambia la ruta
# en config.env, recrea los contenedores y solo al final borra lo viejo.
#

import os
import re
import shutil
import subprocess
import time

import mcpanel_core as core

from . import spaces, system
from .jobs import start_job, step
from .options import storage_options
from .status import ROLES, role_status
from .system import GB, MIN_GB, StorageError


def copy_tree(source, dest, label):
    # rsync conserva permisos y dueno; su avance se muestra en el panel
    os.makedirs(dest, exist_ok=True)

    if not shutil.which("rsync"):
        system.run("cp", "-a", source.rstrip("/") + "/.", dest)
        return

    process = subprocess.Popen(
        ["rsync", "-aHAX", "--info=progress2", "--no-inc-recursive",
         source.rstrip("/") + "/", dest.rstrip("/") + "/"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    for line in iter(process.stdout.readline, ""):
        m = re.search(r"(\d+)%", line)

        if m:
            step("copy", int(m.group(1)), **label)

    process.wait()

    if process.returncode != 0:
        raise StorageError("La copia falló: " + process.stderr.read().strip()[:300])


def stop_all_servers():
    for srv in core.list_servers():
        if core.container_state(srv)[0] != "running":
            continue

        step("stop", server=srv.name)

        try:
            os.makedirs(os.path.dirname(srv.run_file), exist_ok=True)

            with open(srv.run_file + ".hint", "w") as f:
                f.write("manual %d" % int(time.time()))
        except OSError:
            pass

        core.runtime().stop(srv)


def default_path_servers(role):
    # Los servidores importados tienen su ruta fija y no se mueven
    column = "data_dir" if role == "data" else "backup_dir"
    fixed = {row["id"] for row in core.query("SELECT id, %s FROM servers" % column) if row[column]}
    return [srv for srv in core.list_servers() if srv.id not in fixed]


def move_role(role, new_root, existing):
    old_root = ROLES[role]["root"]()

    if os.path.realpath(new_root) == os.path.realpath(old_root):
        raise StorageError("Esa ya es la ubicación actual")

    # Si el disco viejo no esta, no hay nada que copiar
    if not (core.path_available(old_root) and os.path.isdir(old_root)):
        existing = "leave"

    os.makedirs(new_root, exist_ok=True)

    try:
        os.chown(new_root, core.MC_UID, core.MC_GID)
    except OSError:
        pass

    servers = default_path_servers(role)
    copied = []

    if role == "data":
        core.set_setting("storage_busy", "1")
        stop_all_servers()

    if existing in ("move", "copy"):
        for n, srv in enumerate(servers):
            source = os.path.join(old_root, srv.slug)

            if not os.path.isdir(source):
                continue

            label = {"server": srv.name, "n": n + 1, "total": len(servers)}
            step("copy", 0, **label)
            copy_tree(source, os.path.join(new_root, srv.slug), label)
            copied.append(source)

    step("save")
    core.set_config({ROLES[role]["key"]: new_root})

    if role == "data":
        # El contenedor guarda la ruta de su carpeta: se recrea
        for srv in core.list_servers():
            if srv.state in ("ready", "error"):
                step("container", server=srv.name)
                core.build_container(srv)
                core.update_server(srv.id, state="ready", state_detail="")
    else:
        core.set_setting("backups_paused", "")

    if existing == "move":
        for source in copied:
            step("delete_old", server=os.path.basename(source))
            shutil.rmtree(source, ignore_errors=True)

        try:
            os.rmdir(old_root)
        except OSError:
            pass

    step("done", 100)


def relocate(role, kind, target, size_gb=0, existing="move", start=None, extra_name=""):
    if role not in ROLES:
        raise StorageError("Ubicación no válida")

    if existing not in ("move", "copy", "leave"):
        raise StorageError("Opción no válida")

    # Los servidores se mueven siempre con sus mundos
    if role == "data":
        existing = "move"

    size_gb = int(size_gb or 0)
    reserved = kind == "folder" and size_gb > 0
    wanted = "folder" if kind == "image" else kind
    option = next((o for o in storage_options(role)["options"]
                   if o["kind"] == wanted and o["target"] == target
                   and (kind != "newpart" or o["start"] == start)), None)

    if not option:
        raise StorageError("Ese destino ya no está disponible")

    if kind in ("lvm", "newpart") or reserved or kind == "image":
        limit = option["free"] - (GB if kind in ("folder", "image") else 0)

        if size_gb < MIN_GB or size_gb * GB > limit:
            raise StorageError("El tamaño debe estar entre %d y %d GB" % (MIN_GB, max(MIN_GB, limit // GB)))

    folder = ROLES[role]["folder"]
    name = ROLES[role]["name"]

    def work():
        if kind == "newpart":
            new_root = os.path.join(spaces.create_partitions(target, start, size_gb, name, extra_name), folder)
        elif kind == "lvm":
            new_root = os.path.join(spaces.create_lvm(target, size_gb, name), folder)
        elif kind == "image" or reserved:
            new_root = os.path.join(spaces.create_image(target, size_gb, name), folder)
        elif kind == "partition":
            new_root = os.path.join(spaces.mount_partition(target), "minecraft", folder)
        else:
            new_root = os.path.join("/srv" if target == "/" else target, "minecraft", folder)

        move_role(role, new_root, existing)

    start_job("relocate:" + role, work)
    return {"ok": True, "message": "Tarea iniciada"}


def grow(role, size_gb):
    status = role_status(role)
    size_gb = int(size_gb or 0)

    if not status["available"]:
        raise StorageError("El disco no está conectado")

    if status["kind"] not in ("lvm", "image"):
        raise StorageError("Solo se puede agrandar un volumen LVM o un archivo reservado")

    current_gb = status["total"] // GB
    max_gb = (status["total"] + status["can_grow"]) // GB

    if not current_gb < size_gb <= max_gb:
        raise StorageError("El nuevo tamaño debe estar entre %d y %d GB" % (current_gb + 1, max_gb))

    def work():
        step("grow", gb=size_gb)

        if status["kind"] == "lvm":
            system.run("lvextend", "-r", "-L", "%dG" % size_gb, status["device"])
        else:
            system.run("fallocate", "-l", "%dG" % size_gb, status["file"])
            system.run("losetup", "-c", status["device"])
            system.run("resize2fs", status["device"])

        step("done", 100)

    start_job("grow:" + role, work)
    return {"ok": True, "message": "Tarea iniciada"}


def set_backups_paused(paused):
    core.set_setting("backups_paused", "yes" if paused else "")
    return {"ok": True, "message": "Respaldos desactivados" if paused else "Respaldos activados"}
