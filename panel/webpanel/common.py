#
# MCServer by Derpchees - Utilidades comunes: servidor de la peticion actual, errores, JSON y cache
#

import subprocess
import json
import os
import time
import threading
import urllib.request

import mcpanel_core as core


INSTALL_DIR = core.INSTALL_DIR
DEFAULT_LANG = core.DEFAULT_LANG

# Cambia en cada arranque del panel: la pagina lo usa para saber que el
# panel ya se reinicio (por ejemplo despues de actualizarse)
BOOT_ID = "%d-%d" % (time.time() * 1000, os.getpid())


# Servidor de la peticion actual. El manejador lo fija con use_server()
# y todas las funciones de un servidor lo leen con S().
_ctx = threading.local()


def S():
    return _ctx.srv


def current_server():
    return getattr(_ctx, "srv", None)


def use_server(srv):
    _ctx.srv = srv


def command(cmd):
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except Exception:
        return ""


def container_info():
    running = command(
        "docker inspect -f '{{.State.Running}}' "
        + S().container + " 2>/dev/null"
    )

    status = command(
        "docker inspect -f '{{.State.Status}}' "
        + S().container + " 2>/dev/null"
    )

    health = command(
        "docker inspect -f "
        "'{{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}' "
        + S().container + " 2>/dev/null"
    )

    return running, status, health


def autostop_info():
    default = {
        "enabled": True,
        "running": False,
        "health": "offline",
        "players": 0,
        "idle_seconds": 0,
        "remaining_seconds": 600,
        "timeout_seconds": 600
    }

    try:
        with open(S().run_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Segundos desde que mc-autostop.sh escribio el estado;
        # la pagina lo usa para que el contador no vaya a saltos
        data["age"] = max(
            0,
            time.time() - os.path.getmtime(S().run_file)
        )

        return data
    except Exception:
        return default


def read_lines(path):
    if not os.path.exists(path):
        return []

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as f:
            return [x.strip() for x in f if x.strip()]
    except Exception:
        return []


class FileError(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def give_to_server(path):
    try:
        os.chown(path, core.MC_UID, core.MC_GID, follow_symlinks=False)
    except Exception:
        pass


def read_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_file(path, data, owner=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-panel"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    if owner:
        give_to_server(tmp)

    os.replace(tmp, path)


def set_stop_hint(srv, reason):
    try:
        os.makedirs(os.path.dirname(srv.run_file), exist_ok=True)

        with open(srv.run_file + ".hint", "w") as f:
            f.write("%s %d" % (reason, int(time.time())))
    except OSError:
        pass


def log_server_action(srv, text):
    try:
        os.makedirs(srv.log_dir, exist_ok=True)

        with open(os.path.join(srv.log_dir, "actions.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " | " + text + "\n")
    except OSError:
        pass


VERSIONS_TTL = 6 * 3600


_versions_cache = {}
_versions_lock = threading.Lock()


def fetch_url(url, timeout=12):
    request = urllib.request.Request(url, headers={"User-Agent": "MCServer-panel"})

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def cached(key, producer):
    with _versions_lock:
        entry = _versions_cache.get(key)

        if entry and time.time() - entry[0] < VERSIONS_TTL:
            return entry[1]

    value = producer()

    with _versions_lock:
        _versions_cache[key] = (time.time(), value)

    return value
