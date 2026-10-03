#
# MCServer by Derpchees - Estado del contenedor, actividad, consola y comandos
#

import subprocess
import os
import re
import time
import calendar

from .common import autostop_info, command, container_info, read_lines, S
from .motd import read_motd
from .containers import pending_path


def activity():
    return read_lines(os.path.join(S().log_dir, "proxy.log"))


def local_ts(text):
    try:
        return time.mktime(
            time.strptime(text, "%Y-%m-%d %H:%M:%S")
        )
    except Exception:
        return 0


PLAYER_EVENT = re.compile(
    r"^(\S+) \[.*?\]: (\w{1,16}) (joined|left) the game$"
)

_player_cache = {}


def player_events():
    # docker logs es grande; se consulta como mucho cada 10s
    cached = _player_cache.get(S().container)

    if cached and time.time() - cached[0] < 10:
        return cached[1]

    output = command(
        "docker logs --timestamps --since 168h "
        + S().container
        + " 2>&1 | grep -E ' (joined|left) the game$'"
    )

    events = []

    for line in output.splitlines():
        m = PLAYER_EVENT.match(line.strip())

        if not m:
            continue

        stamp, name, kind = m.groups()

        try:
            ts = calendar.timegm(
                time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S")
            )
        except Exception:
            continue

        events.append({
            "ts": ts,
            "type": "join" if kind == "joined" else "leave",
            "text": name
        })

    _player_cache[S().container] = (time.time(), events)

    return events


def recent_events(lines, limit=30):
    # "text" es el nombre del jugador (join/leave) o un dato corto;
    # la pagina arma la frase en el idioma elegido
    events = list(player_events())

    for line in lines:
        stamp, _, rest = line.partition(" | ")

        if "PETICION RECIBIDA" in rest:
            kind = "request"
            state = rest.rpartition(":")[2].strip()
            text = "on" if state == "running" else "off"
        elif "INICIO AUTOMATICO" in rest:
            kind = "start"
            text = ""
        else:
            continue

        events.append({
            "ts": local_ts(stamp),
            "type": kind,
            "text": text
        })

    for line in read_lines(os.path.join(S().log_dir, "autostop.log")):
        stamp, _, rest = line.partition(" | ")

        if "APAGADO AUTOMATICAMENTE" in rest:
            events.append({
                "ts": local_ts(stamp),
                "type": "stop",
                "text": ""
            })

    events.sort(key=lambda x: x["ts"])

    return events[-limit:]


def server_data():
    running, status, health = container_info()
    lines = activity()

    attempts = [
        x for x in lines
        if "PETICION RECIBIDA" in x
    ]

    starts = [
        x for x in lines
        if "INICIO AUTOMATICO" in x
    ]

    return {
        "running": running == "true",
        "status": status or "desconocido",
        "health": health or "desconocido",
        "attempts": len(attempts),
        "last_attempt": attempts[-1] if attempts else "Ninguno",
        "last_start": starts[-1] if starts else "Ninguno",
        "events": recent_events(lines),
        "autostop": autostop_info(),
        "motd": read_motd(S()),
        "pending": os.path.exists(pending_path(S()))
    }


def docker_action(name):
    commands = {
        "start": ["docker", "start", S().container],
        "stop": ["docker", "stop", S().container],
        "restart": ["docker", "restart", S().container]
    }

    messages = {
        "start": "Servidor iniciado",
        "stop": "Servidor apagado",
        "restart": "Servidor reiniciado"
    }

    if name not in commands:
        return {
            "ok": False,
            "message": "Acción no válida"
        }

    result = subprocess.run(
        commands[name],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return {
            "ok": True,
            "message": messages[name]
        }

    return {
        "ok": False,
        "message": "Error ejecutando Docker",
        "output": result.stderr.strip()
    }


def send_command(command_text):
    command_text = command_text.strip()

    if not command_text:
        return {
            "ok": False,
            "message": "Comando vacío"
        }

    running, _, _ = container_info()

    if running != "true":
        return {
            "ok": False,
            "message": "El servidor está apagado"
        }

    result = subprocess.run(
        [
            "docker",
            "exec",
            S().container,
            "rcon-cli",
            command_text
        ],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return {
            "ok": True,
            "message": "Comando enviado",
            "output": result.stdout.strip()
        }

    return {
        "ok": False,
        "message": "No se pudo ejecutar el comando",
        "output": result.stderr.strip()
    }


# Lineas que genera mc-autostop.sh cada 10s al consultar
# jugadores con rcon-cli; solo ensucian la consola
RCON_NOISE = re.compile(
    r"Thread RCON Client /\S+ (started|shutting down)"
)


def console():
    running, _, _ = container_info()

    if running != "true":
        return "El servidor está apagado."

    result = subprocess.run(
        [
            "docker",
            "logs",
            "--tail",
            "2000",
            S().container
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace"
    )

    lines = [
        x for x in result.stdout.splitlines()
        if not RCON_NOISE.search(x)
    ]

    return "\n".join(lines[-250:])[-60000:]
