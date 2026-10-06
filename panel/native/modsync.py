#
# MCServer by Derpchees - mods y plugins de Modrinth sin Docker (Windows)
#
# Hace lo que MODRINTH_PROJECTS hace en la imagen de Docker: baja la
# version compatible de cada proyecto (o la fijada) y sus dependencias
# obligatorias. Lo que el panel bajo se anota en .mcpanel/mods.json para
# poder quitarlo despues; los archivos que subio la persona no se tocan.
#

import json
import os
import re
import urllib.parse

from . import fetch

API = "https://api.modrinth.com/v2"
MARK = os.path.join(".mcpanel", "mods.json")

# Cargadores que acepta cada tipo de servidor en Modrinth
LOADERS = {
    "FABRIC": ["fabric"],
    "FORGE": ["forge"],
    "NEOFORGE": ["neoforge"],
    "PAPER": ["paper", "spigot", "bukkit"]
}


def api(path, params=None):
    url = API + path

    if params:
        url += "?" + urllib.parse.urlencode({k: json.dumps(v) for k, v in params.items()})

    return fetch.get_json(url)


def compatible(project, mc, loaders):
    versions = api("/project/%s/version" % urllib.parse.quote(project),
                   {"loaders": loaders, "game_versions": [mc]})
    stable = [v for v in versions if v.get("version_type") == "release"]
    return (stable or versions or [None])[0]


def primary_file(version):
    files = version.get("files") or []
    return next((f for f in files if f.get("primary")), files[0] if files else None)


def sync(data_dir, folder, entries, mc, loaders, log):
    # entries: [(slug, id de version fijada o "")]
    target = os.path.join(data_dir, folder)
    os.makedirs(target, exist_ok=True)
    mark_path = os.path.join(data_dir, MARK)

    try:
        with open(mark_path, "r", encoding="utf-8") as f:
            installed = json.load(f)
    except (OSError, ValueError):
        installed = {}

    wanted = {}
    queue = list(entries)
    seen = set()

    while queue:
        project, pinned = queue.pop(0)

        if project in seen:
            continue

        seen.add(project)

        try:
            version = api("/version/%s" % urllib.parse.quote(pinned)) if pinned else compatible(project, mc, loaders)
        except Exception as error:
            log("Modrinth: no se pudo consultar %s (%s)" % (project, error))
            continue

        if not version:
            log("Modrinth: %s no tiene versión para %s %s" % (project, "/".join(loaders), mc))
            continue

        file = primary_file(version)

        if not file:
            continue

        name = re.sub(r'[\\/:*?"<>|]', "_", file["filename"])
        wanted[version["project_id"]] = name
        path = os.path.join(target, name)

        if not os.path.isfile(path):
            log("Descargando " + name)
            fetch.download(file["url"], path, {"sha512": (file.get("hashes") or {}).get("sha512")})

        for dep in version.get("dependencies") or []:
            if dep.get("dependency_type") == "required" and dep.get("project_id"):
                queue.append((dep["project_id"], dep.get("version_id") or ""))

    # Lo que el panel bajo antes y ya no se pide (o cambio de version) se borra
    keep = set(wanted.values())

    for name in set(installed.values()) - keep:
        try:
            os.remove(os.path.join(target, name))
            log("Quitado " + name)
        except OSError:
            pass

    os.makedirs(os.path.dirname(mark_path), exist_ok=True)

    with open(mark_path, "w", encoding="utf-8") as f:
        json.dump(wanted, f, indent=2)
