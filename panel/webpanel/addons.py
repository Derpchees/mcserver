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

from .common import FileError, fetch_url, log_server_action, S
from .mods import cf_get
from .properties import read_properties


MAX_UPLOAD = 500 * 1024 ** 2
UUID = re.compile(r"^[0-9a-f-]{32,36}$")

CF_GAME = 78022
CF_CLASS = {"addons": 4984, "textures": 6929}
CF_FILE_TYPES = (".mcaddon", ".mcpack", ".zip")


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
        "texturepacks_required": read_properties().get("texturepacks-required", "") == "true",
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


def require_textures():
    # Con paquetes de recursos, que los jugadores los descarguen al entrar.
    # Si el servidor nunca arranco no hay server.properties: no se crea uno
    # a medias (la imagen ya no lo completaria)
    path = os.path.join(S().data_dir, "server.properties")

    if not os.path.isfile(path):
        return

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    for i, line in enumerate(lines):
        if line.startswith("texturepacks-required="):
            if line.strip() == "texturepacks-required=true":
                return
            lines[i] = "texturepacks-required=true"
            break
    else:
        lines.append("texturepacks-required=true")

    tmp = path + ".tmp-panel"

    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        os.chown(tmp, core.MC_UID, core.MC_GID)
    except OSError:
        pass

    os.replace(tmp, path)


def install_file(path, user, source=None, group=""):
    addons = store()

    try:
        installed = addons.install(path, source, group)
    except PackError as error:
        raise FileError(str(error))

    if any(item["kind"] == "resource" for item in installed):
        require_textures()

    log_server_action(S(), "%s instaló el add-on %s" % (
        user["username"], ", ".join(item["name"] for item in installed)))

    return changed("Add-on instalado", {"installed": installed})


def upload_addon(handler, name, length, user):
    name = os.path.basename(str(name or ""))

    if not name.lower().endswith(CF_FILE_TYPES):
        raise FileError("Sube un archivo .mcaddon, .mcpack o .zip")

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

    if on and item["kind"] == "resource":
        require_textures()

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

def cf_addon_search(kind, query):
    if kind not in CF_CLASS:
        raise FileError("Búsqueda no válida")

    data = cf_get("/mods/search", {
        "gameId": CF_GAME,
        "classId": CF_CLASS[kind],
        "searchFilter": str(query or "")[:80],
        "sortField": 2,
        "sortOrder": "desc",
        "pageSize": 30
    })

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

    return {"results": results}


def cf_release(project_id):
    # Los archivos de la version mas reciente: un .mcaddon, o los .mcpack
    # (comportamiento y recursos) que el autor subio juntos
    files = cf_get("/mods/%d/files" % project_id, {"pageSize": 50}).get("data", [])
    files = [f for f in files if str(f.get("fileName", "")).lower().endswith(CF_FILE_TYPES)
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

    files = cf_release(project_id)
    name = project.get("name", "")
    url = (project.get("links") or {}).get("websiteUrl", "")
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
