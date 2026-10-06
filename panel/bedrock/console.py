#
# MCServer by Derpchees - consola de Bedrock (sin RCON)
#
# Bedrock no tiene RCON: los comandos se escriben en la entrada del
# servidor con send-command (viene en la imagen) y la respuesta sale
# en el log del contenedor. Los jugadores conectados se cuentan con el
# estado que da para la lista de servidores y sus nombres salen del log.
#

import json
import re
import subprocess
import time

from . import signaling


# [2026-01-01 12:00:00:123 INFO] Player connected: Steve, xuid: 2535...
PLAYER_LINE = re.compile(r"Player (connected|disconnected): (.+?), xuid: ?(\d*)")

# Nombres de jugador de Bedrock (gamertags): letras, numeros y espacios
PLAYER_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ .#-]{0,31}$")

COLOR = {"green": "a", "aqua": "b", "gray": "7", "gold": "6", "red": "c", "yellow": "e"}


def clean(text):
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(text or "")).strip()


def quote(name):
    # Los nombres con espacios van entre comillas
    return '"%s"' % name.replace('"', "") if " " in name else name


def docker_logs(container, since=None, tail=None):
    args = ["docker", "logs"]

    if since is not None:
        args += ["--since", since if isinstance(since, str) else "%.3f" % since]

    if tail is not None:
        args += ["--tail", str(tail)]

    try:
        result = subprocess.run(args + [container], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""

    return result.stdout


def send(container, text, wait=0.0):
    # Manda una linea a la consola. Con wait, devuelve lo que el servidor
    # escribio en el log en esos segundos (la respuesta del comando).
    text = clean(text)

    if not text:
        return False, ""

    started = time.time() - 0.2

    try:
        # send-command busca el proceso en /proc: sin --privileged Docker no lo deja
        result = subprocess.run(["docker", "exec", "--privileged", container, "send-command"] + text.split(" "),
                                capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False, ""

    if result.returncode != 0:
        return False, (result.stdout + result.stderr).strip()

    if not wait:
        return True, ""

    time.sleep(wait)
    lines = [line for line in docker_logs(container, since=started).splitlines() if line.strip()]
    return True, "\n".join(lines[-40:])


def tellraw(container, target, text, label=None, color="gold"):
    # Mensaje en el chat del juego (formato rawtext de Bedrock)
    prefix = "§%s[%s]§r " % (COLOR.get(color, "6"), clean(label)) if label else ""
    payload = json.dumps({"rawtext": [{"text": prefix + clean(text)}]}, ensure_ascii=False)
    return send(container, "tellraw %s %s" % (target if target == "@a" else quote(target), payload))[0]


def started_at(container):
    try:
        result = subprocess.run(["docker", "inspect", "-f", "{{.State.StartedAt}}", container],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None

    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def online_names(container):
    # Conectados segun el log desde que arranco el contenedor
    output = docker_logs(container, since=started_at(container))
    online = {}

    for line in output.splitlines():
        m = PLAYER_LINE.search(line)

        if not m:
            continue

        kind, name, xuid = m.groups()

        if kind == "connected":
            online[name] = xuid
        else:
            online.pop(name, None)

    return online


def player_count(port):
    # Jugadores conectados (estado del puerto interno) o None si no responde
    info = signaling.status(port)
    return int(info.get("players") or 0) if info else None
