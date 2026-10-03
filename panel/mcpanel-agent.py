#!/usr/bin/env python3
#
# MCServer by Derpchees - agente
# https://github.com/Derpchees/mcserver
#
# Un solo proceso para todos los servidores:
#   - proxy: escucha el puerto de cada servidor y lo enciende al conectarse
#   - apagado automatico cuando no hay jugadores
#   - respaldos programados
#   - eventos para las notificaciones (encendido, apagado, caidas, alertas)
#

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mcpanel_core as core  # noqa: E402
from storage import watch  # noqa: E402


CHECK_INTERVAL = 10
START_TIMEOUT = 300
ALERT_COOLDOWN = 3600


def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(srv, filename, text):
    try:
        os.makedirs(srv.log_dir, exist_ok=True)

        with open(os.path.join(srv.log_dir, filename), "a", encoding="utf-8") as f:
            f.write(now_text() + " | " + text + "\n")
    except OSError:
        pass


def set_hint(srv, reason):
    # Motivo del proximo apagado, para distinguirlo de una caida
    try:
        os.makedirs(os.path.dirname(srv.run_file), exist_ok=True)

        with open(srv.run_file + ".hint", "w") as f:
            f.write("%s %d" % (reason, int(time.time())))
    except OSError:
        pass


def take_hint(srv):
    path = srv.run_file + ".hint"

    try:
        with open(path, "r") as f:
            reason, ts = f.read().split()

        os.remove(path)

        if time.time() - int(ts) < 300:
            return reason
    except (OSError, ValueError):
        pass

    return None


async def run(*args):
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")


async def inspect(srv):
    code, out, _ = await run(
        "docker", "inspect", "-f",
        "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}|{{.State.ExitCode}}",
        srv.container
    )

    if code != 0:
        return "missing", "missing", 0

    status, health, exit_code = (out.strip().split("|") + ["", "", "0"])[:3]

    try:
        exit_code = int(exit_code)
    except ValueError:
        exit_code = 0

    return status, health, exit_code


async def port_open(port):
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 2)
        writer.close()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


# ============================================================
# Proxy
# ============================================================

class Proxy:

    def __init__(self):
        self.listeners = {}

    async def refresh(self, servers):
        wanted = {srv.id: srv for srv in servers if srv.state == "ready"}

        for server_id in list(self.listeners):
            port, listener = self.listeners[server_id]
            srv = wanted.get(server_id)

            if not srv or srv.game_port != port:
                listener.close()
                del self.listeners[server_id]

        for server_id, srv in wanted.items():
            if server_id in self.listeners:
                continue

            try:
                listener = await asyncio.start_server(
                    lambda r, w, sid=server_id: self.handle(sid, r, w),
                    core.LISTEN_IP, srv.game_port, reuse_address=True
                )
                self.listeners[server_id] = (srv.game_port, listener)
            except OSError as error:
                log(srv, "proxy.log", "ERROR | no se pudo escuchar el puerto %d: %s" % (srv.game_port, error))

    async def handle(self, server_id, reader, writer):
        srv = core.get_server(server_id)

        if not srv:
            writer.close()
            return

        status, _, _ = await inspect(srv)
        log(srv, "proxy.log", "PETICION RECIBIDA | Minecraft estaba: " + status)

        if status != "running" and not watch.data_ready():
            log(srv, "proxy.log", "SIN INICIO | el disco de los servidores no esta disponible")
            writer.close()
            return

        if status != "running":
            log(srv, "proxy.log", "INICIO AUTOMATICO | docker start " + srv.container)
            await run("docker", "start", srv.container)

            for i in range(START_TIMEOUT):
                if await port_open(srv.internal_port):
                    log(srv, "proxy.log", "MINECRAFT DISPONIBLE | espera=%ds" % (i + 1))
                    break

                if reader.at_eof():
                    break

                await asyncio.sleep(1)
        else:
            log(srv, "proxy.log", "MINECRAFT YA ESTABA ENCENDIDO")

        try:
            up_reader, up_writer = await asyncio.open_connection("127.0.0.1", srv.internal_port)
        except OSError:
            writer.close()
            return

        async def pipe(src, dst):
            try:
                while True:
                    data = await src.read(65536)

                    if not data:
                        break

                    dst.write(data)
                    await dst.drain()
            except (OSError, asyncio.CancelledError):
                pass
            finally:
                try:
                    dst.close()
                except OSError:
                    pass

        await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))


