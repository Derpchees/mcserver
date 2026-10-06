#
# MCServer by Derpchees - Almacenamiento (administracion)
#
# Ver y cambiar donde viven los servidores y los respaldos. Ver lo puede
# cualquier administrador; cambiarlo solo el dueno del sistema.
#

import mcpanel_core as core

from storage import rebuild, relocate, status
from storage.options import storage_options
from storage.system import StorageError

from .common import FileError
from .access import is_owner


WINDOWS_ONLY = "En Windows los servidores y respaldos viven en la carpeta de instalación"


def storage_get():
    # Discos, particiones y LVM son de Linux
    if core.WINDOWS:
        raise FileError(WINDOWS_ONLY)

    return status.storage_status()


def storage_options_for(role):
    if role not in status.ROLES:
        raise FileError("Ubicación no válida")

    return storage_options(role)


def storage_action(user, path, data):
    if not is_owner(user):
        raise FileError("Solo el dueño del sistema puede cambiar el almacenamiento", 403)

    if core.WINDOWS:
        raise FileError(WINDOWS_ONLY)

    try:
        if path == "/admin/storage/relocate" and data.get("kind") == "rebuild":
            if data.get("role") != "backups":
                raise FileError("Solo se puede rehacer un disco para los respaldos")
            return rebuild.rebuild(str(data.get("target", "")), data.get("size_gb") or 0,
                                   str(data.get("extra_name") or ""))

        if path == "/admin/storage/relocate":
            start = data.get("start")
            return relocate.relocate(
                str(data.get("role", "")), str(data.get("kind", "")), str(data.get("target", "")),
                size_gb=data.get("size_gb") or 0, existing=str(data.get("existing", "move")),
                start=int(start) if start is not None else None,
                extra_name=str(data.get("extra_name") or "")
            )

        if path == "/admin/storage/grow":
            return relocate.grow(str(data.get("role", "")), data.get("size_gb") or 0)

        if path == "/admin/storage/backups":
            return relocate.set_backups_paused(bool(data.get("paused")))
    except (StorageError, ValueError) as error:
        raise FileError(str(error))

    raise FileError("No encontrado", 404)


def data_disk_ready():
    # Los servidores no se encienden si falta su disco o se estan moviendo
    if core.get_setting("storage_busy"):
        return "Los servidores se están moviendo de disco. Espera a que termine."

    if not core.path_available(core.data_root()):
        return "El disco de los servidores no está conectado"

    return None


def storage_alert():
    # Resumen para el aviso que ven los administradores en todo el panel
    data_ok = core.path_available(core.data_root())
    backups = status.backups_state({"available": core.path_available(core.backup_root())})

    if data_ok and backups == "ok" and not core.get_setting("storage_busy"):
        return None

    return {"data": data_ok, "backups": backups, "busy": bool(core.get_setting("storage_busy"))}
