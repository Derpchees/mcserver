#
# MCServer by Derpchees - Funciones experimentales (opcionales) del mundo
#
# Bedrock: los "Experimentos" del mundo (bedrock/experiments.py); se
# pueden cambiar cuando quieras y se aplican al reiniciar.
# Java: los paquetes experimentales de Minecraft (initial-enabled-packs);
# solo cuentan al crear el mundo, asi que se eligen antes del primer
# arranque o al regenerarlo.
#

import os
import re

import mcpanel_core as core
import runtime
from bedrock import experiments as bedrock_experiments

from .common import FileError, log_server_action, S
from .properties import ensure_properties, read_properties

# Paquetes experimentales de Java por version (los de la 1.21)
JAVA_EXPERIMENTS = {
    "1.21": ("trade_rebalance", "minecart_improvements", "redstone_experiments")
}


def java_version():
    version = S().version or ""

    if version.upper() == "LATEST" and S().type in ("VANILLA", "PAPER", "FABRIC"):
        try:
            from .versions import vanilla_versions
            from .common import cached
            version = cached("mc-VANILLA", vanilla_versions)[0]
        except Exception:
            return ""

    return version


def java_options():
    if S().type in ("MODRINTH", "AUTO_CURSEFORGE"):
        return ()

    m = re.match(r"^(1\.\d+)", java_version())
    return JAVA_EXPERIMENTS.get(m.group(1), ()) if m else ()


def java_world_exists():
    name = read_properties().get("level-name") or "world"
    return os.path.isfile(os.path.join(S().data_dir, name, "level.dat"))


def experiments_state():
    if core.is_bedrock(S()):
        try:
            current = bedrock_experiments.current(S())
        except (OSError, ValueError):
            current = None

        wanted = bedrock_experiments.wanted(S())
        values = wanted or current or {}

        return {
            "edition": "bedrock",
            "items": [{"id": name, "on": bool(values.get(name))} for name in bedrock_experiments.EXPERIMENTS],
            "editable": True,
            "pending": wanted is not None
        }

    options = java_options()
    enabled = [p.strip() for p in read_properties().get("initial-enabled-packs", "vanilla").split(",") if p.strip()]

    return {
        "edition": "java",
        "items": [{"id": name, "on": name in enabled} for name in options],
        # En Java solo cuentan al crear el mundo
        "editable": not java_world_exists(),
        "pending": False
    }


def set_experiments(data, user):
    changes = data.get("values")

    if not isinstance(changes, dict) or not changes:
        raise FileError("Petición no válida")

    srv = S()

    if core.is_bedrock(srv):
        bedrock_experiments.request(srv, changes)
        running = runtime.running(srv)

        if not running:
            try:
                bedrock_experiments.apply_pending(srv)
            except (OSError, ValueError) as error:
                raise FileError("No se pudo cambiar el mundo: %s" % error)

        log_server_action(srv, "%s cambió los experimentos del mundo" % user["username"])
        return {"ok": True, "message": "Experimentos guardados", "restart": running}

    if java_world_exists():
        raise FileError("Estas funciones solo se eligen al crear el mundo: regenéralo para cambiarlas")

    options = java_options()
    enabled = [p.strip() for p in read_properties().get("initial-enabled-packs", "vanilla").split(",") if p.strip()]

    for name, on in changes.items():
        if name not in options:
            raise FileError("Función no válida")

        if on and name not in enabled:
            enabled.append(name)
        elif not on and name in enabled:
            enabled.remove(name)

    if "vanilla" not in enabled:
        enabled.insert(0, "vanilla")

    from native import props
    props.update(ensure_properties(), {"initial-enabled-packs": ",".join(enabled)})
    log_server_action(srv, "%s cambió las funciones experimentales" % user["username"])
    return {"ok": True, "message": "Experimentos guardados", "restart": False}
