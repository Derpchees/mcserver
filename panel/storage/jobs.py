#
# MCServer by Derpchees - almacenamiento: tareas en segundo plano
#
# Una tarea a la vez (crear un espacio, mover datos, agrandar). El panel
# consulta su avance con job_status().
#

import os
import threading
import time
import traceback

import mcpanel_core as core

from .system import StorageError

LOG_FILE = os.path.join(core.LOG_ROOT, "storage.log")

_job = {"running": False}
_job_lock = threading.Lock()


def job_status():
    with _job_lock:
        return dict(_job)


def log(text):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " | " + text + "\n")
    except OSError:
        pass


# Cada paso viaja como clave + datos; la pagina lo traduce (job.<clave>)
STEPS = {
    "gpt": "Creando la tabla de particiones (GPT) en {disk}",
    "partition": "Creando la partición {name} ({gb} GB) en {disk}",
    "format": "Dando formato a {device} (ext4)",
    "mount": "Montando en {mount}",
    "mount_existing": "Montando {device} en {mount} (no se formatea)",
    "extra_ready": "Partición para otro uso lista en {mount}",
    "lvm": "Creando el volumen {lv} de {gb} GB en {vg}",
    "image": "Apartando {gb} GB en {file}",
    "stop": "Apagando {server}",
    "copy": "Copiando {server} ({n} de {total})",
    "save": "Guardando la nueva ubicación",
    "container": "Actualizando el contenedor de {server}",
    "delete_old": "Borrando la copia anterior de {server}",
    "grow": "Agrandando el espacio a {gb} GB",
    "done": "Listo",
    "rebuild_copy": "Copiando el contenido de {mount} al disco del sistema ({n} de {total})",
    "rebuild_unmount": "Desmontando el disco",
    "rebuild_table": "Creando la tabla de particiones nueva en {disk}",
    "rebuild_restore": "Devolviendo los respaldos de {server}",
    "rebuild_others": "Devolviendo los demas archivos a {mount}",
}


_last_logged = {"text": None}


def step(code, progress=None, **values):
    # Al registro solo van los pasos (no cada avance) y sin repetir lineas
    text = STEPS.get(code, code).format(**values)

    if (progress is None or progress in (0, 100)) and text != _last_logged["text"]:
        _last_logged["text"] = text
        log(text)

    with _job_lock:
        _job["step"] = code
        _job["vars"] = values
        _job["progress"] = progress


def start_job(kind, work):
    with _job_lock:
        if _job.get("running"):
            raise StorageError("Ya hay una tarea de almacenamiento en curso")

        _job.clear()
        _job.update({"running": True, "kind": kind, "step": "", "progress": None,
                     "started": int(time.time()), "error": None})

    log("TAREA | " + kind)

    def wrapper():
        error = None

        try:
            work()
        except Exception as exc:
            error = str(exc)[:400]
            log("ERROR | " + error + "\n" + traceback.format_exc())
        finally:
            core.set_setting("storage_busy", "")

            with _job_lock:
                _job.update({"running": False, "error": error, "finished": int(time.time())})

            core.add_event(None, "storage_failed" if error else "storage_done",
                           "error" if error else "success", error or kind)

    threading.Thread(target=wrapper, daemon=True).start()
