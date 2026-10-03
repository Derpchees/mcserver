#
# MCServer by Derpchees - Mods, plugins y modpacks (CurseForge y Modrinth)
#

import json
import os
import re
import urllib.parse
import urllib.request
import urllib.error

import mcpanel_core as core

from .common import FileError, log_server_action, read_json_file, S, use_server, write_json_file
from .containers import pending_path, request_rebuild


CF_API = "https://api.curseforge.com/v1"
CF_GAME = 432
CF_CLASS = {"mods": 6, "plugins": 5, "modpacks": 4471}
CF_LOADER = {"FORGE": 1, "FABRIC": 4, "NEOFORGE": 6}
MOD_KIND = {"FORGE": "mods", "NEOFORGE": "mods", "FABRIC": "mods", "PAPER": "plugins"}
CF_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,100}$")


def cf_key():
    return core.get_setting("cf_api_key")


def cf_get(path, params):
    key = cf_key()

    if not key:
        raise FileError("Falta la clave de API de CurseForge. El administrador la agrega en Administración.")

    request = urllib.request.Request(
        CF_API + path + "?" + urllib.parse.urlencode(params),
        headers={"x-api-key": key, "Accept": "application/json", "User-Agent": "MCServer-panel"}
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise FileError("CurseForge rechazó la clave de API")
        raise FileError("CurseForge respondió con un error (%d)" % error.code)
    except (urllib.error.URLError, OSError, ValueError):
        raise FileError("No se pudo conectar con CurseForge")


def cf_environment(mod):
    # Los archivos recientes de CurseForge indican "Server" o "Client"
    flags = set()

    for item in mod.get("latestFiles", []):
        flags |= set(item.get("gameVersions", []))

    if "Server" in flags:
        return "server"

    if "Client" in flags:
        return "client"

    return "unknown"


def cf_search(kind, query, version="", type_=""):
    if kind not in CF_CLASS:
        raise FileError("Búsqueda no válida")

    params = {
        "gameId": CF_GAME,
        "classId": CF_CLASS[kind],
        "searchFilter": str(query or "")[:80],
        "sortField": 2,
        "sortOrder": "desc",
        "pageSize": 30
    }

    if version and version != "LATEST" and kind != "modpacks":
        params["gameVersion"] = version

    if kind == "mods" and type_ in CF_LOADER:
        params["modLoaderType"] = CF_LOADER[type_]

    results = []

    for mod in cf_get("/mods/search", params).get("data", []):
        env = cf_environment(mod) if kind == "mods" else "server"

        # Solo mods que funcionan en el servidor
        if env == "client":
            continue

        results.append({
            "id": mod.get("id"),
            "slug": mod.get("slug", ""),
            "name": mod.get("name", ""),
            "summary": (mod.get("summary") or "")[:200],
            "downloads": mod.get("downloadCount", 0),
            "icon": (mod.get("logo") or {}).get("thumbnailUrl", ""),
            "author": ", ".join(a.get("name", "") for a in mod.get("authors", [])[:2]),
            "url": (mod.get("links") or {}).get("websiteUrl", ""),
            "env": env
        })

    return {"results": results}


MODRINTH_API = "https://api.modrinth.com/v2"
MODRINTH_UA = "Derpchees/mcserver (github.com/Derpchees/mcserver)"
MODRINTH_LOADER = {"FORGE": "forge", "NEOFORGE": "neoforge", "FABRIC": "fabric"}
PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$")
MODPACK_TYPES = ("AUTO_CURSEFORGE", "MODRINTH")


def modrinth_get(path, params=None):
    url = MODRINTH_API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    request = urllib.request.Request(url, headers={"User-Agent": MODRINTH_UA, "Accept": "application/json"})

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise FileError("Modrinth respondió con un error (%d)" % error.code)
    except (urllib.error.URLError, OSError, ValueError):
        raise FileError("No se pudo conectar con Modrinth")


def modrinth_env(server_side):
    if server_side in ("required", "optional"):
        return "server"

    if server_side == "unsupported":
        return "client"

    return "unknown"


def modrinth_item(project):
    slug = project.get("slug") or project.get("project_id") or project.get("id") or ""

    return {
        "id": project.get("project_id") or project.get("id"),
        "slug": slug,
        "name": project.get("title") or slug,
        "summary": (project.get("description") or "")[:200],
        "downloads": project.get("downloads", 0),
        "icon": project.get("icon_url") or "",
        "author": project.get("author") or "",
        "url": "https://modrinth.com/project/" + slug,
        "env": modrinth_env(project.get("server_side", ""))
    }


def modrinth_search(kind, query, version="", type_=""):
    if kind not in ("mods", "plugins", "modpacks"):
        raise FileError("Búsqueda no válida")

    if kind == "mods":
        facets = [["project_type:mod"]]

        if type_ in MODRINTH_LOADER:
            facets.append(["categories:" + MODRINTH_LOADER[type_]])
    elif kind == "plugins":
        facets = [["project_type:plugin"], ["categories:paper", "categories:spigot", "categories:bukkit"]]
    else:
        facets = [["project_type:modpack"]]

    # Solo proyectos que corren en el servidor
    if kind != "plugins":
        facets.append(["server_side:required", "server_side:optional"])

    if version and version != "LATEST" and kind != "modpacks":
        facets.append(["versions:" + version])

    data = modrinth_get("/search", {
        "query": str(query or "")[:80],
        "facets": json.dumps(facets),
        "limit": 40,
        "index": "relevance" if query else "downloads"
    }) or {}

    results = [modrinth_item(hit) for hit in data.get("hits", [])]

    # El filtro de Modrinth a veces deja pasar mods solo de cliente
    if kind != "plugins":
        results = [r for r in results if r["env"] != "client"]

    return {"results": results}


def parse_project_tokens(text):
    # Nombres (slugs), IDs o enlaces de Modrinth, separados por lineas,
    # comas o espacios
    tokens = []

    for raw in re.split(r"[\s,;]+", str(text or "")):
        raw = raw.strip()

        if not raw:
            continue

        m = re.search(r"modrinth\.com/(?:mod|plugin|modpack|project|datapack)/([^/?#\s]+)", raw)
        token = m.group(1) if m else raw

        if PROJECT_ID.match(token) and token not in tokens:
            tokens.append(token)

    return tokens[:150]


def mods_meta_path():
    return os.path.join(S().state_dir, "mods.json")


def mod_slugs():
    return [x for x in S().extra_env.get("MODRINTH_PROJECTS", "").split(",") if x]


def mods_state():
    kind = MOD_KIND.get(S().type)
    folder = os.path.join(S().data_dir, kind or "mods")
    files = []

    if os.path.isdir(folder):
        for entry in sorted(os.scandir(folder), key=lambda e: e.name.lower()):
            if entry.is_file() and entry.name.endswith(".jar"):
                files.append({"name": entry.name, "size": entry.stat().st_size})

    meta = read_json_file(mods_meta_path(), {})

    return {
        "kind": kind,
        "type": S().type,
        "version": S().version,
        "folder": kind or "mods",
        "projects": [dict(meta.get(slug, {}), slug=slug) for slug in mod_slugs()],
        "files": files,
        "modpack": (meta.get("_modpack") or {"slug": S().extra_env.get("MODRINTH_MODPACK") or S().extra_env.get("CF_SLUG", "")})
                   if S().type in MODPACK_TYPES else None,
        "pending": os.path.exists(pending_path(S())),
        "running": core.container_state(S())[0] == "running"
    }


def set_mod_slugs(slugs):
    extra = dict(S().extra_env)

    if slugs:
        extra["MODRINTH_PROJECTS"] = ",".join(slugs)
    else:
        extra.pop("MODRINTH_PROJECTS", None)

    core.update_server(S().id, extra_env=json.dumps(extra) if extra else "")
    fresh = core.get_server(S().id)
    use_server(fresh)
    return request_rebuild(fresh)


PLUGIN_LOADERS = {"paper", "spigot", "bukkit", "purpur", "folia"}


def add_mods(data, user):
    # Agrega varios a la vez: elegidos en la busqueda (items) y/o una
    # lista pegada (text). Cada proyecto se comprueba con Modrinth: debe
    # funcionar en el servidor y ser del tipo correcto (mod o plugin).
    if S().type not in MOD_KIND:
        raise FileError("Este tipo de servidor no admite mods ni plugins")

    plugins = MOD_KIND[S().type] == "plugins"
    loader = MODRINTH_LOADER.get(S().type)
    tokens = []

    for item in data.get("items") or []:
        if isinstance(item, dict) and PROJECT_ID.match(str(item.get("slug", ""))):
            tokens.append(str(item["slug"]))

    for token in parse_project_tokens(data.get("text", "")):
        if token not in tokens:
            tokens.append(token)

    tokens = tokens[:150]
    found = {}

    if tokens:
        for project in modrinth_get("/projects", {"ids": json.dumps(tokens)}) or []:
            for key in (project.get("slug"), project.get("id")):
                if key:
                    found[key] = project

    wanted = []
    skipped = []

    for token in tokens:
        project = found.get(token)

        if not project:
            skipped.append({"name": token, "reason": "not_found"})
            continue

        name = project.get("title") or token
        loaders = set(project.get("loaders") or [])

        if plugins and not (loaders & PLUGIN_LOADERS):
            skipped.append({"name": name, "reason": "not_plugin"})
            continue

        if not plugins and loader and loader not in loaders:
            skipped.append({"name": name, "reason": "wrong_loader"})
            continue

        if not plugins and modrinth_env(project.get("server_side")) == "client":
            skipped.append({"name": name, "reason": "client"})
            continue

        item = modrinth_item(project)
        wanted.append({"slug": item["slug"], "name": item["name"], "icon": item["icon"], "env": item["env"]})

    slugs = mod_slugs()
    meta = read_json_file(mods_meta_path(), {})
    added = []

    for item in wanted:
        if item["slug"] in slugs:
            continue

        slugs.append(item["slug"])
        meta[item["slug"]] = {"name": item["name"], "icon": item["icon"], "env": item["env"]}
        added.append(item["name"])

    if not added:
        return {"ok": True, "message": "Sin cambios", "added": [], "skipped": skipped, "applied": "none"}

    write_json_file(mods_meta_path(), meta)
    applied = set_mod_slugs(slugs)
    log_server_action(S(), "%s agregó: %s" % (user["username"], ", ".join(added)))

    return {"ok": True, "message": "Agregado", "added": added, "skipped": skipped, "applied": applied}


def remove_mods(data, user):
    remove = {str(s) for s in (data.get("slugs") or [])}
    slugs = mod_slugs()
    keep = [s for s in slugs if s not in remove]

    if len(keep) == len(slugs):
        raise FileError("Ese proyecto no está agregado", 404)

    meta = read_json_file(mods_meta_path(), {})

    for slug in remove:
        meta.pop(slug, None)

    write_json_file(mods_meta_path(), meta)
    applied = set_mod_slugs(keep)
    log_server_action(S(), "%s quitó: %s" % (user["username"], ", ".join(sorted(remove))))

    return {"ok": True, "message": "Quitado", "removed": len(slugs) - len(keep), "applied": applied}


def set_modpack(data, user):
    # Convierte el servidor en un modpack de Modrinth. Se guarda la
    # configuracion anterior para poder volver; el mundo no se toca.
    slug = str(data.get("slug", "")).strip()

    if not PROJECT_ID.match(slug):
        raise FileError("Modpack no válido")

    srv = S()
    meta = read_json_file(mods_meta_path(), {})

    if srv.type not in MODPACK_TYPES:
        meta["_prev"] = {"type": srv.type, "version": srv.version, "extra": srv.extra_env}

    meta["_modpack"] = {
        "slug": slug,
        "name": str(data.get("name") or slug)[:80],
        "icon": str(data.get("icon") or "")[:400]
    }
    write_json_file(mods_meta_path(), meta)

    core.update_server(srv.id, type="MODRINTH", version="LATEST",
                       extra_env=json.dumps({"MODRINTH_MODPACK": slug}))
    fresh = core.get_server(srv.id)
    use_server(fresh)
    applied = request_rebuild(fresh)
    log_server_action(fresh, "%s cambió el modpack a %s" % (user["username"], slug))

    return {"ok": True, "message": "Modpack elegido", "applied": applied}


def clear_modpack(user):
    srv = S()

    if srv.type not in MODPACK_TYPES:
        raise FileError("Este servidor no usa un modpack")

    meta = read_json_file(mods_meta_path(), {})
    prev = meta.pop("_prev", None) or {"type": "VANILLA", "version": "LATEST", "extra": {}}
    meta.pop("_modpack", None)
    write_json_file(mods_meta_path(), meta)

    core.update_server(srv.id, type=prev["type"], version=prev["version"],
                       extra_env=json.dumps(prev["extra"]) if prev.get("extra") else "")
    fresh = core.get_server(srv.id)
    use_server(fresh)
    applied = request_rebuild(fresh)
    log_server_action(fresh, "%s quitó el modpack" % user["username"])

    return {"ok": True, "message": "Modpack quitado", "applied": applied, "type": prev["type"]}
