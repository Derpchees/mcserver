#
# MCServer by Derpchees - Versiones disponibles (Minecraft y cargadores de mods)
#

import json
import re
import xml.etree.ElementTree as ET
import urllib.parse

import mcpanel_core as core

from .common import cached, fetch_url, FileError


LOADER_TEXT = re.compile(r"^[0-9A-Za-z._+-]{1,40}$")
JAVA_CHOICES = ("", "8", "11", "17", "21", "25")

LOADER_ENV = core.LOADER_ENV


def is_stable(version):
    return not re.search(r"(pre|rc|snapshot|alpha|beta|w\d)", version, re.I)


def vanilla_versions():
    data = json.loads(fetch_url("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"))
    return [v["id"] for v in data["versions"] if v.get("type") == "release"]


def paper_versions():
    data = json.loads(fetch_url("https://fill.papermc.io/v3/projects/paper"))
    versions = []

    for group in data.get("versions", {}).values():
        versions += [v for v in group if is_stable(v)]

    return versions


def paper_builds(mc):
    data = json.loads(fetch_url("https://fill.papermc.io/v3/projects/paper/versions/%s/builds"
                                % urllib.parse.quote(mc)))
    builds = sorted(data, key=lambda b: b["id"], reverse=True)
    stable = [str(b["id"]) for b in builds if b.get("channel") == "STABLE"]

    return {"loaders": [str(b["id"]) for b in builds][:40], "recommended": stable[0] if stable else None}


def fabric_versions():
    data = json.loads(fetch_url("https://meta.fabricmc.net/v2/versions/game"))
    return [v["version"] for v in data if v.get("stable")]


def fabric_loaders():
    data = json.loads(fetch_url("https://meta.fabricmc.net/v2/versions/loader"))
    stable = [v["version"] for v in data if v.get("stable")]
    return {"loaders": [v["version"] for v in data][:40], "recommended": stable[0] if stable else None}


def forge_index():
    # maven-metadata.xml tiene todas las versiones como "<mc>-<forge>"
    root = ET.fromstring(fetch_url("https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"))
    by_mc = {}

    for node in root.iter("version"):
        mc, _, forge = (node.text or "").partition("-")

        if forge:
            by_mc.setdefault(mc, []).append(forge.split("-")[0])

    try:
        promos = json.loads(fetch_url(
            "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
        )).get("promos", {})
    except Exception:
        promos = {}

    return by_mc, promos


def version_key(text):
    return [int(p) if p.isdigit() else -1 for p in re.split(r"[.\-]", text)]


def neoforge_mc(version):
    # NeoForge sigue a Minecraft: 21.4.x -> 1.21.4, 21.0.x -> 1.21,
    # y desde la numeracion por ano 26.1.0.x -> 26.1, 26.1.1.x -> 26.1.1
    parts = version.split("-")[0].split(".")

    if len(parts) < 3 or not parts[0].isdigit():
        return None

    if int(parts[0]) >= 26:
        return parts[0] + "." + parts[1] + ("" if parts[2] == "0" else "." + parts[2])

    return "1." + parts[0] + ("" if parts[1] == "0" else "." + parts[1])


def neoforge_index():
    root = ET.fromstring(fetch_url("https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"))
    by_mc = {}

    for node in root.iter("version"):
        mc = neoforge_mc(node.text or "")

        if mc:
            by_mc.setdefault(mc, []).append(node.text)

    return by_mc


def neoforge_versions():
    by_mc = cached("neoforge-index", neoforge_index)
    return sorted(by_mc, key=version_key, reverse=True)


def neoforge_builds(mc):
    by_mc = cached("neoforge-index", neoforge_index)
    builds = sorted(set(by_mc.get(mc, [])), key=version_key, reverse=True)
    stable = [b for b in builds if is_stable(b)]

    return {"loaders": builds[:40], "recommended": stable[0] if stable else (builds[0] if builds else None)}


def forge_versions():
    by_mc, _ = cached("forge-index", forge_index)
    return sorted((mc for mc in by_mc if is_stable(mc)), key=version_key, reverse=True)


def forge_builds(mc):
    by_mc, promos = cached("forge-index", forge_index)
    builds = sorted(set(by_mc.get(mc, [])), key=version_key, reverse=True)
    recommended = promos.get(mc + "-recommended") or promos.get(mc + "-latest") or (builds[0] if builds else None)

    return {"loaders": builds[:40], "recommended": recommended}


def bedrock_versions():
    # La misma lista que usa la imagen de Bedrock cuando no responde la de Microsoft.
    # La version exacta va completa (1.26.52.3): asi la descarga la imagen.
    data = json.loads(fetch_url(
        "https://raw.githubusercontent.com/kittizz/bedrock-server-downloads/refs/heads/main/bedrock-server-downloads.json"
    ))
    versions = []

    for item in data.get("release", {}).values():
        m = re.search(r"bedrock-server-([0-9.]+)\.zip", ((item or {}).get("linux") or {}).get("url", ""))

        if m:
            versions.append(m.group(1))

    return sorted(set(versions), key=version_key, reverse=True)


def available_versions(type_, mc=""):
    # Sin mc: versiones de Minecraft del tipo. Con mc: versiones del cargador.
    type_ = (type_ or "").upper()

    if type_ not in core.SERVER_TYPES:
        raise FileError("Tipo de servidor no válido")

    try:
        if not mc:
            producer = {"VANILLA": vanilla_versions, "PAPER": paper_versions,
                        "FABRIC": fabric_versions, "FORGE": forge_versions,
                        "NEOFORGE": neoforge_versions, "BEDROCK": bedrock_versions}[type_]
            return {"versions": cached("mc-" + type_, producer)}

        if not LOADER_TEXT.match(mc):
            raise FileError("Versión no válida")

        if type_ in ("VANILLA", "BEDROCK"):
            return {"loaders": [], "recommended": None}

        if type_ == "FABRIC":
            return cached("fabric-loaders", fabric_loaders)

        if type_ == "PAPER":
            return cached("paper-" + mc, lambda: paper_builds(mc))

        if type_ == "NEOFORGE":
            return neoforge_builds(mc)

        return forge_builds(mc)

    except FileError:
        raise
    except Exception as error:
        # Sin internet o la fuente cambio: el panel deja escribir la version a mano
        return {"versions": [], "loaders": [], "error": str(error)[:120]}
