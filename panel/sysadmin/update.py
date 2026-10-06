#
# MCServer by Derpchees - actualizar desde el panel
#
# Compara la version instalada con la de GitHub y, si se pide, descarga la
# version nueva y corre "install.sh --update" fuera del panel (como unidad
# de systemd), porque la actualizacion reinicia el panel. Se conservan la
# configuracion, las cuentas, los mundos y los respaldos.
#

import json
import os
import re
import subprocess
import time
import urllib.request

import mcpanel_core as core
import runtime

from sysadmin import tasks
from bedrock import console as bedrock_console

REPO = "Derpchees/mcserver"
BRANCH = "main"
RAW = "https://raw.githubusercontent.com/%s/%s/install.sh" % (REPO, BRANCH)
TARBALL = "https://codeload.github.com/%s/tar.gz/refs/heads/%s" % (REPO, BRANCH)
LOG = os.path.join(core.LOG_ROOT, "update.log")

_cache = {"ts": 0, "latest": None, "notes_ts": 0, "notes": None}

# Notas de cada version (en ingles y espanol): las instaladas viajan con el
# panel; las de la version nueva se leen de GitHub antes de actualizar
NOTES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "changelog.json")
NOTES_RAW = "https://raw.githubusercontent.com/%s/%s/panel/changelog.json" % (REPO, BRANCH)


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

        _, output = runtime.rcon(srv, ["list"])
        m = re.search(r"There are (\d+)", re.sub(r"\u00a7.", "", output))
        total += int(m.group(1)) if m else 0

    return total


def clean_notes(data):
    out = []

    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not re.match(r"^\d+(\.\d+){1,3}$", str(item.get("version", ""))):
            continue

        out.append({
            "version": str(item["version"]),
            "date": str(item.get("date", ""))[:10],
            "en": [str(x)[:400] for x in item.get("en", [])][:20],
            "es": [str(x)[:400] for x in item.get("es", [])][:20]
        })

    return out


def installed_notes():
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return clean_notes(json.load(f))
    except (OSError, ValueError):
        return []


def latest_notes(force=False):
    if not force and _cache["notes"] is not None and time.time() - _cache["notes_ts"] < 1800:
        return _cache["notes"]

    request = urllib.request.Request(NOTES_RAW, headers={"User-Agent": "MCServer-panel"})

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            notes = clean_notes(json.loads(response.read(1024 * 1024)))
    except (OSError, ValueError):
        notes = []

    _cache.update({"notes_ts": time.time(), "notes": notes})
    return notes


def status(force=False):
    current = installed_version()
    info = {"installed": current, "latest": None, "available": False, "error": None,
            "repo": "https://github.com/" + REPO, "task": tasks.status("update")}

    try:
        info["latest"] = latest_version(force)
        info["available"] = current == "dev" or version_tuple(info["latest"]) > version_tuple(current)
    except Exception as error:
        info["error"] = str(error)[:200]

    # Novedades de lo que se instalaria y las de las versiones ya instaladas
    info["notes"] = installed_notes()
    info["notes_new"] = []

    if info["available"] and current != "dev":
        info["notes_new"] = [n for n in latest_notes(force)
                             if version_tuple(n["version"]) > version_tuple(current)]

    return info


RAW_PS1 = "https://raw.githubusercontent.com/%s/%s/install.ps1" % (REPO, BRANCH)


def start_update_windows():
    # install.ps1 -Update baja la version nueva, detiene la tarea "MCServer"
    # (panel y agente; los servidores siguen) y la vuelve a iniciar
    from native import procs

    tasks.log("update", "ACTUALIZANDO desde %s (instalada %s)" % (RAW_PS1, installed_version()))
    os.makedirs(core.LOG_ROOT, exist_ok=True)
    script = ("& ([scriptblock]::Create((Invoke-RestMethod -UseBasicParsing '%s'))) -Update -Dir '%s' *>> '%s'"
              % (RAW_PS1, core.HOME_DIR.replace("'", "''"), LOG.replace("'", "''")))

    try:
        procs.spawn_detached(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])
    except RuntimeError as error:
        raise tasks.TaskError("No se pudo iniciar la actualización: %s" % error)

    return {"ok": True, "message": "Actualizando"}


def start_update():
    if core.WINDOWS:
        return start_update_windows()

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
