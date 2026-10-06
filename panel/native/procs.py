#
# MCServer by Derpchees - procesos independientes del panel (Windows)
#
# Los servidores, respaldos y actualizaciones corren aparte: si el panel o
# el agente se reinician (por ejemplo al actualizar), siguen vivos. El
# Programador de tareas mete al panel en un "job" que se cierra con el; los
# procesos nuevos salen de ese job (o se crean con WMI si no se puede).
#

import os
import subprocess
import sys

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000

PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pythonw():
    # El Python sin ventana que viene junto al que corre el panel
    folder = os.path.dirname(sys.executable)
    candidate = os.path.join(folder, "pythonw.exe")
    return candidate if os.path.isfile(candidate) else sys.executable


def panel_script(*parts):
    return os.path.join(PANEL_DIR, *parts)


def quote(arg):
    return subprocess.list2cmdline([str(arg)])


def spawn_detached(args, cwd=None):
    # Devuelve el PID del proceso nuevo
    args = [str(a) for a in args]
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    for extra in (CREATE_BREAKAWAY_FROM_JOB, None):
        if extra is None:
            pid = spawn_wmi(args, cwd)

            if pid:
                return pid

            extra = 0

        try:
            proc = subprocess.Popen(args, cwd=cwd, creationflags=flags | extra, close_fds=True,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            return proc.pid
        except OSError:
            continue

    raise RuntimeError("No se pudo iniciar el proceso")


def spawn_wmi(args, cwd=None):
    # WMI crea el proceso fuera de cualquier job
    line = subprocess.list2cmdline(args).replace("'", "''")
    script = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
              "@{CommandLine='%s'%s}; if ($r.ReturnValue -eq 0) { $r.ProcessId }"
              % (line, "; CurrentDirectory='%s'" % cwd.replace("'", "''") if cwd else ""))

    try:
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, text=True, timeout=60, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return None

    value = result.stdout.strip()
    return int(value) if value.isdigit() else None


def run_quiet(args, **kwargs):
    # Como subprocess.run pero sin abrir ventanas de consola
    kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    return subprocess.run([str(a) for a in args], **kwargs)
