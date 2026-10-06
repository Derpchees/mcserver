#
# MCServer by Derpchees - Jugadores de un servidor Bedrock
#
# Bedrock guarda a los jugadores por XUID (cuenta de Xbox) en allowlist.json
# y permissions.json. Los nombres salen del log ("Player connected: X, xuid: N")
# y se recuerdan en el estado del panel. No tiene baneos ni suspensiones.
#

import os
import re
import time

from bedrock import console as bedrock_console

from .common import autostop_info, container_info, FileError, read_json_file, S, write_json_file
from .status import player_events


GAMEMODES = ("survival", "creative", "adventure", "spectator")
_names_cache = {}


def names_path():
    return os.path.join(S().state_dir, "bedrock-players.json")


def known_names():
    # xuid -> nombre; se actualiza con el log como mucho cada 10s
    path = names_path()
    names = read_json_file(path, {})
    cached = _names_cache.get(S().container)

    if cached and time.time() - cached < 10:
        return names

    _names_cache[S().container] = time.time()
    output = bedrock_console.docker_logs(S().container, since="168h")
    changed = False

    for line in output.splitlines():
        m = bedrock_console.PLAYER_LINE.search(line)

        if m and m.group(3) and names.get(m.group(3)) != m.group(2):
            names[m.group(3)] = m.group(2)
            changed = True

    if changed:
        write_json_file(path, names)

    return names


def list_players():
    data = os.path.realpath(S().data_dir)
    allowlist = read_json_file(os.path.join(data, "allowlist.json"), [])
    permissions = read_json_file(os.path.join(data, "permissions.json"), [])
    names = known_names()

    running, _, _ = container_info()
    online = []

    if running == "true":
        online = [n for n in autostop_info().get("names", []) if isinstance(n, str)]

    players = {}

    def entry(name, xuid=""):
        key = name.lower()

        if key not in players:
            players[key] = {"name": name, "uuid": xuid, "online": False, "op": False, "op_level": 0,
                            "whitelisted": False, "ban": None, "first_seen": None, "last_seen": None,
                            "joins": 0}

        if xuid and not players[key]["uuid"]:
            players[key]["uuid"] = xuid

        return players[key]

    for xuid, name in names.items():
        entry(name, xuid)

    for item in allowlist:
        name = item.get("name") or names.get(str(item.get("xuid", "")))

        if name:
            entry(name, str(item.get("xuid", "")))["whitelisted"] = True

    for item in permissions:
        name = names.get(str(item.get("xuid", "")))

        if name and item.get("permission") == "operator":
            p = entry(name, str(item.get("xuid", "")))
            p["op"] = True
            p["op_level"] = 4

    for event in player_events():
        p = entry(event["text"])

        if event["type"] == "join":
            p["joins"] += 1
            p["first_seen"] = p["first_seen"] or event["ts"]

        p["last_seen"] = event["ts"]

    for name in online:
        p = entry(name)
        p["online"] = True
        p["last_seen"] = int(time.time())

    ordered = sorted(players.values(),
                     key=lambda p: (not p["online"], -(p["last_seen"] or 0), p["name"].lower()))

    return {"running": running == "true", "online": online, "players": ordered, "edition": "bedrock"}


def player_action(data, log_action):
    name = str(data.get("name", ""))
    action = str(data.get("action", ""))

    if not bedrock_console.PLAYER_NAME.match(name):
        raise FileError("Nombre de jugador no válido")

    running, _, _ = container_info()

    if running != "true":
        raise FileError("El servidor está apagado")

    quoted = bedrock_console.quote(name)
    container = S().container

    def reason_text(default):
        text = re.sub(r"[\x00-\x1f\x7f]", " ", str(data.get("reason", ""))).strip()[:120]
        return text or default

    if action == "kick":
        command = "kick %s %s" % (quoted, reason_text("Expulsado por un administrador"))
    elif action in ("op", "deop"):
        command = "%s %s" % (action, quoted)
    elif action in ("whitelist_add", "whitelist_remove"):
        command = "allowlist %s %s" % (action.split("_")[1], quoted)
    elif action == "gamemode":
        mode = str(data.get("mode", ""))

        if mode not in GAMEMODES:
            raise FileError("Modo de juego no válido")

        command = "gamemode %s %s" % (mode, quoted)
    elif action == "message":
        text = re.sub(r"[\x00-\x1f\x7f]", " ", str(data.get("text", ""))).strip()[:240]

        if not text:
            raise FileError("Mensaje vacío")

        ok = bedrock_console.tellraw(container, name, text, "Server -> " + name, "gold")
        log_action("message " + name)

        if not ok:
            raise FileError("No se pudo ejecutar la acción", 500)

        return {"ok": True, "message": "Acción aplicada", "output": ""}
    elif action == "tp":
        target = str(data.get("target", ""))

        if not bedrock_console.PLAYER_NAME.match(target):
            raise FileError("Nombre de jugador no válido")

        command = "tp %s %s" % (quoted, bedrock_console.quote(target))
    elif action == "kill":
        command = "kill " + quoted
    elif action in ("ban", "timeout", "pardon"):
        raise FileError("Bedrock no tiene baneos: usa la lista de permitidos")
    else:
        raise FileError("Acción no válida")

    ok, out = bedrock_console.send(container, command, wait=0.8)
    log_action(action + " " + name + (" | " + out.splitlines()[-1] if out else ""))

    if not ok:
        raise FileError("No se pudo ejecutar la acción", 500)

    failed = re.search(r"No targets matched|not found|Unknown|Syntax error|is not|already|Could not", out, re.I)

    return {"ok": not failed, "message": "Acción aplicada" if not failed else out.splitlines()[-1], "output": out}
