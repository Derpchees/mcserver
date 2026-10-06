#
# MCServer by Derpchees - Estado del contenedor, actividad, consola y comandos
#

import os
import re
import time
import calendar

import mcpanel_core as core
import runtime
from bedrock import console as bedrock_console

from .common import autostop_info, container_info, read_lines, S
from .motd import read_motd
from .containers import has_pending


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

# Bedrock: "[fecha INFO] Player connected: Steve, xuid: 2535..."
BEDROCK_PLAYER_EVENT = re.compile(
    r"^(\S+) .*Player (connected|disconnected): (.+?), xuid"
)

_player_cache = {}


def player_events():
    # docker logs es grande; se consulta como mucho cada 10s
    cached = _player_cache.get(S().container)

    if cached and time.time() - cached[0] < 10:
        return cached[1]

    output = runtime.logs(S(), since=time.time() - 168 * 3600, timestamps=True)
    events = []

    for line in output.splitlines():
        if "the game" not in line and "Player " not in line:
            continue

        m = PLAYER_EVENT.match(line.strip())
        b = None if m else BEDROCK_PLAYER_EVENT.match(line.strip())

        if b:
            stamp, kind, name = b.groups()
            kind = "joined" if kind == "connected" else "left"
        elif m:
            stamp, name, kind = m.groups()
        else:
            continue

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
        "pending": has_pending(S())
    }


def docker_action(name):
    commands = {
        "start": runtime.start,
        "stop": runtime.stop,
        "restart": runtime.restart
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

    ok, error = commands[name](S())

    if ok:
        return {
            "ok": True,
            "message": messages[name]
        }

    return {
        "ok": False,
        "message": "No se pudo completar la acción",
        "output": error
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

    if core.is_bedrock(S()):
        # La respuesta sale en el log: se espera un momento para leerla
        ok, output = bedrock_console.send(S(), command_text, wait=1.0)

        return {
            "ok": ok,
            "message": "Comando enviado" if ok else "No se pudo ejecutar el comando",
            "output": output
        }

    ok, output = runtime.rcon(S(), [command_text])

    return {
        "ok": ok,
        "message": "Comando enviado" if ok else "No se pudo ejecutar el comando",
        "output": output
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

    lines = [
        x for x in runtime.logs(S(), tail=2000).splitlines()
        if not RCON_NOISE.search(x)
    ]

    return "\n".join(lines[-250:])[-60000:]
