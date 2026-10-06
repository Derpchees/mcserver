#
# MCServer by Derpchees - experimentos de Bedrock (funciones opcionales)
#
# Son los interruptores de "Experimentos" al crear un mundo (Beta APIs,
# funciones de creador...). Muchos add-ons los necesitan. Viven en el
# level.dat del mundo y solo se pueden cambiar con el servidor apagado: lo
# que se pide se guarda y se aplica antes del proximo arranque (runtime.start).
# Un mundo nuevo se crea al encender; si habia experimentos pedidos, el
# agente lo reinicia una vez para aplicarlos.
#

import json
import os

from native import props

from . import leveldat

# Nombres internos de Bedrock 1.26 (los mismos que guarda el juego)
EXPERIMENTS = ("gametest", "upcoming_creator_features", "experimental_creator_cameras",
               "villager_trades_rebalance")


def wanted_path(srv):
    return os.path.join(srv.state_dir, "experiments.json")


def level_dat(srv):
    name = props.read(os.path.join(srv.data_dir, "server.properties")).get("level-name") or "Bedrock level"
    return os.path.join(srv.data_dir, "worlds", name, "level.dat")


def wanted(srv):
    try:
        with open(wanted_path(srv), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None

    return {k: bool(v) for k, v in data.items() if k in EXPERIMENTS}


def current(srv):
    # Los que tiene el mundo (None si todavia no existe)
    path = level_dat(srv)

    if not os.path.isfile(path):
        return None

    _, root = leveldat.read(path)
    tag = leveldat.get(root, "experiments")
    items = dict(tag[1]) if tag and tag[0] == leveldat.COMPOUND else {}
    return {name: bool(items.get(name, (0, 0))[1]) for name in EXPERIMENTS}


def request(srv, changes):
    # Guarda lo pedido (se aplica con el servidor apagado)
    values = wanted(srv) or current(srv) or {name: False for name in EXPERIMENTS}
    values.update({k: bool(v) for k, v in changes.items() if k in EXPERIMENTS})
    os.makedirs(srv.state_dir, exist_ok=True)

    with open(wanted_path(srv), "w", encoding="utf-8") as f:
        json.dump(values, f)

    return values


def pending(srv):
    return wanted(srv) is not None


def apply_pending(srv):
    # Solo con el servidor apagado y el mundo ya creado. True si se aplico.
    values = wanted(srv)
    path = level_dat(srv)

    if values is None or not os.path.isfile(path):
        return False

    version, root = leveldat.read(path)
    tag = leveldat.get(root, "experiments")
    items = list(tag[1]) if tag and tag[0] == leveldat.COMPOUND else []

    for name, on in values.items():
        leveldat.put(items, name, (leveldat.BYTE, 1 if on else 0))

    used = any(v for v in values.values())

    # El juego marca el mundo como experimental para siempre una vez usado
    if used or leveldat.get(items, "experiments_ever_used", (0, 0))[1]:
        leveldat.put(items, "experiments_ever_used", (leveldat.BYTE, 1))
        leveldat.put(items, "saved_with_toggled_experiments", (leveldat.BYTE, 1))

    leveldat.put(root, "experiments", (leveldat.COMPOUND, items))
    leveldat.write(path, version, root)
    os.remove(wanted_path(srv))
    return True


def needs_restart(srv):
    # Mundo recien creado con experimentos pedidos: hay que reiniciarlo una vez
    return pending(srv) and os.path.isfile(level_dat(srv))
