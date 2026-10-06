#
# MCServer by Derpchees - vigilante de un servidor (Windows)
#
#   pythonw runner.py <launch.json>
#
# Corre el servidor (Java o bedrock_server.exe) y se queda con su consola:
#   - guarda cada linea en el log con la hora ("<ms>\t<linea>")
#   - escucha en 127.0.0.1 (puerto al azar, con clave) para mandarle
#     comandos o apagarlo con "stop" (como docker stop)
#   - si se cae y asi se pidio, lo vuelve a encender (como --restart de Docker)
# Su estado (PIDs, puerto, si sigue encendido) va en un JSON que lee el panel.
#

import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from native import winsys  # noqa: E402

CREATE_NO_WINDOW = 0x08000000
LOG_LIMIT = 20 * 1024 * 1024
STOP_TIMEOUT = 90


class Runner:

    def __init__(self, launch):
        self.launch = launch
        self.state_path = launch["state"]
        self.token = secrets.token_hex(16)
        self.lock = threading.Lock()
        self.child = None
        self.stopping = threading.Event()
        self.state = {"pid": os.getpid(), "created": winsys.created_at(os.getpid()),
                      "token": self.token, "status": "starting", "child": None,
                      "started": time.time(), "exit_code": None}

    # ---------- estado y log ----------

    def save(self, **values):
        self.state.update(values)
        tmp = self.state_path + ".tmp"

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f)

        # Si alguien lo esta leyendo justo ahora, Windows no deja reemplazarlo
        for _ in range(50):
            try:
                os.replace(tmp, self.state_path)
                return
            except PermissionError:
                time.sleep(0.05)

    def log(self, text):
        path = self.launch["log"]
        line = "%d\t%s\n" % (time.time() * 1000, text.rstrip("\r\n"))

        with self.lock:
            try:
                if os.path.getsize(path) > LOG_LIMIT:
                    os.replace(path, path + ".1")
            except OSError:
                pass

            with open(path, "a", encoding="utf-8") as f:
                f.write(line)

    def read_output(self, child):
        for raw in iter(child.stdout.readline, b""):
            self.log(raw.decode("utf-8", "replace"))

    # ---------- comandos ----------

    def send(self, text):
        child = self.child

        if not child or child.poll() is not None:
            return False

        try:
            child.stdin.write((text.strip() + "\n").encode("utf-8"))
            child.stdin.flush()
            return True
        except OSError:
            return False

    def stop(self):
        if self.stopping.is_set():
            return

        self.stopping.set()
        self.save(status="stopping")
        self.send(self.launch.get("stop_command") or "stop")

        # Si no termina a tiempo, se cierra a la fuerza
        def deadline(child=self.child):
            time.sleep(STOP_TIMEOUT)

            if child and child.poll() is None:
                self.log("[MCServer] no se apago a tiempo; se cierra a la fuerza")
                child.kill()

        threading.Thread(target=deadline, daemon=True).start()

    def serve(self, listener):
        while True:
            conn, _ = listener.accept()
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()

    def handle(self, conn):
        with conn:
            try:
                conn.settimeout(10)
                data = b""

                while not data.endswith(b"\n") and len(data) < 65536:
                    chunk = conn.recv(4096)

                    if not chunk:
                        break

                    data += chunk

                request = json.loads(data.decode("utf-8"))
            except (OSError, ValueError):
                return

            ok = False

            if request.get("token") == self.token:
                if request.get("op") == "send":
                    ok = self.send(str(request.get("text", ""))[:4000])
                elif request.get("op") == "stop":
                    self.stop()
                    ok = True

            try:
                conn.sendall(json.dumps({"ok": ok}).encode("utf-8") + b"\n")
            except OSError:
                pass

    # ---------- ciclo ----------

    def run(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        self.save(port=listener.getsockname()[1])
        threading.Thread(target=self.serve, args=(listener,), daemon=True).start()

        crashes = []
        code = None

        while True:
            self.log("[MCServer] iniciando: " + " ".join(self.launch["cmd"][:1]))

            try:
                env = dict(os.environ, **self.launch.get("env", {}))
                child = subprocess.Popen(self.launch["cmd"], cwd=self.launch["cwd"], env=env,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW)
            except OSError as error:
                self.log("[MCServer] no se pudo iniciar: %s" % error)
                code = -1
                break

            self.child = child
            # El job cierra el servidor si este vigilante muere, y pone los topes
            job = winsys.limit_job(child.pid, self.launch.get("memory", 0),
                                   self.launch.get("cpus", 0), os.cpu_count() or 1)
            self.save(status="running", child=child.pid, child_created=winsys.created_at(child.pid),
                      started=time.time(), exit_code=None)

            reader = threading.Thread(target=self.read_output, args=(child,), daemon=True)
            reader.start()
            code = child.wait()
            reader.join(5)
            self.child = None

            if job:
                winsys.kernel32.CloseHandle(job)

            self.log("[MCServer] terminó con código %d" % code)

            if self.stopping.is_set() or code == 0 or not self.launch.get("restart"):
                break

            # Se reinicia tras una caida, pero no mas de 3 veces en 10 minutos
            crashes = [t for t in crashes if time.time() - t < 600] + [time.time()]

            if len(crashes) > 3:
                break

            self.save(status="restarting", child=None, exit_code=code)
            time.sleep(5)

        self.save(status="exited", child=None, exit_code=code, stopped=time.time(),
                  manual=self.stopping.is_set())


if __name__ == "__main__":
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        Runner(json.load(f)).run()
