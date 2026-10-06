#
# MCServer by Derpchees - Add-ons de Bedrock: subir, activar, quitar y CurseForge
#
# Solo add-ons gratuitos: los que se suben (de CurseForge, MCPEDL, etc.) y
# los de CurseForge (todos gratis). El Marketplace de pago no se usa.
#

import datetime
import os
import re
import tempfile

import mcpanel_core as core
from bedrock.addons import Addons
from bedrock.packs import PackError

from .common import cached, FileError, fetch_url, log_server_action, S
from .mods import cf_get, page_number, SEARCH_PAGE
from .properties import ensure_properties, read_properties


MAX_UPLOAD = 500 * 1024 ** 2
UUID = re.compile(r"^[0-9a-f-]{32,36}$")

CF_GAME = 78022
CF_CLASS = {"addons": 4984, "textures": 6929}
CF_FILE_TYPES = (".mcaddon", ".mcpack", ".zip")
WORLD_FILE_TYPES = (".mcworld", ".zip")

# Orden de la busqueda (sortField de CurseForge)
CF_SORT = {"relevance": 2, "downloads": 6, "updated": 3, "newest": 11}


def store():
    if not core.is_bedrock(S()):
        raise FileError("Los add-ons son solo para servidores Bedrock")

    return Addons(S().data_dir, core.MC_UID, core.MC_GID)


def running():
    return core.container_state(S())[0] == "running"


def addons_state():
    items = store().installed()

    return {
        "addons": items,
        "running": running(),
        "cf_enabled": bool(core.get_setting("cf_api_key")),
        # Lo elige el dueno: si los jugadores deben bajar los paquetes de recursos
        "textures_required": read_properties().get(TEXTURES_KEY, "") == "true",
        "has_properties": True,
        "installed_cf": sorted({str(i["source"].get("id")) for i in items
                                if i["source"].get("provider") == "curseforge"})
    }


def check_uuid(value):
    value = str(value or "").lower()

    if not UUID.match(value):
        raise FileError("Add-on no válido")

    return value


def changed(message, extra=None):
    out = {"ok": True, "message": message, "running": running()}
    out.update(extra or {})
    return out


# Propiedad de Bedrock: obliga a los jugadores a bajar los paquetes de
# recursos del mundo para entrar (si no, el juego les pregunta)
TEXTURES_KEY = "texturepack-required"


def set_textures_required(data, user):
    # Antes del primer arranque se crea completo (ver properties.ensure_properties)
    store()
    on = bool(data.get("required"))
    path = ensure_properties()

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    # La 2.5 escribia por error "texturepacks-required": se quita
    lines = [line for line in lines if not line.startswith("texturepacks-required=")]
    entry = TEXTURES_KEY + "=" + ("true" if on else "false")

    for i, line in enumerate(lines):
        if line.startswith(TEXTURES_KEY + "="):
            lines[i] = entry
            break
    else:
        lines.append(entry)

    tmp = path + ".tmp-panel"

    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        os.chown(tmp, core.MC_UID, core.MC_GID)
    except OSError:
        pass

    os.replace(tmp, path)
    log_server_action(S(), "%s %s los paquetes de recursos obligatorios" % (
        user["username"], "activó" if on else "desactivó"))
    return changed("Ajuste guardado")


def install_file(path, user, source=None, group=""):
    addons = store()

    try:
        installed = addons.install(path, source, group)
    except PackError as error:
        raise FileError(str(error))

    log_server_action(S(), "%s instaló el add-on %s" % (
        user["username"], ", ".join(item["name"] for item in installed)))

    return changed("Add-on instalado", {"installed": installed})


