#
# MCServer by Derpchees - Jugadores
#

import json
import os
import re
import time
import threading

import mcpanel_core as core
import runtime

from .common import (
    autostop_info, container_info, FileError, read_json_file, S, use_server, write_json_file,
)
from .chat import chat_history
from . import bedrock_players


PLAYER_NAME = re.compile(r"^\w{1,16}$")
GAMEMODES = ("survival", "creative", "adventure", "spectator")
_timeouts_lock = threading.Lock()


def load_timeouts():
    return read_json_file(os.path.join(S().state_dir, "timeouts.json"), {})


def rcon(*args):
    return runtime.rcon(S(), args)


def log_action(text):
    try:
        with open(os.path.join(S().log_dir, "actions.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " | " + text + "\n")
    except Exception:
        pass


def list_players():
    if core.is_bedrock(S()):
        return bedrock_players.list_players()

    data = os.path.realpath(S().data_dir)
    cache = read_json_file(os.path.join(data, "usercache.json"), [])
    ops = read_json_file(os.path.join(data, "ops.json"), [])
    whitelist = read_json_file(os.path.join(data, "whitelist.json"), [])
    bans = read_json_file(os.path.join(data, "banned-players.json"), [])
    timeouts = load_timeouts()

    running, _, _ = container_info()
    online = []

    if running == "true":
        state = autostop_info()
        online = [n for n in state.get("names", []) if isinstance(n, str)]

    players = {}

    def entry(name, uuid=""):
        key = name.lower()

        if key not in players:
            players[key] = {
                "name": name,
                "uuid": uuid,
                "online": False,
                "op": False,
                "op_level": 0,
                "whitelisted": False,
                "ban": None,
                "first_seen": None,
                "last_seen": None,
                "joins": 0
            }

        if uuid and not players[key]["uuid"]:
            players[key]["uuid"] = uuid

        return players[key]

    # El cache puede tener el mismo nombre con varios UUID (modo
    # offline/online); se prefiere el que tiene datos de jugador
    playerdata = os.path.join(data, "world", "playerdata")

    for item in cache:
        name, uuid = item.get("name"), item.get("uuid", "")

        if not name:
            continue

        p = entry(name)

        if os.path.exists(os.path.join(playerdata, uuid + ".dat")) or not p["uuid"]:
            p["uuid"] = uuid

    for item in ops:
        if item.get("name"):
            p = entry(item["name"], item.get("uuid", ""))
            p["op"] = True
            p["op_level"] = item.get("level", 4)

    for item in whitelist:
        if item.get("name"):
            entry(item["name"], item.get("uuid", ""))["whitelisted"] = True

    for item in bans:
        if item.get("name"):
            p = entry(item["name"], item.get("uuid", ""))
            p["ban"] = {
                "reason": item.get("reason", ""),
                "created": item.get("created", ""),
                "source": item.get("source", ""),
                "until": timeouts.get(item["name"].lower())
            }

    for message in chat_history()["messages"]:
        if message["type"] not in ("join", "leave"):
            continue

        p = entry(message["name"])

        if message["type"] == "join":
            p["joins"] += 1
            p["first_seen"] = p["first_seen"] or message["ts"]

        p["last_seen"] = message["ts"]

    for name in online:
        p = entry(name)
        p["online"] = True
        p["last_seen"] = int(time.time())

    ordered = sorted(
        players.values(),
        key=lambda p: (not p["online"], -(p["last_seen"] or 0), p["name"].lower())
    )

    return {
        "running": running == "true",
        "online": online,
        "players": ordered
    }


def player_action(data):
    if core.is_bedrock(S()):
        return bedrock_players.player_action(data, log_action)

    name = str(data.get("name", ""))
    action = str(data.get("action", ""))

    if not PLAYER_NAME.match(name):
        raise FileError("Nombre de jugador no válido")

    running, _, _ = container_info()

    if running != "true":
        raise FileError("El servidor está apagado")

    def reason_text(default):
        text = re.sub(r"[\x00-\x1f\x7f]", " ", str(data.get("reason", ""))).strip()[:120]
        return text or default

    if action == "kick":
        ok, out = rcon("kick", name, reason_text("Expulsado por un administrador"))

    elif action == "ban":
        ok, out = rcon("ban", name, reason_text("Baneado por un administrador"))

        with _timeouts_lock:
            timeouts = load_timeouts()
            timeouts.pop(name.lower(), None)
            write_json_file(os.path.join(S().state_dir, "timeouts.json"), timeouts)

    elif action == "timeout":
        try:
            minutes = int(data.get("minutes", 0))
        except (TypeError, ValueError):
            minutes = 0

        if not 1 <= minutes <= 60 * 24 * 30:
            raise FileError("Duración no válida")

        until = int(time.time()) + minutes * 60
        ok, out = rcon("ban", name, reason_text("Suspensión temporal"))

        if ok:
            with _timeouts_lock:
                timeouts = load_timeouts()
                timeouts[name.lower()] = until
                write_json_file(os.path.join(S().state_dir, "timeouts.json"), timeouts)

    elif action == "pardon":
        ok, out = rcon("pardon", name)

        with _timeouts_lock:
            timeouts = load_timeouts()
            timeouts.pop(name.lower(), None)
            write_json_file(os.path.join(S().state_dir, "timeouts.json"), timeouts)

    elif action in ("op", "deop"):
        ok, out = rcon(action, name)

    elif action in ("whitelist_add", "whitelist_remove"):
        ok, out = rcon("whitelist", action.split("_")[1], name)

    elif action == "gamemode":
        mode = str(data.get("mode", ""))

        if mode not in GAMEMODES:
            raise FileError("Modo de juego no válido")

        ok, out = rcon("gamemode", mode, name)

    elif action == "message":
        text = re.sub(r"[\x00-\x1f\x7f]", " ", str(data.get("text", ""))).strip()[:240]

        if not text:
            raise FileError("Mensaje vacío")

        payload = json.dumps([
            "",
            {"text": "[Server -> " + name + "] ", "color": "gold"},
            {"text": text}
        ], ensure_ascii=False)

        ok, out = rcon("tellraw", name, payload)

    elif action == "tp":
        target = str(data.get("target", ""))

        if not PLAYER_NAME.match(target):
            raise FileError("Nombre de jugador no válido")

        ok, out = rcon("tp", name, target)

    elif action == "kill":
        ok, out = rcon("kill", name)

    else:
        raise FileError("Acción no válida")

    log_action(action + " " + name + (" | " + out if out else ""))

    if not ok:
        raise FileError("No se pudo ejecutar la acción", 500)

    # Minecraft responde en ingles: se devuelve tal cual para mostrarlo
    failed = re.search(
        r"No player was found|Unknown|Could not|not found|is not|Nothing changed|"
        r"already|Incorrect|Expected",
        out,
        re.I
    )

    return {
        "ok": not failed,
        "message": "Acción aplicada" if not failed else out,
        "output": out
    }


def timeout_loop():
    # Levanta los bans temporales vencidos de todos los servidores. Con el
    # servidor apagado se edita banned-players.json (Minecraft lo lee al arrancar).
    while True:
        time.sleep(30)

        for srv in core.list_servers():
            if core.is_bedrock(srv):
                continue

            use_server(srv)
            bans_file = os.path.join(srv.data_dir, "banned-players.json")

            try:
                with _timeouts_lock:
                    timeouts = load_timeouts()
                    now = time.time()
                    expired = [name for name, until in timeouts.items() if until <= now]

                    if not expired:
                        continue

                    running, _, _ = container_info()

                    for name in expired:
                        if running == "true":
                            ok, out = rcon("pardon", name)
                        else:
                            bans = read_json_file(bans_file, [])
                            bans = [b for b in bans if str(b.get("name", "")).lower() != name]
                            write_json_file(bans_file, bans, owner=True)
                            ok = True

                        if ok:
                            timeouts.pop(name, None)
                            log_action("timeout vencido " + name)

                    write_json_file(os.path.join(S().state_dir, "timeouts.json"), timeouts)
            except Exception:
                pass
