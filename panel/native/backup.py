#
# MCServer by Derpchees - respaldo de un servidor (Windows)
#
#   pythonw backup.py <servidor> auto|manual
#
# Lo mismo que bin/mcpanel-backup.sh en Linux: si el servidor esta
# encendido se pausa el guardado mientras se copia (save-off; en Bedrock
# save hold), se comprime la carpeta en mc-<tipo>-<fecha>.tar.gz y se
# conservan solo los respaldos automaticos mas recientes.
#

import os
import sys
import tarfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcpanel_core as core  # noqa: E402
import announce  # noqa: E402
import runtime  # noqa: E402
from native import winsys  # noqa: E402

# Lo que no hace falta guardar: cache y los programas de Bedrock (se bajan solos)
SKIP_DIRS = {".cache"}
SKIP_EXT = (".exe", ".dll", ".pdb", ".part")


def lock_path(srv):
    return os.path.join(os.path.dirname(srv.run_file), srv.slug + ".backup.lock")


def running(srv):
    try:
        with open(lock_path(srv), "r") as f:
            pid, created = (int(x) for x in f.read().split())
    except (OSError, ValueError):
        return False

    return winsys.pid_alive(pid, created)


def take_lock(srv):
    if running(srv):
        return False

    os.makedirs(os.path.dirname(lock_path(srv)), exist_ok=True)

    with open(lock_path(srv), "w") as f:
        f.write("%d %d" % (os.getpid(), winsys.created_at(os.getpid()) or 0))

    return True


class Backup:

    def __init__(self, srv, kind):
        self.srv = srv
        self.kind = kind
        self.announced = False

    def log(self, text):
        os.makedirs(self.srv.log_dir, exist_ok=True)

        with open(os.path.join(self.srv.log_dir, "backup.log"), "a", encoding="utf-8") as f:
            f.write("%s | %s | %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), self.kind, text))

    def fail(self, text):
        self.log("ERROR | " + text)
        core.add_event(self.srv.id, "backup_failed", "error", text[:200])

        if self.announced:
            announce.announce(self.srv, "backup_failed")

        sys.exit(1)

    def pause_saving(self):
        srv = self.srv

        if not core.is_bedrock(srv):
            if not runtime.rcon(srv, ["save-off"])[0]:
                return False

            runtime.rcon(srv, ["save-all", "flush"])
            time.sleep(5)
            return True

        since = time.time()

        if not runtime.console_send(srv, "save hold")[0]:
            return False

        for _ in range(30):
            time.sleep(2)
            runtime.console_send(srv, "save query")

            if "ready to be copied" in runtime.logs(srv, since=since):
                return True

        return True

    def resume_saving(self):
        if core.is_bedrock(self.srv):
            runtime.console_send(self.srv, "save resume")
        else:
            runtime.rcon(self.srv, ["save-on"])

    def run(self):
        srv = self.srv

        if not core.path_available(srv.backup_dir):
            self.fail("El disco de respaldos no está conectado")

        os.makedirs(srv.backup_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        final = os.path.join(srv.backup_dir, "mc-%s-%s.tar.gz" % (self.kind, stamp))
        tmp = final + ".partial"
        paused = False

        if runtime.running(srv):
            announce.announce(srv, "backup_start")
            self.announced = True
            paused = self.pause_saving()
            self.log("INICIANDO | Minecraft encendido, " + ("guardado pausado" if paused
                                                           else "no se pudo pausar el guardado, se respalda igual"))
        else:
            self.log("INICIANDO | Minecraft apagado")

        start = time.time()
        base = os.path.basename(os.path.normpath(srv.data_dir))

        skipped = []

        try:
            with tarfile.open(tmp, "w:gz", compresslevel=6) as tar:
                for root, dirs, files in os.walk(srv.data_dir):
                    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

                    for name in files:
                        if name.lower().endswith(SKIP_EXT):
                            continue

                        full = os.path.join(root, name)
                        relative = os.path.relpath(full, srv.data_dir).replace(os.sep, "/")

                        # Un archivo bloqueado por otro programa se salta, no tira el respaldo
                        try:
                            tar.add(full, arcname=base + "/" + relative, recursive=False)
                        except OSError:
                            skipped.append(relative)
        except OSError as error:
            try:
                os.remove(tmp)
            except OSError:
                pass

            if paused:
                self.resume_saving()
                paused = False

            self.fail("No se pudo crear el respaldo: %s" % error)
        finally:
            if paused:
                self.resume_saving()

        if skipped:
            self.log("AVISO | archivos en uso no copiados: " + ", ".join(skipped[:10]))

        os.replace(tmp, final)
        size = os.path.getsize(final)
        text = "%.1fM" % (size / 1024 ** 2) if size < 1024 ** 3 else "%.1fG" % (size / 1024 ** 3)
        self.log("COMPLETADO | %s | %s | %ds" % (os.path.basename(final), text, time.time() - start))
        core.add_event(srv.id, "backup_ok", "success", text)

        if self.announced:
            announce.announce(srv, "backup_done")

        # Solo se conservan los automaticos mas recientes
        if self.kind == "auto":
            keep = min(srv.backup_keep, core.BACKUP_KEEP_MAX)
            autos = sorted((n for n in os.listdir(srv.backup_dir)
                            if n.startswith("mc-auto-") and n.endswith(".tar.gz")), reverse=True)

            for old in autos[keep:]:
                os.remove(os.path.join(srv.backup_dir, old))
                self.log("BORRADO RESPALDO ANTERIOR | " + old)


def main():
    if len(sys.argv) != 3 or sys.argv[2] not in ("auto", "manual"):
        print("Uso: backup.py <servidor> auto|manual", file=sys.stderr)
        sys.exit(2)

    srv = core.get_server_by_slug(sys.argv[1])

    if not srv:
        sys.exit(1)

    job = Backup(srv, sys.argv[2])

    if not take_lock(srv):
        job.log("YA HAY UN RESPALDO EN CURSO | cancelado")
        sys.exit(1)

    try:
        job.run()
    finally:
        try:
            os.remove(lock_path(srv))
        except OSError:
            pass


if __name__ == "__main__":
    main()
