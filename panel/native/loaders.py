#
# MCServer by Derpchees - instalar el servidor de Java de cada tipo (Windows)
#
# Lo que la imagen de Docker hace sola: bajar el server.jar oficial, Paper,
# el lanzador de Fabric o correr el instalador de Forge/NeoForge. Devuelve
# lo que va despues de "java <memoria>" para arrancarlo. Lo instalado se
# anota en .mcpanel/install.json y no se repite si nada cambio.
#

import json
import os
import re
import subprocess
import urllib.parse

from . import fetch, mojang
from .procs import CREATE_NO_WINDOW

MARK = os.path.join(".mcpanel", "install.json")


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


def resolve_loader(type_, mc, loader):
    # Version del cargador: la elegida o la recomendada para esa version
    if loader:
        return loader

    from webpanel import versions

    if type_ == "FABRIC":
        found = versions.fabric_loaders()["recommended"]
    elif type_ == "FORGE":
        found = versions.forge_builds(mc)["recommended"]
    elif type_ == "NEOFORGE":
        found = versions.neoforge_builds(mc)["recommended"]
    elif type_ == "PAPER":
        found = str(fetch.get_json("https://fill.papermc.io/v3/projects/paper/versions/%s/builds/latest"
                                   % urllib.parse.quote(mc))["id"])
    else:
        return ""

    if not found:
        raise RuntimeError("No hay %s para Minecraft %s" % (type_.title(), mc))

    return found


def install(data_dir, type_, mc, loader, java_exe, log):
    # Devuelve los argumentos para java (sin la memoria)
    loader = resolve_loader(type_, mc, loader)
    wanted = {"type": type_, "mc": mc, "loader": loader}
    mark = read_mark(data_dir)

    if mark.get("launch") and all(mark.get(k) == v for k, v in wanted.items()) \
            and launch_ready(data_dir, mark["launch"]):
        return mark["launch"]

    log("Instalando %s %s%s" % (type_.title(), mc, " (" + loader + ")" if loader else ""))

    if type_ == "VANILLA":
        launch = vanilla(data_dir, mc)
    elif type_ == "PAPER":
        launch = paper(data_dir, mc, loader)
    elif type_ == "FABRIC":
        launch = fabric(data_dir, mc, loader)
    elif type_ == "FORGE":
        url = ("https://maven.minecraftforge.net/net/minecraftforge/forge/%s-%s/forge-%s-%s-installer.jar"
               % (mc, loader, mc, loader))
        launch = run_installer(data_dir, url, java_exe, log, ("forge-%s-%s" % (mc, loader),))
    elif type_ == "NEOFORGE":
        url = ("https://maven.neoforged.net/releases/net/neoforged/neoforge/%s/neoforge-%s-installer.jar"
               % (loader, loader))
        launch = run_installer(data_dir, url, java_exe, log, ("neoforge-%s" % loader,))
    else:
        raise RuntimeError("Tipo de servidor no disponible en Windows: " + type_)

    write_mark(data_dir, dict(wanted, launch=launch))
    log("Instalado")
    return launch


def launch_ready(data_dir, launch):
    # El archivo con que arranca sigue ahi (por si se borro desde Archivos)
    for arg in launch:
        if arg.startswith("@"):
            return os.path.isfile(os.path.join(data_dir, arg[1:]))

        if arg.endswith(".jar"):
            return os.path.isfile(os.path.join(data_dir, arg))

    return False


def vanilla(data_dir, mc):
    url, sha1 = mojang.server_download(mc)
    fetch.download(url, os.path.join(data_dir, "server.jar"), {"sha1": sha1})
    return ["-jar", "server.jar", "nogui"]


def paper(data_dir, mc, build):
    info = fetch.get_json("https://fill.papermc.io/v3/projects/paper/versions/%s/builds/%s"
                          % (urllib.parse.quote(mc), urllib.parse.quote(build)))
    download = info["downloads"]["server:default"]
    name = re.sub(r"[^0-9A-Za-z._-]", "_", download["name"])

    # Las versiones anteriores de Paper ya no hacen falta
    for old in os.listdir(data_dir):
        if old.startswith("paper-") and old.endswith(".jar") and old != name:
            os.remove(os.path.join(data_dir, old))

    fetch.download(download["url"], os.path.join(data_dir, name), {"sha256": download["checksums"]["sha256"]})
    return ["-jar", name, "nogui"]


def fabric(data_dir, mc, loader):
    installers = fetch.get_json("https://meta.fabricmc.net/v2/versions/installer")
    installer = next((i["version"] for i in installers if i.get("stable")), installers[0]["version"])
    url = "https://meta.fabricmc.net/v2/versions/loader/%s/%s/%s/server/jar" % (
        urllib.parse.quote(mc), urllib.parse.quote(loader), urllib.parse.quote(installer))
    fetch.download(url, os.path.join(data_dir, "fabric-server-launch.jar"))
    return ["-jar", "fabric-server-launch.jar", "nogui"]


def run_installer(data_dir, url, java_exe, log, names):
    # Forge y NeoForge traen su instalador: baja librerias y deja un run.bat
    installer = os.path.join(data_dir, "mcpanel-installer.jar")
    fetch.download(url, installer)

    try:
        os.remove(os.path.join(data_dir, "run.bat"))
    except OSError:
        pass

    try:
        process = subprocess.Popen([java_exe, "-jar", installer, "--installServer"], cwd=data_dir,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   creationflags=CREATE_NO_WINDOW)

        for raw in iter(process.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").strip()

            # Solo lo importante: el instalador escribe una linea por archivo
            if line and not line.startswith(("Downloading", "  ", "Considering", "File exists")):
                log(line[:300])

        if process.wait() != 0:
            raise RuntimeError("El instalador terminó con error (código %d)" % process.returncode)
    finally:
        for leftover in (installer, installer + ".log", os.path.join(data_dir, "installer.log")):
            try:
                os.remove(leftover)
            except OSError:
                pass

    launch = launch_from_runbat(data_dir)

    if launch:
        return launch

    # Versiones viejas: un jar propio en la carpeta
    for name in sorted(os.listdir(data_dir)):
        if name.endswith(".jar") and name.startswith(names) and "installer" not in name:
            return ["-jar", name, "nogui"]

    raise RuntimeError("No se encontró cómo arrancar el servidor instalado")


def launch_from_runbat(data_dir):
    # run.bat: "java @user_jvm_args.txt @libraries/.../win_args.txt %*"
    try:
        with open(os.path.join(data_dir, "run.bat"), "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return None

    for line in reversed(lines):
        parts = line.strip().split()

        if not parts or parts[0].lower() not in ("java", '"java"') or "--onlyCheckJava" in parts:
            continue

        args = [p for p in parts[1:] if p not in ("%*", "@user_jvm_args.txt") and not p.startswith("||")]
        args = args[:args.index("||")] if "||" in args else args

        if args:
            return args + ["nogui"]

    return None
