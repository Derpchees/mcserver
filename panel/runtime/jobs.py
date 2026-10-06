#
# MCServer by Derpchees - tareas que corren aparte del panel (respaldos)
#
# Linux: unidades transitorias de systemd con el script de bash. Windows:
# un proceso de Python independiente (native/backup.py).
#

import os
import shlex
import subprocess
import time

import mcpanel_core as core


def start_backup(srv, kind):
    # kind: "auto" o "manual"
    srv.write_env()

    if core.NATIVE:
        from native import procs
        procs.spawn_detached([procs.pythonw(), procs.panel_script("native", "backup.py"), srv.slug, kind])
        return

    result = subprocess.run(
        ["systemd-run", "--unit", "mcpanel-backup-%s-%d" % (srv.slug, int(time.time())),
         "--collect", "--quiet", "--nice=10", core.CONFIG_SETENV,
         os.path.join(core.INSTALL_DIR, "bin", "mcpanel-backup.sh"), srv.slug, kind],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "systemd-run")


def backup_running(srv):
    if core.NATIVE:
        from native import backup
        return backup.running(srv)

    # Los respaldos corren como unidades mcpanel-backup-<slug>-<ts>
    result = subprocess.run(
        "systemctl list-units --type=service --state=active --no-legend --plain "
        + shlex.quote("mcpanel-backup-%s-*" % srv.slug),
        shell=True, capture_output=True, text=True
    )
    return bool(result.stdout.strip())
