#
# MCServer by Derpchees - actualizar desde el panel
#
# Compara la version instalada con la de GitHub y, si se pide, descarga la
# version nueva y corre "install.sh --update" fuera del panel (como unidad
# de systemd), porque la actualizacion reinicia el panel. Se conservan la
# configuracion, las cuentas, los mundos y los respaldos.
#

import os
import re
import subprocess
import time
import urllib.request

import mcpanel_core as core

from sysadmin import tasks
from bedrock import console as bedrock_console

REPO = "Derpchees/mcserver"
BRANCH = "main"
RAW = "https://raw.githubusercontent.com/%s/%s/install.sh" % (REPO, BRANCH)
TARBALL = "https://codeload.github.com/%s/tar.gz/refs/heads/%s" % (REPO, BRANCH)
LOG = os.path.join(core.LOG_ROOT, "update.log")

_cache = {"ts": 0, "latest": None}


def installed_version():
    try:
        with open(os.path.join(core.INSTALL_DIR, "VERSION"), "r") as f:
            return f.read().strip() or "dev"
    except OSError:
        return "dev"


def version_tuple(text):
    return tuple(int(x) for x in re.findall(r"\d+", text or "")[:3]) or (0,)


def latest_version(force=False):
    # Se consulta GitHub como mucho cada 30 minutos
    if not force and _cache["latest"] and time.time() - _cache["ts"] < 1800:
        return _cache["latest"]

    request = urllib.request.Request(RAW, headers={"User-Agent": "MCServer-panel"})

    with urllib.request.urlopen(request, timeout=15) as response:
        m = re.search(r'^VERSION="([^"]+)"', response.read().decode("utf-8", "replace"), re.M)

    if not m:
        raise tasks.TaskError("No se pudo leer la versión de GitHub")

    _cache.update({"ts": time.time(), "latest": m.group(1)})
    return m.group(1)


def players_online():
    total = 0

    for srv in core.list_servers():
        if core.container_state(srv)[0] != "running":
            continue

        if core.is_bedrock(srv):
            total += bedrock_console.player_count(srv.internal_port) or 0
            continue

        result = core.docker("exec", srv.container, "rcon-cli", "list")
        m = re.search(r"There are (\d+)", re.sub(r"\x1b\[[0-9;]*m", "", result.stdout))
        total += int(m.group(1)) if m else 0

    return total


def status(force=False):
    current = installed_version()
    info = {"installed": current, "latest": None, "available": False, "error": None,
            "repo": "https://github.com/" + REPO, "task": tasks.status("update")}

    try:
        info["latest"] = latest_version(force)
        info["available"] = current == "dev" or version_tuple(info["latest"]) > version_tuple(current)
    except Exception as error:
        info["error"] = str(error)[:200]

    return info


def start_update():
    # Corre fuera del panel: install.sh reinicia mcpanel-web y mcpanel-agent
    script = (
        "set -e; T=$(mktemp -d); trap 'rm -rf \"$T\"' EXIT; "
        "curl -fsSL %s | tar xz -C \"$T\"; "
        "SRC=$(find \"$T\" -mindepth 1 -maxdepth 1 -type d | head -1); "
        "bash \"$SRC/install.sh\" --update" % TARBALL
    )

    tasks.log("update", "ACTUALIZANDO desde %s (instalada %s)" % (TARBALL, installed_version()))

    result = subprocess.run(
        ["systemd-run", "--unit", "mcpanel-update-%d" % int(time.time()), "--collect", "--quiet",
         "-p", "StandardOutput=append:" + LOG, "-p", "StandardError=append:" + LOG,
         "bash", "-c", script],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        raise tasks.TaskError("No se pudo iniciar la actualización: " + result.stderr.strip()[:200])

    return {"ok": True, "message": "Actualizando"}
