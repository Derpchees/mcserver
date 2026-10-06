#
# MCServer by Derpchees - Ajustes del servidor (server.properties)
#

import os
import re

import mcpanel_core as core
import runtime
from bedrock import console as bedrock_console

from .common import container_info, FileError, give_to_server, read_lines, S


# Solo estas claves se pueden leer y cambiar desde el panel. Puertos y
# RCON quedan fuera a proposito: cambiarlos dejaria al panel sin conexion.
SETTINGS = {
    "difficulty": ("enum", ["peaceful", "easy", "normal", "hard"]),
    "gamemode": ("enum", ["survival", "creative", "adventure", "spectator"]),
    "force-gamemode": ("bool", None),
    "hardcore": ("bool", None),
    "pvp": ("bool", None),
    "allow-flight": ("bool", None),
    "enable-command-block": ("bool", None),
    "spawn-protection": ("int", (0, 256)),
    "player-idle-timeout": ("int", (0, 1440)),

    "spawn-monsters": ("bool", None),
    "spawn-animals": ("bool", None),
    "spawn-npcs": ("bool", None),
    "allow-nether": ("bool", None),
    "view-distance": ("int", (3, 32)),
    "simulation-distance": ("int", (3, 32)),

    "max-players": ("int", (1, 200)),
    "white-list": ("bool", None),
    "enforce-whitelist": ("bool", None),
    "online-mode": ("bool", None),
    "hide-online-players": ("bool", None)
}

# Se aplican al momento por RCON; el resto necesita reiniciar
LIVE_SETTINGS = {
    "difficulty": lambda v: ["difficulty", v],
    "white-list": lambda v: ["whitelist", "on" if v == "true" else "off"]
}

# Bedrock tiene otras claves (y no tiene RCON: se aplican con send-command)
BEDROCK_SETTINGS = {
    "difficulty": ("enum", ["peaceful", "easy", "normal", "hard"]),
    "gamemode": ("enum", ["survival", "creative", "adventure"]),
    "force-gamemode": ("bool", None),
    "allow-cheats": ("bool", None),
    "player-idle-timeout": ("int", (0, 1440)),

    "view-distance": ("int", (5, 96)),
    "tick-distance": ("int", (4, 12)),

    "max-players": ("int", (1, 200)),
    "allow-list": ("bool", None),
    "online-mode": ("bool", None),
    "default-player-permission-level": ("enum", ["visitor", "member", "operator"]),
    "texturepack-required": ("bool", None)
}

BEDROCK_LIVE = {
    "difficulty": lambda v: ["difficulty", v]
}


def allowed_settings():
    return BEDROCK_SETTINGS if core.is_bedrock(S()) else SETTINGS


def live_settings():
    return BEDROCK_LIVE if core.is_bedrock(S()) else LIVE_SETTINGS


def unescape_property(value):
    def replace(match):
        token = match.group(1)

        if token.startswith("u"):
            return chr(int(token[1:], 16))

        return {"n": "\n", "t": "\t"}.get(token, token)

    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", replace, value)


def escape_property(value):
    out = []

    for ch in value.replace("\\", "\\\\"):
        out.append(ch if 32 <= ord(ch) < 127 else "\\u%04x" % ord(ch))

    return "".join(out)


def read_properties():
    values = {}

    for line in read_lines(os.path.join(S().data_dir, "server.properties")):
        if line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        values[key.strip()] = unescape_property(value)

    return values


def clean_setting(key, value):
    kind, rule = allowed_settings()[key]

    if kind == "bool":
        if value not in (True, False, "true", "false"):
            raise FileError("Valor no válido para " + key)
        return "true" if value in (True, "true") else "false"

    if kind == "enum":
        if value not in rule:
            raise FileError("Valor no válido para " + key)
        return value

    if kind == "int":
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise FileError("Valor no válido para " + key)

        if not rule[0] <= number <= rule[1]:
            raise FileError(
                "%s debe estar entre %d y %d" % (key, rule[0], rule[1])
            )

        return str(number)

    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value)).strip()

    if len(text) > rule:
        raise FileError("%s admite hasta %d caracteres" % (key, rule))

    return text


def get_settings():
    values = read_properties()
    running, _, _ = container_info()

    return {
        "running": running == "true",
        "values": {k: values.get(k, "") for k in allowed_settings()},
        "live": list(live_settings()),
        "edition": "bedrock" if core.is_bedrock(S()) else "java"
    }


def save_settings(changes):
    if not isinstance(changes, dict) or not changes:
        raise FileError("No hay cambios que guardar")

    if not os.path.isfile(os.path.join(S().data_dir, "server.properties")):
        raise FileError("No existe server.properties", 404)

    current = read_properties()
    updates = {}

    for key, value in changes.items():
        if key not in allowed_settings():
            raise FileError("Ajuste no permitido: " + str(key), 403)

        cleaned = clean_setting(key, value)

        if current.get(key) != cleaned:
            updates[key] = cleaned

    if not updates:
        return {"ok": True, "message": "Sin cambios", "changed": [], "restart": False}

    # Se reescriben solo las lineas cambiadas; el resto queda intacto
    with open(os.path.join(S().data_dir, "server.properties"), "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    pending = dict(updates)

    for i, line in enumerate(lines):
        if line.startswith("#") or "=" not in line:
            continue

        key = line.partition("=")[0].strip()

        if key in pending:
            lines[i] = key + "=" + escape_property(pending.pop(key))

    for key, value in pending.items():
        lines.append(key + "=" + escape_property(value))

    mode = os.stat(os.path.join(S().data_dir, "server.properties")).st_mode & 0o7777
    tmp = os.path.join(S().data_dir, "server.properties") + ".tmp-panel"

    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    os.chmod(tmp, mode)
    give_to_server(tmp)
    os.replace(tmp, os.path.join(S().data_dir, "server.properties"))

    running, _, _ = container_info()
    applied = []

    if running == "true":
        live = live_settings()

        for key, value in updates.items():
            if key not in live:
                continue

            if core.is_bedrock(S()):
                if bedrock_console.send(S(), " ".join(live[key](value)))[0]:
                    applied.append(key)
                continue

            if runtime.rcon(S(), live[key](value))[0]:
                applied.append(key)

    return {
        "ok": True,
        "message": "Ajustes guardados",
        "changed": sorted(updates),
        "applied": applied,
        # Con el servidor apagado todo se aplica en el proximo arranque
        "restart": running == "true" and any(k not in applied for k in updates)
    }
