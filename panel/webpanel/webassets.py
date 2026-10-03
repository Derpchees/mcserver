#
# MCServer by Derpchees - Pagina web: index.html, y app.css y app.js armados desde web/
#

import os
import html

import mcpanel_core as core

from .common import DEFAULT_LANG, INSTALL_DIR


try:
    with open(os.path.join(INSTALL_DIR, "VERSION"), "r") as f:
        APP_VERSION = f.read().strip() or "dev"
except Exception:
    APP_VERSION = "dev"

# La pagina vive en web/: index.html, y css/ y js/ partidos en archivos
# numerados que se unen en orden en un solo app.css y un solo app.js
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

# Con MCPANEL_DEV=1 se releen en cada peticion (para editar sin reiniciar)
WEB_DEV = os.environ.get("MCPANEL_DEV") == "1"


def fill_values(text):
    # Valores de la instalacion insertados en la pagina
    return (
        text
        .replace("__SYSTEM_NAME__", html.escape(core.SYSTEM_NAME))
        .replace("__DEFAULT_LANG__", "es" if DEFAULT_LANG == "es" else "en")
        .replace("__VERSION__", html.escape(APP_VERSION))
    )


def bundle(folder, extension):
    path = os.path.join(WEB_DIR, folder)
    parts = []

    for name in sorted(os.listdir(path)):
        if name.endswith(extension):
            with open(os.path.join(path, name), "r", encoding="utf-8") as f:
                parts.append(f.read())

    return "\n".join(parts)


def build_web():
    with open(os.path.join(WEB_DIR, "index.html"), "r", encoding="utf-8") as f:
        page = f.read()

    return {
        "page": fill_values(page).encode("utf-8"),
        "css": fill_values(bundle("css", ".css")).encode("utf-8"),
        "js": fill_values(bundle("js", ".js")).encode("utf-8")
    }


_web = build_web()


def web(part):
    return (build_web() if WEB_DEV else _web)[part]
