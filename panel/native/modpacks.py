#
# MCServer by Derpchees - modpacks sin Docker (Windows)
#
# Modrinth (.mrpack) y CurseForge (zip con manifest.json): baja los mods
# que corren en el servidor, copia sus archivos de configuracion y dice
# que cargador y version de Minecraft necesita. Lo que bajo se anota en
# .mcpanel/modpack.json para cambiar de version limpio.
#

import json
import os
import re
import shutil
import urllib.parse
import zipfile

from . import fetch

MARK = os.path.join(".mcpanel", "modpack.json")
MODRINTH = "https://api.modrinth.com/v2"
CURSEFORGE = "https://api.curseforge.com/v1"

# Dependencia del modpack -> tipo de servidor
MRPACK_LOADERS = {"fabric-loader": "FABRIC", "forge": "FORGE", "neoforge": "NEOFORGE"}

CF_CLASS_MODS = 6


def read_mark(data_dir):
    try:
        with open(os.path.join(data_dir, MARK), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_mark(data_dir, values):
    path = os.path.join(data_dir, MARK)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(values, f, indent=2)


def safe_path(data_dir, relative):
    # Nunca fuera de la carpeta del servidor
    relative = relative.replace("\\", "/").lstrip("/")
    full = os.path.normpath(os.path.join(data_dir, relative))

    if not full.startswith(os.path.normpath(data_dir) + os.sep):
        raise RuntimeError("Ruta no válida en el modpack: " + relative)

    return full


def remove_old(data_dir, old_files, new_files):
    for relative in set(old_files) - set(new_files):
        try:
            os.remove(safe_path(data_dir, relative))
        except (OSError, RuntimeError):
            pass


def extract_folder(zf, prefix, data_dir):
    # Copia los archivos de una carpeta del zip (overrides/) al servidor
    for info in zf.infolist():
        if info.is_dir() or not info.filename.startswith(prefix):
            continue

        relative = info.filename[len(prefix):]

        if not relative:
            continue

        dest = safe_path(data_dir, relative)
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        with zf.open(info) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)


# ============================================================
# Modrinth
# ============================================================

def modrinth(data_dir, slug, version_id, log):
    # Devuelve (tipo, minecraft, cargador)
    if version_id:
        version = fetch.get_json("%s/version/%s" % (MODRINTH, urllib.parse.quote(version_id)))
    else:
        versions = fetch.get_json("%s/project/%s/version" % (MODRINTH, urllib.parse.quote(slug)))
        stable = [v for v in versions if v.get("version_type") == "release"]
        version = (stable or versions or [None])[0]

    if not version:
        raise RuntimeError("El modpack %s no tiene versiones" % slug)

    mark = read_mark(data_dir)

    if mark.get("provider") == "modrinth" and mark.get("version") == version["id"]:
        return mark["type"], mark["mc"], mark["loader"]

    file = next((f for f in version["files"] if f.get("primary")), version["files"][0])
    archive = os.path.join(data_dir, ".mcpanel", "modpack.mrpack")
    log("Descargando el modpack %s %s" % (slug, version.get("version_number", "")))
    fetch.download(file["url"], archive, {"sha512": (file.get("hashes") or {}).get("sha512")})

    with zipfile.ZipFile(archive) as zf:
        index = json.loads(zf.read("modrinth.index.json"))
        deps = index.get("dependencies") or {}
        type_ = next((t for key, t in MRPACK_LOADERS.items() if key in deps), None)

        if not type_:
            raise RuntimeError("Este modpack usa un cargador que no está disponible en Windows")

        loader = deps[next(k for k, t in MRPACK_LOADERS.items() if t == type_)]
        files = []

        for item in index.get("files") or []:
            if (item.get("env") or {}).get("server") == "unsupported":
                continue

            files.append(item["path"])
            dest = safe_path(data_dir, item["path"])

            if not os.path.isfile(dest):
                log("Descargando " + os.path.basename(dest))
                fetch.download(item["downloads"][0], dest, {"sha512": (item.get("hashes") or {}).get("sha512")})

        remove_old(data_dir, mark.get("files") or [], files)
        extract_folder(zf, "overrides/", data_dir)
        extract_folder(zf, "server-overrides/", data_dir)

    os.remove(archive)
    write_mark(data_dir, {"provider": "modrinth", "slug": slug, "version": version["id"],
                          "type": type_, "mc": deps["minecraft"], "loader": loader, "files": files})
    return type_, deps["minecraft"], loader


