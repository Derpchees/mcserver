#
# MCServer by Derpchees - Acceso seguro y actualizaciones (administracion)
#
# Ver el estado lo puede cualquier administrador; cambiarlo solo el dueno
# del sistema. HTTPS tiene dos modos: dominio gratis (DuckDNS + Let's
# Encrypt, recomendado) o CA propia (sin servicios externos).
#

import mcpanel_core as core

from sysadmin import duckdns, localca, update
from sysadmin.localca import CertError
from sysadmin.tasks import TaskError

from .common import FileError
from .access import is_owner


def https_status():
    return {"mode": core.live_cfg("TLS_MODE", ""), "duckdns": duckdns.status(), "local": localca.status()}


def turn_off():
    mode = core.live_cfg("TLS_MODE", "")

    if mode == "duckdns":
        duckdns.disable()
    elif mode == "local":
        localca.disable()


def system_get(path, force=False):
    if path == "/admin/https":
        return https_status()

    if path == "/admin/update":
        info = update.status(force)
        info["players"] = update.players_online()
        return info

    raise FileError("No encontrado", 404)


def system_action(user, path, data):
    if not is_owner(user):
        raise FileError("Solo el dueño del sistema puede hacer esto", 403)

    try:
        if path == "/admin/https/duckdns":
            return duckdns.enable(data.get("subdomain"), data.get("token"), bool(data.get("game_address")))

        if path == "/admin/https/local":
            turn_off()
            info = localca.enable()
            localca.restart_panel_soon()
            return dict(info, ok=True, message="HTTPS activado")

        if path == "/admin/https/disable":
            turn_off()
            localca.restart_panel_soon()
            return {"ok": True, "message": "HTTPS desactivado"}

        if path == "/admin/update/start":
            return update.start_update()
    except (TaskError, CertError) as error:
        raise FileError(str(error))

    raise FileError("No encontrado", 404)
