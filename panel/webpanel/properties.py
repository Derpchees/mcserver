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
    "hide-online-players": ("bool", None),

    # Como se genera el mundo: solo cuenta antes de crearlo (o al regenerarlo)
    "level-seed": ("text", 64),
    "level-type": ("enum", ["minecraft:normal", "minecraft:flat", "minecraft:large_biomes", "minecraft:amplified"]),
    "generate-structures": ("bool", None)
}

# Valores de Minecraft cuando la clave no esta en server.properties (por
# ejemplo antes del primer arranque): el panel los muestra y se pueden
# cambiar antes de encenderlo
JAVA_DEFAULTS = {
    "difficulty": "easy", "gamemode": "survival", "force-gamemode": "false", "hardcore": "false",
    "pvp": "true", "allow-flight": "false", "enable-command-block": "false", "spawn-protection": "16",
    "player-idle-timeout": "0", "spawn-monsters": "true", "spawn-animals": "true", "spawn-npcs": "true",
    "allow-nether": "true", "view-distance": "10", "simulation-distance": "10", "max-players": "20",
    "white-list": "false", "enforce-whitelist": "false", "online-mode": "true",
    "hide-online-players": "false", "level-seed": "", "level-type": "minecraft:normal",
    "generate-structures": "true"
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
    "texturepack-required": ("bool", None),
    "level-seed": ("text", 64)
}

# El server.properties que trae Bedrock (sin la red, que pone el panel o la
# imagen). Si se configura antes del primer arranque se escribe completo:
# despues nadie lo completaria.
BEDROCK_DEFAULTS = {
    "gamemode": "survival", "force-gamemode": "false", "difficulty": "easy", "allow-cheats": "false",
    "max-players": "10", "online-mode": "true", "allow-list": "false", "enable-lan-visibility": "true",
    "view-distance": "32", "tick-distance": "4", "player-idle-timeout": "30", "max-threads": "8",
    "level-name": "Bedrock level", "level-seed": "", "default-player-permission-level": "member",
    "texturepack-required": "false", "content-log-file-enabled": "false",
    "content-log-console-output-enabled": "false", "content-log-level": "info",
    "compression-threshold": "1", "compression-algorithm": "zlib",
    "server-authoritative-movement-strict": "false", "server-authoritative-dismount-strict": "false",
    "server-authoritative-entity-interactions-strict": "false",
    "player-position-acceptance-threshold": "0.5", "player-movement-action-direction-threshold": "0.85",
    "server-authoritative-block-breaking-pick-range-scalar": "1.5", "chat-restriction": "None",
    "disable-player-interaction": "false", "client-side-chunk-generation-enabled": "true",
    "block-network-ids-are-hashes": "true", "disable-persona": "false", "disable-custom-skins": "false",
    "server-build-radius-ratio": "Disabled"
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


def properties_path(srv=None):
    return os.path.join((srv or S()).data_dir, "server.properties")


def defaults(srv=None):
    return BEDROCK_DEFAULTS if core.is_bedrock(srv or S()) else JAVA_DEFAULTS


def ensure_properties(srv=None):
    # Antes del primer arranque no hay server.properties: se crea para poder
    # configurar el servidor sin encenderlo (Bedrock completo, Java lo completa)
    srv = srv or S()
    path = properties_path(srv)

    if os.path.isfile(path):
        return path

    lines = ["%s=%s" % (k, v) for k, v in BEDROCK_DEFAULTS.items()] if core.is_bedrock(srv) else []

    if core.is_bedrock(srv) and srv.extra_env.get("SERVER_NAME"):
        lines.insert(0, "server-name=" + escape_property(srv.extra_env["SERVER_NAME"]))

    os.makedirs(srv.data_dir, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    give_to_server(path)
    return path


def read_properties():
    values = dict(defaults())

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

    ensure_properties()
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