def upload_addon(handler, name, length, user):
    name = os.path.basename(str(name or ""))

    # Un .mcworld es un mapa: va a la lista de mundos
    if name.lower().endswith(".mcworld"):
        from .worlds import upload_world
        store()
        return upload_world(handler, name, length, user)

    if not name.lower().endswith(CF_FILE_TYPES):
        raise FileError("Sube un archivo .mcaddon, .mcpack, .mcworld o .zip")

    if length <= 0 or length > MAX_UPLOAD:
        raise FileError("El archivo es demasiado grande", 413)

    fd, tmp = tempfile.mkstemp(prefix="mcpanel-addon-", suffix=".zip")
    remaining = length

    try:
        with os.fdopen(fd, "wb") as f:
            while remaining > 0:
                chunk = handler.rfile.read(min(1024 * 1024, remaining))

                if not chunk:
                    raise FileError("La subida se interrumpió")

                f.write(chunk)
                remaining -= len(chunk)

        return install_file(tmp, user, {"provider": "upload", "file": name[:120]})
    finally:
        os.remove(tmp)


def toggle_addon(data, user):
    uuid = check_uuid(data.get("uuid"))
    on = bool(data.get("enabled"))

    try:
        item = store().set_enabled(uuid, on)
    except PackError as error:
        raise FileError(str(error))

    log_server_action(S(), "%s %s el add-on %s" % (user["username"], "activó" if on else "desactivó", item["name"]))
    return changed("Add-on activado" if on else "Add-on desactivado")


def remove_addon(data, user):
    uuids = data.get("uuids")

    if not isinstance(uuids, list) or not uuids:
        raise FileError("Petición no válida")

    addons = store()
    names = []

    for value in uuids[:100]:
        try:
            names.append(addons.remove(check_uuid(value))["name"])
        except PackError:
            continue

    log_server_action(S(), "%s quitó los add-ons %s" % (user["username"], ", ".join(names)))
    return changed("Add-ons quitados", {"removed": len(names)})


def addon_icon(uuid):
    path = store().icon_path(check_uuid(uuid))

    if not path or os.path.getsize(path) > 2 * 1024 ** 2:
        raise FileError("No encontrado", 404)

    with open(path, "rb") as f:
        return f.read()


# ============================================================
# CurseForge (Minecraft Bedrock): todo es gratis
# ============================================================

def cf_categories():
    # Clases de Bedrock en CurseForge (add-ons, texturas, mapas...) y la
    # categoria de shaders (dentro de texturas). Se buscan por nombre.
    def producer():
        found = {"classes": {}, "shaders": None}

        for item in cf_get("/categories", {"gameId": CF_GAME}).get("data", []):
            slug = str(item.get("slug", ""))

            if item.get("isClass"):
                found["classes"][slug] = item["id"]
            elif "shader" in slug and item.get("classId") == CF_CLASS["textures"]:
                found["shaders"] = item["id"]

        return found

    return cached("cf-bedrock-categories", producer)


def cf_filter(kind):
    # (classId, categoryId) de cada tipo de busqueda
    if kind in CF_CLASS:
        return CF_CLASS[kind], None

    info = cf_categories()

    if kind == "shaders" and info["shaders"]:
        return CF_CLASS["textures"], info["shaders"]

    if kind == "maps":
        for slug in ("maps", "worlds", "mcworld"):
            if slug in info["classes"]:
                return info["classes"][slug], None

    raise FileError("Búsqueda no válida")


