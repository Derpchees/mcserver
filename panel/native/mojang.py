#
# MCServer by Derpchees - versiones de Minecraft Java (lista oficial de Mojang)
#

import json
import os
import re

import mcpanel_core as core

from . import fetch

MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def cache_dir():
    path = os.path.join(core.STATE_ROOT, "cache")
    os.makedirs(path, exist_ok=True)
    return path


def manifest():
    return fetch.get_json(MANIFEST)


def resolve(version):
    # "LATEST" (o vacio) -> la ultima version estable
    if not version or version.upper() == "LATEST":
        return manifest()["latest"]["release"]

    return version


def version_info(version):
    # Detalles de una version (descarga del servidor y Java que pide). Se
    # guardan: no cambian nunca.
    path = os.path.join(cache_dir(), "mc-%s.json" % re.sub(r"[^0-9A-Za-z._-]", "_", version))

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        pass

    entry = next((v for v in manifest()["versions"] if v["id"] == version), None)

    if not entry:
        raise RuntimeError("Minecraft %s no existe" % version)

    info = fetch.get_json(entry["url"])

    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f)

    return info


def java_major(version):
    # Java que necesita cada version (lo dice Mojang; si no responde, se calcula)
    try:
        return int(version_info(version)["javaVersion"]["majorVersion"])
    except Exception:
        pass

    m = re.match(r"^1\.(\d+)(?:\.(\d+))?", version or "")

    if not m:
        return 25

    minor, patch = int(m.group(1)), int(m.group(2) or 0)

    if minor < 17:
        return 8
    if minor < 20 or (minor == 20 and patch < 5):
        return 17

    return 21


def server_download(version):
    # (url, sha1) del server.jar oficial
    server = version_info(version).get("downloads", {}).get("server")

    if not server:
        raise RuntimeError("Minecraft %s no tiene servidor oficial" % version)

    return server["url"], server.get("sha1")
