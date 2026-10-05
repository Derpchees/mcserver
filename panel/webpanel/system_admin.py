#
# MCServer by Derpchees - Acceso seguro y actualizaciones (administracion)
#
# Ver el estado lo puede cualquier administrador; cambiarlo solo el dueno
# del sistema.
#

from sysadmin import https, update
from sysadmin.tasks import TaskError

from .common import FileError
from .access import is_owner


def system_get(path, force=False):
    if path == "/admin/https":
        return https.status()

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
            return https.enable(data.get("subdomain"), data.get("token"), bool(data.get("game_address")))

        if path == "/admin/https/disable":
            return https.disable()

        if path == "/admin/update/start":
            return update.start_update()
    except TaskError as error:
        raise FileError(str(error))

    raise FileError("No encontrado", 404)
