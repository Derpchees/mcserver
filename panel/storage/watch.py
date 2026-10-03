#
# MCServer by Derpchees - almacenamiento: vigilancia de discos (agente)
#
# Cada pocos segundos revisa que esten montados el disco de los servidores
# y el de los respaldos, y avisa cuando uno se desconecta o vuelve.
#   - Sin disco de servidores: no se encienden servidores y se apagan los
#     encendidos (escribirian en la carpeta vacia del disco del sistema).
#   - Sin disco de respaldos: los respaldos se pausan solos y se reanudan
#     cuando el disco vuelve.
#

import mcpanel_core as core

_last = {}


def data_ready():
    return core.path_available(core.data_root()) and not core.get_setting("storage_busy")


def backups_ready():
    return core.path_available(core.backup_root()) and not core.get_setting("storage_busy")


def check():
    # Devuelve True si el disco de los servidores acaba de desconectarse
    data_ok = core.path_available(core.data_root())
    backups_ok = core.path_available(core.backup_root())
    lost_data = False

    if _last.get("data") is not None and data_ok != _last["data"]:
        if data_ok:
            core.add_event(None, "storage_data_back", "success", core.data_root())
        else:
            core.add_event(None, "storage_data_missing", "error", core.data_root())
            lost_data = True

    if _last.get("backups") is not None and backups_ok != _last["backups"]:
        if backups_ok:
            # Si el administrador los desactivo mientras faltaba el disco, se reanudan
            core.set_setting("backups_paused", "")
            core.add_event(None, "storage_backup_back", "success", core.backup_root())
        else:
            core.add_event(None, "storage_backup_missing", "warning", core.backup_root())

    # Al arrancar el agente sin el disco tambien hay que avisar
    if _last.get("data") is None and not data_ok:
        core.add_event(None, "storage_data_missing", "error", core.data_root())
        lost_data = True

    if _last.get("backups") is None and not backups_ok:
        core.add_event(None, "storage_backup_missing", "warning", core.backup_root())

    _last["data"] = data_ok
    _last["backups"] = backups_ok

    return lost_data
