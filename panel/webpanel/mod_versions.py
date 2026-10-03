#
# MCServer by Derpchees - Version de mods, plugins y modpacks
#
# Por defecto se usa la version mas reciente compatible. Aqui se puede
# fijar una version concreta:
#   - mods y plugins (Modrinth): MODRINTH_PROJECTS con "slug:version"
#   - modpack de Modrinth: MODRINTH_VERSION
#   - modpack de CurseForge: CF_FILE_ID
# Fijar o quitar una version recrea el contenedor (o queda pendiente si
# el servidor esta encendido), igual que agregar mods.
#

import json
import re
import urllib.parse

import mcpanel_core as core

from .common import FileError, log_server_action, read_json_file, S, use_server, write_json_file
from .containers import request_rebuild
from .mods import (
    CF_CLASS, CF_GAME, cf_get, MOD_KIND, mod_pins, mod_slugs, mods_meta_path, modrinth_get,
    MODRINTH_LOADER, modrinth_version_of, PLUGIN_LOADERS, PROJECT_ID, set_mod_slugs,
)

CF_RELEASE = {1: "release", 2: "beta", 3: "alpha"}
GAME_VERSION = re.compile(r"^\d+\.\d+(\.\d+)?$")
MAX_VERSIONS = 60


def modrinth_item(version):
    return {
        "id": version.get("id"),
        "number": str(version.get("version_number") or version.get("name") or "")[:60],
        "type": version.get("version_type") or "release",
        "game_versions": [v for v in version.get("game_versions", []) if GAME_VERSION.match(v)][-4:],
        "loaders": version.get("loaders", []),
        "date": (version.get("date_published") or "")[:10],
        "downloads": version.get("downloads", 0)
    }


def cf_item(file):
    return {
        "id": str(file.get("id")),
        "number": str(file.get("displayName") or file.get("fileName") or "")[:60],
        "type": CF_RELEASE.get(file.get("releaseType"), "release"),
        "game_versions": [v for v in file.get("gameVersions", []) if GAME_VERSION.match(v)][-4:],
        "loaders": [],
        "date": (file.get("fileDate") or "")[:10],
        "downloads": file.get("downloadCount", 0)
    }


# ------------------------------------------------------------
# Mods y plugins
# ------------------------------------------------------------

def project_versions(slug):
    # Versiones compatibles con el cargador y la version de Minecraft del servidor
    if slug not in mod_slugs():
        raise FileError("Ese proyecto no está agregado", 404)

    params = {}

    if MOD_KIND.get(S().type) == "plugins":
        params["loaders"] = json.dumps(sorted(PLUGIN_LOADERS))
    elif S().type in MODRINTH_LOADER:
        params["loaders"] = json.dumps([MODRINTH_LOADER[S().type]])

    if S().version not in ("", "LATEST", "SNAPSHOT"):
        params["game_versions"] = json.dumps([S().version])

    data = modrinth_get("/project/%s/version" % urllib.parse.quote(slug), params) or []

    return {
        "slug": slug,
        "current": mod_pins().get(slug, ""),
        "game_version": S().version,
        "versions": [modrinth_item(v) for v in data[:MAX_VERSIONS]]
    }


def set_project_version(data, user):
    slug = str(data.get("slug", ""))
    version = str(data.get("version") or "")
    slugs = mod_slugs()

    if slug not in slugs:
        raise FileError("Ese proyecto no está agregado", 404)

    pins = mod_pins()
    meta = read_json_file(mods_meta_path(), {})
    entry = meta.setdefault(slug, {})

    if version:
        info = modrinth_version_of(slug, version)
        pins[slug] = info["id"]
        entry["version_name"] = info["version_number"]
    else:
        pins.pop(slug, None)
        entry.pop("version_name", None)

    write_json_file(mods_meta_path(), meta)
    applied = set_mod_slugs(slugs, pins)
    log_server_action(S(), "%s fijó %s en %s" % (user["username"], slug, entry.get("version_name") or "la última versión"))

    return {"ok": True, "message": "Versión cambiada", "applied": applied}


# ------------------------------------------------------------
# Modpacks
# ------------------------------------------------------------

def cf_modpack(slug):
    found = cf_get("/mods/search", {"gameId": CF_GAME, "classId": CF_CLASS["modpacks"], "slug": slug}).get("data", [])

    if not found:
        raise FileError("No se encontró el modpack en CurseForge")

    return found[0]


def modpack_versions(slug=""):
    # Del modpack actual, o de uno de Modrinth que se esta por elegir
    srv = S()

    if slug:
        if not PROJECT_ID.match(slug):
            raise FileError("Modpack no válido")

        provider, current = "modrinth", ""
    elif srv.type == "MODRINTH":
        provider, slug, current = "modrinth", srv.extra_env.get("MODRINTH_MODPACK", ""), srv.extra_env.get("MODRINTH_VERSION", "")
    elif srv.type == "AUTO_CURSEFORGE":
        provider, slug, current = "curseforge", srv.extra_env.get("CF_SLUG", ""), srv.extra_env.get("CF_FILE_ID", "")
    else:
        raise FileError("Este servidor no usa un modpack")

    if provider == "modrinth":
        data = modrinth_get("/project/%s/version" % urllib.parse.quote(slug)) or []
        versions = [modrinth_item(v) for v in data[:MAX_VERSIONS]]
    else:
        files = cf_get("/mods/%d/files" % cf_modpack(slug)["id"], {"pageSize": 50}).get("data", [])
        files.sort(key=lambda f: f.get("fileDate") or "", reverse=True)
        versions = [cf_item(f) for f in files[:MAX_VERSIONS]]

    return {"slug": slug, "provider": provider, "current": current, "versions": versions}


def set_modpack_version(data, user):
    srv = S()
    version = str(data.get("version") or "")
    extra = dict(srv.extra_env)
    meta = read_json_file(mods_meta_path(), {})
    pack = meta.setdefault("_modpack", {})
    name = ""

    if srv.type == "MODRINTH":
        extra.pop("MODRINTH_VERSION", None)

        if version:
            info = modrinth_version_of(extra.get("MODRINTH_MODPACK", ""), version)
            extra["MODRINTH_VERSION"] = info["id"]
            name = info["version_number"]
    elif srv.type == "AUTO_CURSEFORGE":
        extra.pop("CF_FILE_ID", None)

        if version:
            if not version.isdigit():
                raise FileError("Versión no válida")

            mod = cf_modpack(extra.get("CF_SLUG", ""))
            file = (cf_get("/mods/%d/files/%s" % (mod["id"], version), {}) or {}).get("data") or {}

            if str(file.get("modId")) != str(mod["id"]):
                raise FileError("Esa versión no es de este proyecto")

            extra["CF_FILE_ID"] = version
            name = cf_item(file)["number"]
    else:
        raise FileError("Este servidor no usa un modpack")

    if name:
        pack["version_name"] = name
    else:
        pack.pop("version_name", None)

    write_json_file(mods_meta_path(), meta)
    core.update_server(srv.id, extra_env=json.dumps(extra))
    fresh = core.get_server(srv.id)
    use_server(fresh)
    applied = request_rebuild(fresh)
    log_server_action(fresh, "%s cambió la versión del modpack a %s" % (user["username"], name or "la última"))

    return {"ok": True, "message": "Versión cambiada", "applied": applied}