# ============================================================
# Monitor: estado, apagado automatico y eventos
# ============================================================

class Monitor:

    def __init__(self):
        self.idle_since = {}
        self.last_status = {}
        self.announced_ready = set()

    def write_state(self, srv, data):
        data.update({"enabled": bool(srv.autostop), "timeout_seconds": srv.idle_minutes * 60})

        try:
            os.makedirs(os.path.dirname(srv.run_file), exist_ok=True)

            with open(srv.run_file + ".tmp", "w") as f:
                json.dump(data, f)

            os.replace(srv.run_file + ".tmp", srv.run_file)
        except OSError:
            pass

    async def players(self, srv):
        code, out, _ = await run("docker", "exec", srv.container, "rcon-cli", "list")

        if code != 0:
            return None, []

        out = re.sub(r"\x1b\[[0-9;]*m", "", out)
        m = re.search(r"There are (\d+)", out)

        if not m:
            return None, []

        names = []

        if "online:" in out:
            names = [n.strip() for n in out.split("online:", 1)[1].split(",")]
            names = [n for n in names if re.match(r"^\w{1,16}$", n)]

        return int(m.group(1)), names

    async def check(self, srv):
        status, health, exit_code = await inspect(srv)
        previous = self.last_status.get(srv.id)
        self.last_status[srv.id] = status
        idle_total = srv.idle_minutes * 60

        # Transiciones -> eventos
        if previous == "running" and status != "running":
            self.announced_ready.discard(srv.id)
            reason = take_hint(srv)

            if reason == "auto":
                core.add_event(srv.id, "server_stopped", "info", "auto")
            elif reason in ("manual", "restart"):
                core.add_event(srv.id, "server_stopped", "info", reason)
            elif exit_code not in (0, 143):
                core.add_event(srv.id, "server_crashed", "error", "exit %d" % exit_code)
            else:
                core.add_event(srv.id, "server_stopped", "info", "other")

        if status == "running" and health == "healthy" and srv.id not in self.announced_ready:
            self.announced_ready.add(srv.id)

            # No se anuncia el estado que ya tenia al arrancar el agente
            if previous is not None:
                core.add_event(srv.id, "server_started", "success", "")

        if status != "running":
            self.idle_since.pop(srv.id, None)
            self.write_state(srv, {"running": False, "health": "offline", "players": 0,
                                   "names": [], "idle_seconds": 0, "remaining_seconds": idle_total})
            return

        if health != "healthy":
            self.idle_since.pop(srv.id, None)
            self.write_state(srv, {"running": True, "health": health, "players": 0,
                                   "names": [], "idle_seconds": 0, "remaining_seconds": idle_total})
            return

        count, names = await self.players(srv)

        if count is None:
            self.idle_since.pop(srv.id, None)
            self.write_state(srv, {"running": True, "health": health, "players": 0,
                                   "names": [], "idle_seconds": 0, "remaining_seconds": idle_total})
            return

        if count > 0 or not srv.autostop:
            if srv.id in self.idle_since and count > 0:
                log(srv, "autostop.log", "JUGADORES DETECTADOS: %d | cancelando cuenta regresiva" % count)

            self.idle_since.pop(srv.id, None)
            self.write_state(srv, {"running": True, "health": health, "players": count,
                                   "names": names, "idle_seconds": 0, "remaining_seconds": idle_total})
            return

        now = time.time()

        if srv.id not in self.idle_since:
            self.idle_since[srv.id] = now
            log(srv, "autostop.log", "0 JUGADORES | iniciando cuenta regresiva de %ds" % idle_total)

        elapsed = int(now - self.idle_since[srv.id])
        remaining = max(0, idle_total - elapsed)

        self.write_state(srv, {"running": True, "health": health, "players": 0, "names": [],
                               "idle_seconds": elapsed, "remaining_seconds": remaining})

        if remaining <= 0:
            count, _ = await self.players(srv)

            if count == 0:
                log(srv, "autostop.log", "0 JUGADORES DURANTE %ds | APAGANDO MINECRAFT" % idle_total)
                set_hint(srv, "auto")
                await run("docker", "stop", srv.container)
                log(srv, "autostop.log", "MINECRAFT APAGADO AUTOMATICAMENTE")
            else:
                log(srv, "autostop.log", "JUGADOR DETECTADO EN VERIFICACION FINAL | cancelando")

            self.idle_since.pop(srv.id, None)