# ============================================================
# CurseForge
# ============================================================

def cf(path, key, data=None):
    return fetch.get_json(CURSEFORGE + path, headers={"x-api-key": key, "Accept": "application/json"}, data=data)


def cf_download_url(file):
    # Algunos autores no dejan descargar por la API: el archivo sigue en su CDN
    if file.get("downloadUrl"):
        return file["downloadUrl"]

    file_id = int(file["id"])
    return "https://edge.forgecdn.net/files/%d/%d/%s" % (file_id // 1000, file_id % 1000,
                                                          urllib.parse.quote(file["fileName"]))


def curseforge(data_dir, slug, file_id, key, log):
    if not key:
        raise RuntimeError("Falta la clave de API de CurseForge (Administración)")

    found = cf("/mods/search?" + urllib.parse.urlencode({"gameId": 432, "classId": 4471, "slug": slug}), key)["data"]

    if not found:
        raise RuntimeError("No se encontró el modpack " + slug)

    mod_id = found[0]["id"]

    if file_id:
        pack = cf("/mods/%d/files/%s" % (mod_id, urllib.parse.quote(str(file_id))), key)["data"]
    else:
        files = cf("/mods/%d/files?pageSize=50" % mod_id, key)["data"]
        files = sorted((f for f in files if not f.get("isServerPack")), key=lambda f: f["fileDate"], reverse=True)
        pack = next((f for f in files if f.get("releaseType") == 1), files[0] if files else None)

    if not pack:
        raise RuntimeError("El modpack %s no tiene archivos" % slug)

    mark = read_mark(data_dir)

    if mark.get("provider") == "curseforge" and str(mark.get("version")) == str(pack["id"]):
        return mark["type"], mark["mc"], mark["loader"]

    archive = os.path.join(data_dir, ".mcpanel", "modpack.zip")
    log("Descargando el modpack %s (%s)" % (slug, pack.get("displayName", "")))
    fetch.download(cf_download_url(pack), archive)

    with zipfile.ZipFile(archive) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        mc = manifest["minecraft"]["version"]
        loaders = manifest["minecraft"].get("modLoaders") or []
        primary = next((l["id"] for l in loaders if l.get("primary")), loaders[0]["id"] if loaders else "")
        name, _, loader = primary.partition("-")
        type_ = {"forge": "FORGE", "neoforge": "NEOFORGE", "fabric": "FABRIC"}.get(name)

        if not type_:
            raise RuntimeError("Este modpack usa un cargador que no está disponible en Windows")

        # NeoForge de la 1.20.1 se anota como "neoforge-1.20.1-47.1.x"
        loader = re.sub(r"^%s-" % re.escape(mc), "", loader)
        wanted = [f["fileID"] for f in manifest.get("files") or [] if f.get("required", True)]
        files = []

        for start in range(0, len(wanted), 200):
            chunk = wanted[start:start + 200]
            infos = cf("/mods/files", key, {"fileIds": chunk})["data"]
            classes = {m["id"]: m.get("classId") for m in
                       cf("/mods", key, {"modIds": sorted({i["modId"] for i in infos})})["data"]}

            for info in infos:
                tags = set(info.get("gameVersions") or [])

                # Solo mods (no texturas ni shaders) y que no sean solo del cliente
                if classes.get(info["modId"]) != CF_CLASS_MODS or ("Client" in tags and "Server" not in tags):
                    continue

                relative = "mods/" + re.sub(r'[\\/:*?"<>|]', "_", info["fileName"])
                files.append(relative)
                dest = safe_path(data_dir, relative)

                if not os.path.isfile(dest):
                    log("Descargando " + info["fileName"])
                    fetch.download(cf_download_url(info), dest)

        remove_old(data_dir, mark.get("files") or [], files)
        extract_folder(zf, (manifest.get("overrides") or "overrides").strip("/") + "/", data_dir)

    os.remove(archive)
    write_mark(data_dir, {"provider": "curseforge", "slug": slug, "version": pack["id"],
                          "type": type_, "mc": mc, "loader": loader, "files": files})
    return type_, mc, loader
