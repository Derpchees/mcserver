#
# MCServer by Derpchees - Mundos: ver, regenerar, borrar, cambiar y subir
#
# Java: cada mundo es una carpeta con level.dat junto al servidor (Paper
# guarda el Nether y el End aparte: <mundo>_nether y <mundo>_the_end).
# Bedrock: carpetas dentro de worlds/. El activo es level-name.
#
# Regenerar no borra al momento: el mundo actual se renombra a
# "<nombre>.old-<fecha>" y queda en la lista para volver a el o borrarlo.
# Todo se hace con el servidor apagado (se apaga si hace falta).
#

import json
import os
import re
import shutil
import tempfile
import time
import zipfile

import mcpanel_core as core
import runtime

from .common import FileError, log_server_action, S, set_stop_hint, use_server
from .containers import request_rebuild
from .properties import ensure_properties, read_properties

FOLDER = re.compile(r"^[A-Za-z0-9 _.()-]{1,64}$")
PAPER_DIMS = ("_nether", "_the_end")
MAX_UPLOAD = 4 * 1024 ** 3


def bedrock():
    return core.is_bedrock(S())


def root():
    return os.path.join(S().data_dir, "worlds") if bedrock() else S().data_dir


def active_name():
    return read_properties().get("level-name") or ("Bedrock level" if bedrock() else "world")


def folders_of(name):
    # Carpetas que forman un mundo (el principal y las dimensiones de Paper)
    base = os.path.join(root(), name)

    if bedrock():
        return [base]

    return [path for path in [base] + [base + suffix for suffix in PAPER_DIMS] if os.path.isdir(path)]


def dir_size(path):
    total = 0

    for folder, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(folder, name))
            except OSError:
                pass

    return total


def is_world(path):
    return os.path.isfile(os.path.join(path, "level.dat"))


def display_name(folder):
    # Bedrock guarda el nombre del mundo en levelname.txt
    try:
        with open(os.path.join(root(), folder, "levelname.txt"), "r", encoding="utf-8", errors="replace") as f:
            text = f.read().strip()

        if text:
            return text[:80]
    except OSError:
        pass

    return folder


def list_worlds():
    active = active_name()
    worlds = []

    if os.path.isdir(root()):
        for entry in sorted(os.scandir(root()), key=lambda e: e.name.lower()):
            if not entry.is_dir() or not is_world(entry.path):
                continue

            # Las dimensiones de Paper van con su mundo
            if not bedrock() and entry.name.endswith(PAPER_DIMS) and \
                    os.path.isdir(os.path.join(root(), re.sub(r"(_nether|_the_end)$", "", entry.name))):
                continue

            worlds.append({
                "id": entry.name,
                "name": display_name(entry.name),
                "active": entry.name == active,
                "size": sum(dir_size(path) for path in folders_of(entry.name)),
                "mtime": int(entry.stat().st_mtime),
                "copy": ".old-" in entry.name
            })

    return worlds


def worlds_state():
    from .experiments import experiments_state

    worlds = list_worlds()

    return {
        "edition": "bedrock" if bedrock() else "java",
        "active": active_name(),
        "exists": any(w["active"] for w in worlds),
        "worlds": worlds,
        "seed": read_properties().get("level-seed", ""),
        "running": runtime.running(S()),
        "experiments": experiments_state()
    }


def check_folder(value):
    value = str(value or "")

    if not FOLDER.match(value) or value in (".", "..") or not os.path.isdir(os.path.join(root(), value)):
        raise FileError("Mundo no válido")

    return value


def stop_if_running(user, why):
    if runtime.running(S()):
        set_stop_hint(S(), "manual")
        runtime.stop(S())
        log_server_action(S(), "%s apagó el servidor para %s" % (user["username"], why))


def set_level(values):
    # Cambia claves de server.properties sin tocar las demas
    from native import props

    props.update(ensure_properties(), values)


def stamp():
    return time.strftime("%Y%m%d-%H%M")


def regenerate(data, user):
    # El mundo actual queda como copia (o se borra si asi se pide); el nuevo
    # se crea al encender, con la semilla elegida (vacia = al azar)
    seed = re.sub(r"[\x00-\x1f\x7f]", "", str(data.get("seed", ""))).strip()[:64]
    keep = data.get("keep", True) is not False
    stop_if_running(user, "regenerar el mundo")
    name = active_name()
    copy = "%s.old-%s" % (name, stamp())

    for path in folders_of(name):
        if not os.path.exists(path):
            continue

        if keep:
            suffix = os.path.basename(path)[len(name):]
            os.replace(path, os.path.join(root(), copy + suffix))
        else:
            shutil.rmtree(path)

    set_level({"level-seed": seed})
    log_server_action(S(), "%s regeneró el mundo%s" % (user["username"], " (copia: %s)" % copy if keep else ""))
    return {"ok": True, "message": "Mundo regenerado", "copy": copy if keep else ""}


