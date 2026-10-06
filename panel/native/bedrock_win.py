#
# MCServer by Derpchees - servidor de Bedrock para Windows
#
# Mojang publica bedrock_server.exe en un zip. Se descomprime en la carpeta
# del servidor sin pisar los ajustes ni las listas (lo mismo que hace la
# imagen de Docker en Linux); los mundos no vienen en el zip.
#

import json
import os
import re
import zipfile

from . import fetch

LINKS = "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
VERSION_URL = "https://www.minecraft.net/bedrockdedicatedserver/bin-win/bedrock-server-%s.zip"
MARK = os.path.join(".mcpanel", "install.json")

# Lo que la persona ya cambio no se reemplaza al actualizar
KEEP = ("server.properties", "permissions.json", "allowlist.json", "whitelist.json")


def latest_url():
    for link in fetch.get_json(LINKS)["result"]["links"]:
        if link.get("downloadType") == "serverBedrockWindows":
            return link["downloadUrl"]

    raise RuntimeError("No se encontró la descarga de Bedrock para Windows")


def install(data_dir, version, log):
    if not version or version.upper() in ("LATEST", "PREVIEW"):
        url = latest_url()
    else:
        url = VERSION_URL % version

    exact = re.search(r"bedrock-server-([0-9.]+)\.zip", url).group(1)
    mark_path = os.path.join(data_dir, MARK)

    try:
        with open(mark_path, "r", encoding="utf-8") as f:
            mark = json.load(f)
    except (OSError, ValueError):
        mark = {}

    exe = os.path.join(data_dir, "bedrock_server.exe")

    if mark.get("version") == exact and os.path.isfile(exe):
        return exact

    log("Instalando Bedrock " + exact)
    archive = os.path.join(data_dir, ".mcpanel", "bedrock.zip")
    fetch.download(url, archive)

    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            dest = os.path.normpath(os.path.join(data_dir, name))

            if not dest.startswith(os.path.normpath(data_dir) + os.sep):
                continue

            if name in KEEP and os.path.exists(dest):
                continue

            if info.is_dir():
                os.makedirs(dest, exist_ok=True)
                continue

            os.makedirs(os.path.dirname(dest), exist_ok=True)

            with zf.open(info) as src, open(dest, "wb") as out:
                out.write(src.read())

    os.remove(archive)
    os.makedirs(os.path.dirname(mark_path), exist_ok=True)

    with open(mark_path, "w", encoding="utf-8") as f:
        json.dump({"type": "BEDROCK", "version": exact}, f)

    log("Instalado")
    return exact
