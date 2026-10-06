#
# MCServer by Derpchees - Java portatil (Windows)
#
# Cada version de Minecraft pide su Java (8, 17, 21, 25). Se descarga una
# vez de Adoptium (Eclipse Temurin, gratis) a la carpeta java\<version>
# de la instalacion; no se instala nada en el sistema.
#

import os
import platform
import shutil
import threading
import zipfile

import mcpanel_core as core

from . import fetch

SUPPORTED = (8, 11, 17, 21, 25)
ADOPTIUM = "https://api.adoptium.net/v3/binary/latest/%d/ga/windows/%s/jre/hotspot/normal/eclipse"

_lock = threading.Lock()


def java_root():
    return core.cfg("JAVA_DIR", core.default_path("/opt/mcpanel/java", "java"))


def pick(major):
    # La version publicada mas cercana (por ejemplo 16 -> 17)
    for candidate in SUPPORTED:
        if candidate >= major:
            return candidate

    return SUPPORTED[-1]


def find_java(folder):
    for root, _, files in os.walk(folder):
        if "java.exe" in files and os.path.basename(root) == "bin":
            return os.path.join(root, "java.exe")

    return None


def ensure(major):
    # Ruta de java.exe; la descarga si hace falta
    major = pick(int(major))
    folder = os.path.join(java_root(), str(major))

    with _lock:
        found = find_java(folder) if os.path.isdir(folder) else None

        if found:
            return found

        arch = "aarch64" if platform.machine().upper() in ("ARM64", "AARCH64") else "x64"
        archive = os.path.join(java_root(), "java%d.zip" % major)
        tmp = folder + ".tmp"

        fetch.download(ADOPTIUM % (major, arch), archive)
        shutil.rmtree(tmp, ignore_errors=True)

        try:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(tmp)

            shutil.rmtree(folder, ignore_errors=True)
            os.replace(tmp, folder)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

            try:
                os.remove(archive)
            except OSError:
                pass

        found = find_java(folder)

        if not found:
            raise RuntimeError("No se encontró Java %d después de descargarlo" % major)

        return found