# ============================================================
# Respaldos programados
# ============================================================

def last_backup_day(srv):
    try:
        with open(os.path.join(srv.state_dir, "last_auto_backup"), "r") as f:
            return f.read().strip()
    except OSError:
        return ""


async def schedule_backups(servers):
    # Sin disco de respaldos se pausan; al volver se recupera el del dia
    if not watch.backups_ready():
        return

    today = time.strftime("%Y-%m-%d")
    now_hm = time.strftime("%H:%M")

    for srv in servers:
        if srv.state != "ready" or not srv.backups:
            continue

        # Tambien recupera un respaldo perdido si el equipo estaba apagado
        if now_hm < srv.backup_time or last_backup_day(srv) == today:
            continue

        try:
            os.makedirs(srv.state_dir, exist_ok=True)

            with open(os.path.join(srv.state_dir, "last_auto_backup"), "w") as f:
                f.write(today)
        except OSError:
            continue

        srv.write_env()

        await run("systemd-run", "--unit", "mcpanel-backup-%s-%d" % (srv.slug, int(time.time())),
                  "--collect", "--quiet", "--nice=10",
                  os.path.join(core.INSTALL_DIR, "bin", "mcpanel-backup.sh"), srv.slug, "auto")


# ============================================================
# Alertas del equipo
# ============================================================

_last_alert = {}


def alert(key, message):
    if time.time() - _last_alert.get(key, 0) < ALERT_COOLDOWN:
        return

    _last_alert[key] = time.time()
    core.add_event(None, key, "warning", message)


def cpu_temp():
    import glob

    for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            if open(hwmon + "/name").read().strip() != "coretemp":
                continue

            for label in glob.glob(hwmon + "/temp*_label"):
                if open(label).read().startswith("Package"):
                    base = label[:-len("_label")]
                    current = int(open(base + "_input").read()) / 1000
                    high = int(open(base + "_max").read()) / 1000 if os.path.exists(base + "_max") else 80
                    return current, high
        except (OSError, ValueError):
            continue

    return None, None


def check_system():
    temp, high = cpu_temp()

    if temp is not None and temp >= high:
        alert("alert_temp", "%.0f" % temp)

    for path in {core.data_root(), core.backup_root()}:
        if os.path.isdir(path) and core.path_available(path):
            usage = shutil.disk_usage(path)
            percent = (usage.total - usage.free) / usage.total * 100

            if percent >= 90:
                alert("alert_disk:" + path, "%s %.0f" % (path, percent))

    info = {}

    with open("/proc/meminfo") as f:
        for line in f:
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0])

    used = (info["MemTotal"] - info["MemAvailable"]) / info["MemTotal"] * 100

    if used >= 92:
        alert("alert_ram", "%.0f" % used)


# ============================================================

async def main():
    proxy = Proxy()
    monitor = Monitor()
    last_system = 0
    last_backup_check = 0

    while True:
        try:
            servers = core.list_servers()
            await proxy.refresh(servers)

            # Si el disco de los servidores se desconecto, se apagan
            if watch.check():
                for srv in servers:
                    status, _, _ = await inspect(srv)

                    if status == "running":
                        set_hint(srv, "manual")
                        log(srv, "autostop.log", "DISCO DE SERVIDORES DESCONECTADO | apagando")
                        await run("docker", "stop", srv.container)

            await asyncio.gather(*(
                monitor.check(srv) for srv in servers if srv.state == "ready"
            ), return_exceptions=True)

            if time.time() - last_backup_check >= 30:
                last_backup_check = time.time()
                await schedule_backups(servers)

            if time.time() - last_system >= 60:
                last_system = time.time()
                await asyncio.get_running_loop().run_in_executor(None, check_system)

        except Exception as error:
            print("agente:", error, file=sys.stderr, flush=True)

        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
