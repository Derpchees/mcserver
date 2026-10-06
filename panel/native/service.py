#
# MCServer by Derpchees - servicio de Windows
#
#   pythonw service.py
#
# Lo arranca el Programador de tareas al encender el equipo (tarea
# "MCServer", como SYSTEM). Corre el panel web y el agente, y los vuelve a
# abrir si se cierran (lo que hace systemd en Linux). Los servidores de
# Minecraft no dependen de esto: siguen vivos si se reinicia.
#

import os
import subprocess
import sys
import time

PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PANEL_DIR)

import mcpanel_core as core  # noqa: E402
from native.procs import CREATE_NO_WINDOW  # noqa: E402

PROGRAMS = {"web": "mcpanel.py", "agent": "mcpanel-agent.py"}
LOG_LIMIT = 10 * 1024 * 1024


def open_log(name):
    os.makedirs(core.LOG_ROOT, exist_ok=True)
    path = os.path.join(core.LOG_ROOT, name + ".log")

    try:
        if os.path.getsize(path) > LOG_LIMIT:
            os.replace(path, path + ".1")
    except OSError:
        pass

    return open(path, "a", encoding="utf-8")


def launch(name):
    log = open_log(name)
    log.write("%s | INICIO\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
    log.flush()

    return subprocess.Popen([sys.executable, "-u", os.path.join(PANEL_DIR, PROGRAMS[name])],
                            cwd=PANEL_DIR, stdout=log, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)


def main():
    children = {}
    failures = {}

    while True:
        for name in PROGRAMS:
            child = children.get(name)

            if child and child.poll() is None:
                continue

            # Si falla seguido se espera un poco mas antes de reintentar
            if child:
                failures[name] = failures.get(name, 0) + 1
                time.sleep(min(30, 2 * failures[name]))

            children[name] = launch(name)

        time.sleep(3)

        for name, child in children.items():
            if child.poll() is None and failures.get(name):
                failures[name] = 0


if __name__ == "__main__":
    main()