def delete_world(data, user):
    folder = check_folder(data.get("id"))

    if folder == active_name():
        raise FileError("No se puede borrar el mundo activo: regenéralo o usa otro primero")

    for path in folders_of(folder):
        shutil.rmtree(path, ignore_errors=True)

    log_server_action(S(), "%s borró el mundo %s" % (user["username"], folder))
    return {"ok": True, "message": "Mundo borrado"}


def activate_world(data, user):
    folder = check_folder(data.get("id"))
    running = runtime.running(S())
    set_level({"level-name": folder})

    # La imagen de Java pone level-name con LEVEL (por defecto "world"):
    # en Docker el nombre va tambien en esa variable
    if not bedrock() and not core.NATIVE:
        extra = dict(S().extra_env)

        if folder == "world":
            extra.pop("LEVEL", None)
        else:
            extra["LEVEL"] = folder

        if extra != S().extra_env:
            core.update_server(S().id, extra_env=json.dumps(extra) if extra else "")
            fresh = core.get_server(S().id)
            use_server(fresh)
            request_rebuild(fresh)

    log_server_action(S(), "%s cambió el mundo a %s" % (user["username"], folder))
    return {"ok": True, "message": "Mundo elegido", "restart": running}


def reset_dimension(data, user):
    # Java: el Nether (DIM-1) o el End (DIM1) se generan de nuevo al entrar
    dim = str(data.get("dim", ""))

    if bedrock() or dim not in ("nether", "end"):
        raise FileError("Acción no válida")

    stop_if_running(user, "reiniciar una dimensión")
    name = active_name()
    inner = "DIM-1" if dim == "nether" else "DIM1"
    paper = os.path.join(root(), name + ("_nether" if dim == "nether" else "_the_end"))

    for path in (os.path.join(root(), name, inner), os.path.join(paper, inner)):
        shutil.rmtree(path, ignore_errors=True)

    log_server_action(S(), "%s reinició %s" % (user["username"], "el Nether" if dim == "nether" else "el End"))
    return {"ok": True, "message": "Dimensión reiniciada"}


# ============================================================
# Subir un mundo (.zip de Java, .mcworld de Bedrock)
# ============================================================

def unique_folder(name):
    base = re.sub(r"[^A-Za-z0-9 _.()-]", "_", name).strip(" .")[:48] or "mundo"
    candidate = base
    n = 2

    while os.path.exists(os.path.join(root(), candidate)):
        candidate = "%s (%d)" % (base, n)
        n += 1

    return candidate


def import_archive(archive, name, user):
    # Busca level.dat en el zip (en la raiz o en una carpeta) y lo agrega
    # como un mundo mas; no lo activa
    work = tempfile.mkdtemp(prefix="mcpanel-world-")

    try:
        try:
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    target = os.path.normpath(os.path.join(work, info.filename))

                    if not target.startswith(work + os.sep) and target != work:
                        raise FileError("El archivo trae rutas no válidas")

                zf.extractall(work)
        except zipfile.BadZipFile:
            raise FileError("El archivo no es un mundo (.zip o .mcworld)")

        found = None

        for folder, _, files in os.walk(work):
            if "level.dat" in files and (found is None or len(folder) < len(found)):
                found = folder

        if not found:
            raise FileError("El archivo no tiene un mundo (falta level.dat)")

        if bedrock() and not os.path.isdir(os.path.join(found, "db")):
            raise FileError("Ese mundo no es de Bedrock")

        if not bedrock() and os.path.isdir(os.path.join(found, "db")):
            raise FileError("Ese mundo es de Bedrock")

        os.makedirs(root(), exist_ok=True)
        label = name if found == work else os.path.basename(found)
        folder = unique_folder(os.path.splitext(label)[0])
        shutil.move(found, os.path.join(root(), folder))

        for path, _, files in os.walk(os.path.join(root(), folder)):
            for item in files + [""]:
                try:
                    os.chown(os.path.join(path, item), core.MC_UID, core.MC_GID)
                except OSError:
                    pass

        log_server_action(S(), "%s subió el mundo %s" % (user["username"], folder))
        return {"ok": True, "message": "Mundo agregado", "id": folder}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def upload_world(handler, name, length, user):
    name = os.path.basename(str(name or "mundo.zip"))

    if not name.lower().endswith((".zip", ".mcworld")):
        raise FileError("Sube un mundo .zip o .mcworld")

    if length <= 0 or length > MAX_UPLOAD:
        raise FileError("El archivo es demasiado grande", 413)

    fd, tmp = tempfile.mkstemp(prefix="mcpanel-world-", suffix=".zip")
    remaining = length

    try:
        with os.fdopen(fd, "wb") as f:
            while remaining > 0:
                chunk = handler.rfile.read(min(1024 * 1024, remaining))

                if not chunk:
                    raise FileError("La subida se interrumpió")

                f.write(chunk)
                remaining -= len(chunk)

        return import_archive(tmp, name, user)
    finally:
        os.remove(tmp)