def cf_addon_search(kind, query, page=0, sort=""):
    class_id, category = cf_filter(kind)

    # CurseForge no deja pasar del resultado 10 000
    page = min(page_number(page), 10000 // SEARCH_PAGE - 1)
    params = {
        "gameId": CF_GAME,
        "classId": class_id,
        "searchFilter": str(query or "")[:80],
        "sortField": CF_SORT.get(sort, 2),
        "sortOrder": "desc",
        "pageSize": SEARCH_PAGE,
        "index": page * SEARCH_PAGE
    }

    if category:
        params["categoryId"] = category

    data = cf_get("/mods/search", params)

    results = []

    for mod in data.get("data", []):
        results.append({
            "id": mod.get("id"),
            "slug": mod.get("slug", ""),
            "name": mod.get("name", ""),
            "summary": (mod.get("summary") or "")[:200],
            "downloads": mod.get("downloadCount", 0),
            "icon": (mod.get("logo") or {}).get("thumbnailUrl", ""),
            "author": ", ".join(a.get("name", "") for a in mod.get("authors", [])[:2]),
            "url": (mod.get("links") or {}).get("websiteUrl", ""),
            # Algunos autores solo dejan descargarlo desde su pagina
            "downloadable": mod.get("allowModDistribution") is not False
        })

    total = min(int((data.get("pagination") or {}).get("totalCount") or 0), 10000)
    return {"results": results, "page": page, "pages": max(1, -(-total // SEARCH_PAGE)), "total": total}


def cf_release(project_id, types=CF_FILE_TYPES):
    # Los archivos de la version mas reciente: un .mcaddon, o los .mcpack
    # (comportamiento y recursos) que el autor subio juntos
    files = cf_get("/mods/%d/files" % project_id, {"pageSize": 50}).get("data", [])
    files = [f for f in files if str(f.get("fileName", "")).lower().endswith(types)
             and f.get("isAvailable", True) is not False]

    if not files:
        raise FileError("Ese add-on no tiene archivos para descargar")

    files.sort(key=lambda f: f.get("fileDate", ""), reverse=True)
    newest = files[0]

    if newest["fileName"].lower().endswith(".mcaddon"):
        return [newest]

    # Mismo lanzamiento: subidos con menos de una hora de diferencia
    def stamp(item):
        try:
            return datetime.datetime.fromisoformat(item.get("fileDate", "").replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0

    batch = [f for f in files if abs(stamp(f) - stamp(newest)) < 3600
             and not f["fileName"].lower().endswith(".mcaddon")]
    return batch[:4] or [newest]


def cf_install(data, user):
    try:
        project_id = int(data.get("id"))
    except (TypeError, ValueError):
        raise FileError("Add-on no válido")

    store()
    project = cf_get("/mods/%d" % project_id, {}).get("data") or {}

    if project.get("gameId") != CF_GAME:
        raise FileError("Ese proyecto no es de Minecraft Bedrock")

    name = project.get("name", "")
    url = (project.get("links") or {}).get("websiteUrl", "")

    # Un mapa es un mundo: se agrega a la lista de mundos (pestana Mundo)
    if project.get("classId") not in (CF_CLASS["addons"], CF_CLASS["textures"]):
        return cf_install_world(project_id, name, url, user)

    files = cf_release(project_id)
    installed = []

    for item in files:
        link = item.get("downloadUrl")

        if not link:
            raise FileError("El autor solo permite descargarlo desde su página: " + url)

        if int(item.get("fileLength") or 0) > MAX_UPLOAD:
            raise FileError("El add-on es demasiado grande")

        fd, tmp = tempfile.mkstemp(prefix="mcpanel-addon-", suffix=".zip")

        try:
            with os.fdopen(fd, "wb") as f:
                f.write(fetch_url(link.replace(" ", "%20"), timeout=120))

            source = {"provider": "curseforge", "id": project_id, "file": item.get("id"),
                      "file_name": item.get("fileName", "")[:120], "url": url}
            installed += install_file(tmp, user, source, name)["installed"]
        except FileError:
            raise
        except Exception as error:
            raise FileError("No se pudo descargar de CurseForge: %s" % str(error)[:120])
        finally:
            os.remove(tmp)

    return changed("Add-on instalado", {"installed": installed})


def cf_install_world(project_id, name, url, user):
    from .worlds import import_archive

    newest = cf_release(project_id, WORLD_FILE_TYPES)[0]
    link = newest.get("downloadUrl")

    if not link:
        raise FileError("El autor solo permite descargarlo desde su página: " + url)

    if int(newest.get("fileLength") or 0) > MAX_UPLOAD:
        raise FileError("El mapa es demasiado grande")

    fd, tmp = tempfile.mkstemp(prefix="mcpanel-map-", suffix=".zip")

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(fetch_url(link.replace(" ", "%20"), timeout=180))

        result = import_archive(tmp, name, user)
    except FileError:
        raise
    except Exception as error:
        raise FileError("No se pudo descargar de CurseForge: %s" % str(error)[:120])
    finally:
        os.remove(tmp)

    return changed("Mapa agregado", {"world": result["id"]})
