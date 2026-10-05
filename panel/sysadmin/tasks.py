#
# MCServer by Derpchees - tareas del sistema en segundo plano
#
# Cada tipo de tarea ("https", "update") corre en su hilo; el panel consulta
# su avance. El paso actual viaja como clave + datos y la pagina lo traduce.
#

import os
import threading
import time
import traceback

import mcpanel_core as core

_tasks = {}
_lock = threading.Lock()


class TaskError(Exception):
    pass


def log(kind, text):
    try:
        os.makedirs(core.LOG_ROOT, exist_ok=True)

        with open(os.path.join(core.LOG_ROOT, kind + ".log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " | " + text + "\n")
    except OSError:
        pass


def status(kind):
    with _lock:
        return dict(_tasks.get(kind) or {"running": False})


def step(kind, code, **values):
    log(kind, code + (" " + str(values) if values else ""))

    with _lock:
        task = _tasks.setdefault(kind, {})
        task["step"] = code
        task["vars"] = values


def start(kind, work, done_event=None):
    with _lock:
        if (_tasks.get(kind) or {}).get("running"):
            raise TaskError("Ya hay una tarea en curso")

        _tasks[kind] = {"running": True, "step": "", "vars": {}, "error": None, "started": int(time.time())}

    def wrapper():
        error = None

        try:
            work()
        except Exception as exc:
            error = str(exc)[:400]
            log(kind, "ERROR | " + error + "\n" + traceback.format_exc())

        with _lock:
            _tasks[kind].update({"running": False, "error": error, "finished": int(time.time())})

        if done_event:
            core.add_event(None, done_event + ("_failed" if error else "_done"),
                           "error" if error else "success", error or "")

    threading.Thread(target=wrapper, daemon=True).start()
