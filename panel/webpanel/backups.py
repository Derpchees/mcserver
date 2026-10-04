#
# MCServer by Derpchees - Respaldos
#

import subprocess
import os
import re
import time
import shlex

import backup_schedule
import mcpanel_core as core

from .common import command, FileError, INSTALL_DIR, read_lines, S
from .stats import _stats, _stats_lock


BACKUP_NAME = re.compile(r"^mc-(auto|manual)-(\d{8}-\d{6})\.tar\.gz$")


def backup_running():
    # Los respaldos corren como unidades transitorias mcpanel-backup-<slug>-<ts>
    output = command(
        "systemctl list-units --type=service --state=active --no-legend --plain "
        + shlex.quote("mcpanel-backup-%s-*" % S().slug)
    )
    return bool(output.strip())


def next_backup_ts():
    # Con el estado actual: encendido y apagado tienen su propio intervalo
    running = core.container_state(S())[0] == "running"
    target = backup_schedule.next_run(S(), running)
    return int(target) if target else None


def list_backups():
    backups = []

    if os.path.isdir(S().backup_dir):
        for name in os.listdir(S().backup_dir):
            m = BACKUP_NAME.match(name)

            if not m:
                continue

            st = os.stat(os.path.join(S().backup_dir, name))

            backups.append({
                "name": name,
                "type": m.group(1),
                "size": st.st_size,
                "mtime": int(st.st_mtime)
            })

    backups.sort(key=lambda b: b["mtime"], reverse=True)

    # Mantiene al dia la grafica de almacenamiento sin esperar al du
    with _stats_lock:
        _stats["sizes"].setdefault(S().slug, {})["backups"] = sum(b["size"] for b in backups)

    next_ts = next_backup_ts()

    log_lines = read_lines(os.path.join(S().log_dir, "backup.log"))

    return {
        "running": backup_running(),
        "next_auto": next_ts,
        "last_log": log_lines[-1] if log_lines else "",
        "backups": backups
    }


def start_backup():
    if backup_running():
        raise FileError("Ya hay un respaldo en curso")

    if not core.path_available(S().backup_dir):
        raise FileError("El disco de respaldos no está conectado")

    S().write_env()

    result = subprocess.run(
        ["systemd-run", "--unit", "mcpanel-backup-%s-%d" % (S().slug, int(time.time())),
         "--collect", "--quiet", "--nice=10",
         os.path.join(INSTALL_DIR, "bin", "mcpanel-backup.sh"), S().slug, "manual"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise FileError("No se pudo iniciar el respaldo: " + result.stderr.strip(), 500)

    return {"ok": True, "message": "Respaldo iniciado"}


def backup_path(name):
    if not BACKUP_NAME.match(name or ""):
        raise FileError("Respaldo no válido", 404)

    full = os.path.join(S().backup_dir, name)

    if not os.path.isfile(full):
        raise FileError("El respaldo no existe", 404)

    return full


def delete_backup(name):
    os.remove(backup_path(name))
    return {"ok": True, "message": "Respaldo eliminado"}
