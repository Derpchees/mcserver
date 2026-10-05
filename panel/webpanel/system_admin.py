#
# MCServer by Derpchees - Acceso seguro y actualizaciones (administracion)
#
# Ver el estado lo puede cualquier administrador; cambiarlo solo el dueno
# del sistema.
#

from sysadmin import localca, update
from sysadmin.localca import CertError
from sysadmin.tasks import TaskError

from .common import FileError
from .access import is_owner


def system_get(path, force=False):
    if path == "/admin/https":
        return localca.status()

    if path == "/admin/update":
        info = update.status(force)
        info["players"] = update.players_online()
        return info

    raise FileError("No encontrado", 404)


def system_action(user, path, data):
    if not is_owner(user):
        raise FileError("Solo el dueño del sistema puede hacer esto", 403)

    try:
        if path == "/admin/https/enable":
            info = localca.enable()
            localca.restart_panel_soon()
            return dict(info, ok=True, message="HTTPS activado")

        if path == "/admin/https/disable":
            localca.disable()
            localca.restart_panel_soon()
            return {"ok": True, "message": "HTTPS desactivado"}

        if path == "/admin/update/start":
            return update.start_update()
    except (TaskError, CertError) as error:
        raise FileError(str(error))

    raise FileError("No encontrado", 404)
