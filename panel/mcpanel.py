#!/usr/bin/env python3
#
# Minecraft Server Panel
# https://github.com/Derpchees/minecraft-server-panel
#
# Panel web para administrar un servidor de Minecraft en Docker
# (itzg/minecraft-server). Toda la configuracion vive en
# /etc/mcpanel/config.env, que escribe install.sh.
#

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import json
import os
import re
import time
import calendar
import urllib.parse
import html
import threading
import shutil
import shlex
import hashlib
import hmac
import secrets
import http.cookies
import glob
import gzip
import tempfile
import zipfile

CONFIG_ENV = os.environ.get("MCPANEL_CONFIG", "/etc/mcpanel/config.env")


def load_env(path):
    # Formato KEY="valor", el mismo que leen los scripts de bash
    values = {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, _, value = line.partition("=")
                value = value.strip()

                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]

                values[key.strip()] = value
    except FileNotFoundError:
        pass

    return values


CFG = load_env(CONFIG_ENV)


def cfg(key, default=""):
    return CFG.get(key, default) or default


CONTAINER = cfg("CONTAINER", "mcpanel-minecraft")
SERVER_NAME = cfg("SERVER_NAME", "Minecraft Server")
PUBLIC_ADDRESS = cfg("PUBLIC_ADDRESS", "")
DEFAULT_LANG = cfg("LANG_DEFAULT", "en")
LOG_DIR = cfg("LOG_DIR", "/var/log/mcpanel")
STATE_DIR = cfg("STATE_DIR", "/var/lib/mcpanel")
RUN_DIR = cfg("RUN_DIR", "/run/mcpanel")
INSTALL_DIR = cfg("INSTALL_DIR", "/opt/mcpanel")

LOG_FILE = os.path.join(LOG_DIR, "proxy.log")
AUTOSTOP_LOG = os.path.join(LOG_DIR, "autostop.log")
AUTOSTOP_FILE = os.path.join(RUN_DIR, "autostop.json")
PORT = int(cfg("PANEL_PORT", "8090"))
BIND = cfg("PANEL_BIND", "0.0.0.0")


def command(cmd):
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except Exception:
        return ""


def container_info():
    running = command(
        "docker inspect -f '{{.State.Running}}' "
        + CONTAINER + " 2>/dev/null"
    )

    status = command(
        "docker inspect -f '{{.State.Status}}' "
        + CONTAINER + " 2>/dev/null"
    )

    health = command(
        "docker inspect -f "
        "'{{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}' "
        + CONTAINER + " 2>/dev/null"
    )

    return running, status, health


def autostop_info():
    default = {
        "enabled": True,
        "running": False,
        "health": "offline",
        "players": 0,
        "idle_seconds": 0,
        "remaining_seconds": 600,
        "timeout_seconds": 600
    }

    try:
        with open(AUTOSTOP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Segundos desde que mc-autostop.sh escribio el estado;
        # la pagina lo usa para que el contador no vaya a saltos
        data["age"] = max(
            0,
            time.time() - os.path.getmtime(AUTOSTOP_FILE)
        )

        return data
    except Exception:
        return default


def read_lines(path):
    if not os.path.exists(path):
        return []

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as f:
            return [x.strip() for x in f if x.strip()]
    except Exception:
        return []


def activity():
    return read_lines(LOG_FILE)


def local_ts(text):
    try:
        return time.mktime(
            time.strptime(text, "%Y-%m-%d %H:%M:%S")
        )
    except Exception:
        return 0


PLAYER_EVENT = re.compile(
    r"^(\S+) \[.*?\]: (\w{1,16}) (joined|left) the game$"
)

_player_cache = {"time": 0, "events": []}


def player_events():
    # docker logs es grande; se consulta como mucho cada 10s
    if time.time() - _player_cache["time"] < 10:
        return _player_cache["events"]

    output = command(
        "docker logs --timestamps --since 168h "
        + CONTAINER
        + " 2>&1 | grep -E ' (joined|left) the game$'"
    )

    events = []

    for line in output.splitlines():
        m = PLAYER_EVENT.match(line.strip())

        if not m:
            continue

        stamp, name, kind = m.groups()

        try:
            ts = calendar.timegm(
                time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S")
            )
        except Exception:
            continue

        events.append({
            "ts": ts,
            "type": "join" if kind == "joined" else "leave",
            "text": name
        })

    _player_cache["time"] = time.time()
    _player_cache["events"] = events

    return events


def recent_events(lines, limit=30):
    # "text" es el nombre del jugador (join/leave) o un dato corto;
    # la pagina arma la frase en el idioma elegido
    events = list(player_events())

    for line in lines:
        stamp, _, rest = line.partition(" | ")

        if "PETICION RECIBIDA" in rest:
            kind = "request"
            state = rest.rpartition(":")[2].strip()
            text = "on" if state == "running" else "off"
        elif "INICIO AUTOMATICO" in rest:
            kind = "start"
            text = ""
        else:
            continue

        events.append({
            "ts": local_ts(stamp),
            "type": kind,
            "text": text
        })

    for line in read_lines(AUTOSTOP_LOG):
        stamp, _, rest = line.partition(" | ")

        if "APAGADO AUTOMATICAMENTE" in rest:
            events.append({
                "ts": local_ts(stamp),
                "type": "stop",
                "text": ""
            })

    events.sort(key=lambda x: x["ts"])

    return events[-limit:]


def server_data():
    running, status, health = container_info()
    lines = activity()

    attempts = [
        x for x in lines
        if "PETICION RECIBIDA" in x
    ]

    starts = [
        x for x in lines
        if "INICIO AUTOMATICO" in x
    ]

    return {
        "running": running == "true",
        "status": status or "desconocido",
        "health": health or "desconocido",
        "attempts": len(attempts),
        "last_attempt": attempts[-1] if attempts else "Ninguno",
        "last_start": starts[-1] if starts else "Ninguno",
        "events": recent_events(lines),
        "autostop": autostop_info()
    }


def docker_action(name):
    commands = {
        "start": ["docker", "start", CONTAINER],
        "stop": ["docker", "stop", CONTAINER],
        "restart": ["docker", "restart", CONTAINER]
    }

    messages = {
        "start": "Servidor iniciado",
        "stop": "Servidor apagado",
        "restart": "Servidor reiniciado"
    }

    if name not in commands:
        return {
            "ok": False,
            "message": "Acción no válida"
        }

    result = subprocess.run(
        commands[name],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return {
            "ok": True,
            "message": messages[name]
        }

    return {
        "ok": False,
        "message": "Error ejecutando Docker",
        "output": result.stderr.strip()
    }


def send_command(command_text):
    command_text = command_text.strip()

    if not command_text:
        return {
            "ok": False,
            "message": "Comando vacío"
        }

    running, _, _ = container_info()

    if running != "true":
        return {
            "ok": False,
            "message": "El servidor está apagado"
        }

    result = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER,
            "rcon-cli",
            command_text
        ],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return {
            "ok": True,
            "message": "Comando enviado",
            "output": result.stdout.strip()
        }

    return {
        "ok": False,
        "message": "No se pudo ejecutar el comando",
        "output": result.stderr.strip()
    }


# Lineas que genera mc-autostop.sh cada 10s al consultar
# jugadores con rcon-cli; solo ensucian la consola
RCON_NOISE = re.compile(
    r"Thread RCON Client /\S+ (started|shutting down)"
)


def console():
    running, _, _ = container_info()

    if running != "true":
        return "El servidor está apagado."

    result = subprocess.run(
        [
            "docker",
            "logs",
            "--tail",
            "2000",
            CONTAINER
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace"
    )

    lines = [
        x for x in result.stdout.splitlines()
        if not RCON_NOISE.search(x)
    ]

    return "\n".join(lines[-250:])[-60000:]




# ============================================================
# Monitor de recursos
# ============================================================

DATA_DIR = cfg("DATA_DIR", "/srv/minecraft/data")
BACKUP_DIR = cfg("BACKUP_DIR", "/srv/minecraft/backups")
HISTORY_POINTS = 90
STATS_INTERVAL = 2

_stats = {
    "cpu": 0.0,
    "cpu_history": [],
    "mem_history": [],
    "container": None,
    "data_size": None,
    "backup_size": None,
    "docker_size": None
}

_stats_lock = threading.Lock()


def read_cpu_times():
    with open("/proc/stat", "r") as f:
        values = [int(x) for x in f.readline().split()[1:]]

    idle = values[3] + values[4]
    return sum(values), idle


def read_memory():
    info = {}

    with open("/proc/meminfo", "r") as f:
        for line in f:
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0]) * 1024

    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", 0)

    return total, total - available


def dir_size(path):
    output = command("du -sb " + shlex.quote(path) + " 2>/dev/null")

    try:
        return int(output.split()[0])
    except Exception:
        return None


def parse_docker_size(text):
    m = re.match(r"([\d.]+)\s*([KMGT]?i?B)", text.strip())

    if not m:
        return 0

    units = {
        "B": 1,
        "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12,
        "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4
    }

    return int(float(m.group(1)) * units.get(m.group(2), 1))


def stats_loop():
    prev_total, prev_idle = read_cpu_times()

    while True:
        time.sleep(STATS_INTERVAL)

        try:
            total, idle = read_cpu_times()
            dt = total - prev_total
            cpu = 0.0 if dt <= 0 else (1 - (idle - prev_idle) / dt) * 100
            prev_total, prev_idle = total, idle

            mem_total, mem_used = read_memory()
            now = int(time.time())

            with _stats_lock:
                _stats["cpu"] = round(cpu, 1)
                _stats["cpu_history"].append([now, round(cpu, 1)])
                _stats["mem_history"].append([now, mem_used])
                del _stats["cpu_history"][:-HISTORY_POINTS]
                del _stats["mem_history"][:-HISTORY_POINTS]
        except Exception:
            pass


def slow_stats_loop():
    # docker stats y du son lentos; van en su propio hilo
    last_du = 0

    while True:
        try:
            output = command(
                "docker stats --no-stream --format "
                "'{{.CPUPerc}}|{{.MemUsage}}' " + CONTAINER + " 2>/dev/null"
            )

            container = None

            if "|" in output:
                cpu_text, mem_text = output.split("|", 1)
                used, _, limit = mem_text.partition("/")
                container = {
                    "cpu": float(cpu_text.strip().rstrip("%") or 0),
                    "mem_used": parse_docker_size(used),
                    "mem_limit": parse_docker_size(limit)
                }

            with _stats_lock:
                _stats["container"] = container

            if time.time() - last_du > 300 or _stats.pop("refresh_du", False):
                data_size = dir_size(DATA_DIR)
                backup_size = dir_size(BACKUP_DIR)
                docker_size = dir_size("/var/lib/docker")

                with _stats_lock:
                    _stats["data_size"] = data_size
                    _stats["backup_size"] = backup_size
                    _stats["docker_size"] = docker_size

                last_du = time.time()
        except Exception:
            pass

        time.sleep(5)


def mount_point(path):
    path = os.path.realpath(path)

    while not os.path.ismount(path):
        parent = os.path.dirname(path)

        if parent == path:
            break

        path = parent

    return path


def disk_model(names):
    # Nombre comercial del disco (ej. "Samsung SSD 870") si el kernel lo expone
    for name in sorted(names):
        try:
            with open("/sys/block/%s/device/model" % name, "r") as f:
                model = f.read().strip()

            if model:
                return model
        except Exception:
            continue

    return ", ".join(sorted(names))


def configured_disks():
    # Un disco por sistema de archivos: el del servidor, el de los respaldos
    # (si es otro) y el del sistema (si es otro, para ver Docker y swap)
    found = []
    seen = {}

    for role, path in (("data", DATA_DIR), ("backups", BACKUP_DIR), ("system", "/")):
        if not os.path.exists(path):
            continue

        mount = mount_point(path)
        dev = os.stat(mount).st_dev

        if dev in seen:
            seen[dev]["roles"].append(role)
            continue

        entry = {"mount": mount, "roles": [role]}
        seen[dev] = entry
        found.append(entry)

    return found


def swap_file_size(mount):
    # Archivos de swap que viven en el disco indicado
    total = 0

    try:
        with open("/proc/swaps", "r") as f:
            for line in f.readlines()[1:]:
                name, kind, size = line.split()[:3]

                if kind == "file" and os.stat(name).st_dev == os.stat(mount).st_dev:
                    total += os.path.getsize(name)
    except Exception:
        pass

    return total


def physical_disks(sys_path):
    # Baja por LVM/particiones hasta los discos fisicos (sda, sdb...)
    slaves = glob.glob(sys_path + "/slaves/*")

    if slaves:
        found = set()
        for slave in slaves:
            found |= physical_disks(os.path.realpath(slave))
        return found

    if os.path.exists(sys_path + "/partition"):
        sys_path = os.path.dirname(sys_path)

    return {os.path.basename(sys_path)}


def disks_for_mount(path):
    try:
        st = os.stat(path)
        dev = "%d:%d" % (os.major(st.st_dev), os.minor(st.st_dev))
        return physical_disks(os.path.realpath("/sys/dev/block/" + dev))
    except Exception:
        return set()


def drive_temperatures():
    # Sensores del modulo drivetemp, por nombre de disco
    temps = {}

    for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            with open(hwmon + "/name", "r") as f:
                if f.read().strip() != "drivetemp":
                    continue

            block = os.listdir(hwmon + "/device/block")[0]
        except Exception:
            continue

        current = read_file_int(hwmon + "/temp1_input")

        if current is None:
            continue

        high = read_file_int(hwmon + "/temp1_max")

        temps[block] = {
            "current": current / 1000,
            "high": high / 1000 if high else None
        }

    return temps


def disk_list(sizes):
    disks = []
    temps = drive_temperatures()
    docker_dev = os.stat("/var/lib/docker").st_dev if os.path.exists("/var/lib/docker") else None

    for disk in configured_disks():
        path = disk["mount"]
        roles = disk["roles"]
        dev = os.stat(path).st_dev

        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = (st.f_blocks - st.f_bfree) * st.f_frsize

        # ext4 reserva ~5% para root; no es espacio usado de verdad
        reserved = (st.f_bfree - st.f_bavail) * st.f_frsize

        parts = []

        if "data" in roles:
            parts.append(["server", "Servidor", sizes.get("data")])

        if "backups" in roles:
            parts.append(["backups", "Respaldos", sizes.get("backups")])

        if docker_dev == dev:
            parts.append(["docker", "Docker", sizes.get("docker")])

        swap = swap_file_size(path)

        if swap:
            parts.append(["swap", "Swap", swap])

        rest_id = "system" if "system" in roles else "other"
        rest_label = "Sistema" if rest_id == "system" else "Otros"

        known = sum(p[2] or 0 for p in parts)
        rest = max(0, used - known)

        # ext4 siempre aparta unos MB para uso interno; por debajo
        # de 128 MB solo meteria ruido en la grafica
        tiny = 128 * 1024 ** 2

        parts.append([rest_id, rest_label, rest if rest >= tiny else 0])
        parts.append(["reserved", "Reservado", reserved if reserved >= tiny else 0])

        disk_temps = [
            temps[name] for name in sorted(disks_for_mount(path))
            if name in temps
        ]

        temp = None

        if disk_temps:
            temp = max(disk_temps, key=lambda t: t["current"])
            # Sin limite reportado: 70 C para SSD, 55 C para discos mecanicos
            if temp["high"] is None:
                rotational = read_file_int(
                    "/sys/block/%s/queue/rotational" % sorted(disks_for_mount(path))[0]
                )
                temp["high"] = 55 if rotational == 1 else 70

        disks.append({
            "id": "-".join(roles),
            "role": "data" if "data" in roles else roles[0],
            "label": disk_model(disks_for_mount(path)),
            "mount": path,
            "temp": temp,
            "total": total,
            "used": used + reserved,
            "free": free,
            "parts": [
                {"id": p[0], "label": p[1], "size": p[2]}
                for p in parts
            ]
        })

    return disks


def read_file_int(path):
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def cpu_temperature():
    # Temperatura general del procesador (sensor "Package" de coretemp)
    for hwmon in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        try:
            with open(hwmon + "/name", "r") as f:
                if f.read().strip() != "coretemp":
                    continue
        except Exception:
            continue

        for label_file in sorted(glob.glob(hwmon + "/temp*_label")):
            try:
                with open(label_file, "r") as f:
                    if not f.read().startswith("Package"):
                        continue
            except Exception:
                continue

            base = label_file[:-len("_label")]
            current = read_file_int(base + "_input")

            if current is None:
                continue

            high = read_file_int(base + "_max")
            crit = read_file_int(base + "_crit")

            return {
                "current": current / 1000,
                "high": high / 1000 if high else 80,
                "crit": crit / 1000 if crit else 95
            }

    for zone in glob.glob("/sys/class/thermal/thermal_zone*"):
        try:
            with open(zone + "/type", "r") as f:
                if f.read().strip() != "x86_pkg_temp":
                    continue
        except Exception:
            continue

        current = read_file_int(zone + "/temp")

        if current is not None:
            return {"current": current / 1000, "high": 80, "crit": 95}

    return None


def system_stats():
    mem_total, mem_used = read_memory()

    with _stats_lock:
        data = {
            "cpu": {
                "percent": _stats["cpu"],
                "cores": os.cpu_count(),
                "load": os.getloadavg(),
                "temp": cpu_temperature(),
                "history": list(_stats["cpu_history"])
            },
            "memory": {
                "total": mem_total,
                "used": mem_used,
                "history": list(_stats["mem_history"])
            },
            "disks": disk_list({
                "data": _stats["data_size"],
                "backups": _stats["backup_size"],
                "docker": _stats["docker_size"]
            }),
            "container": _stats["container"]
        }

    try:
        with open("/proc/uptime", "r") as f:
            data["uptime"] = int(float(f.read().split()[0]))
    except Exception:
        data["uptime"] = None

    return data


# ============================================================
# Chat del servidor
# ============================================================

LOGS_DIR = os.path.join(DATA_DIR, "logs")
CHAT_LIMIT = 3000

# Forge: [29Sep2026 00:40:42.324] [Server thread/INFO] [...]: mensaje
CHAT_LINE_FULL = re.compile(
    r"^\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2})\.\d+\] \[Server thread/INFO\] \[[^\]]*\]: (.*)$"
)

# Vanilla: [00:40:42] [Server thread/INFO]: mensaje (fecha sale del archivo)
CHAT_LINE_SHORT = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2})\] \[Server thread/INFO\](?: \[[^\]]*\])?: (.*)$"
)

CHAT_PATTERNS = [
    ("chat", re.compile(r"^(?:\[Not Secure\] )?<([^>]{1,32})> (.*)$")),
    ("say", re.compile(r"^(?:\[Not Secure\] )?\[(Server|Rcon)\] (.*)$")),
    ("join", re.compile(r"^(\w{1,16}) joined the game$")),
    ("leave", re.compile(r"^(\w{1,16}) left the game$")),
    ("advancement", re.compile(
        r"^(\w{1,16}) has (?:made the advancement|completed the challenge|reached the goal) \[(.+)\]$"
    ))
]

_chat_cache = {}
_chat_lock = threading.Lock()


def parse_chat_message(text):
    for kind, pattern in CHAT_PATTERNS:
        m = pattern.match(text)

        if m:
            groups = m.groups()
            return {
                "type": kind,
                "name": groups[0],
                "text": groups[1] if len(groups) > 1 else ""
            }

    return None


def parse_chat_file(path):
    # Los logs guardan la hora del contenedor, que esta en UTC
    name = os.path.basename(path)
    date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", name)

    if date_match:
        file_date = date_match.group(1)
    else:
        file_date = time.strftime("%Y-%m-%d", time.gmtime(os.path.getmtime(path)))

    opener = gzip.open if path.endswith(".gz") else open
    messages = []

    try:
        with opener(path, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")

                m = CHAT_LINE_FULL.match(line)

                if m:
                    try:
                        ts = calendar.timegm(time.strptime(m.group(1), "%d%b%Y %H:%M:%S"))
                    except ValueError:
                        continue
                else:
                    m = CHAT_LINE_SHORT.match(line)

                    if not m:
                        continue

                    try:
                        ts = calendar.timegm(
                            time.strptime(file_date + " " + m.group(1), "%Y-%m-%d %H:%M:%S")
                        )
                    except ValueError:
                        continue

                message = parse_chat_message(m.group(2))

                if message:
                    message["ts"] = ts
                    messages.append(message)
    except Exception:
        pass

    return messages


PANEL_CHAT_FILE = os.path.join(STATE_DIR, "chat.jsonl")
CHAT_MAX_CHARS = 240


def panel_chat_messages():
    # Mensajes enviados desde el panel: tellraw no queda en los logs
    # de Minecraft, asi que se guardan aqui para el historial
    messages = []

    try:
        with open(PANEL_CHAT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    messages.append(json.loads(line))
                except ValueError:
                    continue
    except FileNotFoundError:
        pass

    return messages


_chat_senders = {}


def chat_rate_limited(ip):
    # Maximo 1 mensaje por segundo y 20 por minuto por IP
    now = time.time()

    with _chat_lock:
        recent = [x for x in _chat_senders.get(ip, []) if now - x < 60]

        if (recent and now - recent[-1] < 1) or len(recent) >= 20:
            _chat_senders[ip] = recent
            return True

        recent.append(now)
        _chat_senders[ip] = recent

        return False


def send_chat(text):
    # Quita saltos de linea y caracteres de control
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text or "").strip()[:CHAT_MAX_CHARS]

    if not text:
        return {"ok": False, "message": "Mensaje vacío"}

    running, _, _ = container_info()

    if running != "true":
        return {"ok": False, "message": "El servidor está apagado"}

    payload = json.dumps(
        ["", {"text": "[Server] ", "color": "green"}, {"text": text}],
        ensure_ascii=False
    )

    result = subprocess.run(
        ["docker", "exec", CONTAINER, "rcon-cli", "tellraw", "@a", payload],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return {
            "ok": False,
            "message": "No se pudo enviar el mensaje",
            "output": result.stderr.strip()
        }

    os.makedirs(os.path.dirname(PANEL_CHAT_FILE), exist_ok=True)

    with _chat_lock:
        with open(PANEL_CHAT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": int(time.time()),
                "type": "say",
                "name": "Server",
                "text": text
            }, ensure_ascii=False) + "\n")

    return {"ok": True, "message": "Mensaje enviado"}


def chat_history():
    files = glob.glob(os.path.join(LOGS_DIR, "*.log.gz"))
    latest = os.path.join(LOGS_DIR, "latest.log")

    if os.path.exists(latest):
        files.append(latest)

    messages = []
    seen = set()

    with _chat_lock:
        for path in files:
            try:
                st = os.stat(path)
            except OSError:
                continue

            key = (st.st_mtime, st.st_size)
            cached = _chat_cache.get(path)

            if not cached or cached[0] != key:
                cached = (key, parse_chat_file(path))
                _chat_cache[path] = cached

            messages.extend(cached[1])

        for path in list(_chat_cache):
            if path not in files:
                del _chat_cache[path]

        messages.extend(panel_chat_messages())

    unique = []

    # latest.log puede repetirse en el .gz del mismo dia al rotar
    for message in sorted(messages, key=lambda x: x["ts"]):
        ident = (message["ts"], message["type"], message["name"], message["text"])

        if ident in seen:
            continue

        seen.add(ident)
        unique.append(message)

    return {
        "messages": unique[-CHAT_LIMIT:],
        "total": len(unique)
    }


# ============================================================
# Autenticacion del gestor de archivos
# ============================================================

CONFIG_FILE = cfg("SECRET_FILE", "/etc/mcpanel/secret.json")
SESSION_COOKIE = "mcfiles"
SESSION_SECONDS = 12 * 3600

_sessions = {}
_failed_logins = {}
_auth_lock = threading.Lock()


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def check_password(password):
    stored = load_config().get("files_password", "")

    try:
        algorithm, iterations, salt, expected = stored.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        int(iterations)
    ).hex()

    return hmac.compare_digest(digest, expected)


def create_session():
    token = secrets.token_urlsafe(32)

    with _auth_lock:
        now = time.time()

        for key in [k for k, v in _sessions.items() if v < now]:
            del _sessions[key]

        _sessions[token] = now + SESSION_SECONDS

    return token


def valid_session(token):
    if not token:
        return False

    with _auth_lock:
        expires = _sessions.get(token)

        if not expires or expires < time.time():
            _sessions.pop(token, None)
            return False

        return True


def end_session(token):
    with _auth_lock:
        _sessions.pop(token, None)


def login_blocked(ip):
    with _auth_lock:
        count, until = _failed_logins.get(ip, (0, 0))
        return until > time.time()


def register_login(ip, ok):
    with _auth_lock:
        if ok:
            _failed_logins.pop(ip, None)
            return

        count, _ = _failed_logins.get(ip, (0, 0))
        count += 1

        # 5 intentos fallidos -> bloqueo de 5 minutos
        until = time.time() + 300 if count >= 5 else 0
        _failed_logins[ip] = (0 if until else count, until)


# ============================================================
# Gestor de archivos
# ============================================================

FILE_UID = int(cfg("MC_UID", "1000"))
FILE_GID = int(cfg("MC_GID", "1000"))
MAX_EDIT_BYTES = 2 * 1024 * 1024

TEXT_EXTENSIONS = {
    ".txt", ".properties", ".json", ".json5", ".toml", ".yml", ".yaml",
    ".cfg", ".conf", ".ini", ".log", ".md", ".sh", ".bat", ".ps1",
    ".mcmeta", ".js", ".snbt", ".csv", ".xml", ".env", ".list"
}


class FileError(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def safe_path(relative, must_exist=True):
    root = os.path.realpath(DATA_DIR)
    relative = (relative or "").replace("\\", "/").lstrip("/")
    full = os.path.realpath(os.path.join(root, relative))

    # realpath resuelve enlaces simbolicos y "..", asi que esto
    # impide salir de la carpeta del servidor
    if full != root and not full.startswith(root + os.sep):
        raise FileError("Ruta fuera de la carpeta del servidor", 403)

    if must_exist and not os.path.lexists(full):
        raise FileError("No existe: " + relative, 404)

    return full


def relative_path(full):
    rel = os.path.relpath(full, os.path.realpath(DATA_DIR))
    return "" if rel == "." else rel.replace(os.sep, "/")


def valid_name(name):
    name = (name or "").strip()

    if not name or name in (".", "..") or "/" in name or "\\" in name or "\0" in name:
        raise FileError("Nombre no válido")

    if len(name.encode("utf-8")) > 255:
        raise FileError("Nombre demasiado largo")

    return name


def give_to_server(path):
    try:
        os.chown(path, FILE_UID, FILE_GID, follow_symlinks=False)
    except Exception:
        pass


def list_files(relative):
    full = safe_path(relative)

    if not os.path.isdir(full):
        raise FileError("No es una carpeta")

    entries = []

    with os.scandir(full) as it:
        for entry in it:
            try:
                st = entry.stat(follow_symlinks=False)
                is_dir = entry.is_dir(follow_symlinks=True)
            except OSError:
                continue

            entries.append({
                "name": entry.name,
                "dir": is_dir,
                "size": 0 if is_dir else st.st_size,
                "mtime": int(st.st_mtime),
                "link": entry.is_symlink()
            })

    entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))

    return {
        "path": relative_path(full),
        "entries": entries
    }


def read_text_file(relative):
    full = safe_path(relative)

    if not os.path.isfile(full):
        raise FileError("No es un archivo")

    if os.path.getsize(full) > MAX_EDIT_BYTES:
        raise FileError("El archivo es demasiado grande para editarlo aquí (máx. 2 MB)")

    with open(full, "rb") as f:
        raw = f.read()

    if b"\0" in raw:
        raise FileError("Es un archivo binario; descárgalo para verlo")

    return {
        "path": relative_path(full),
        "content": raw.decode("utf-8", errors="replace")
    }


def write_text_file(relative, content):
    full = safe_path(relative, must_exist=False)

    if os.path.isdir(full):
        raise FileError("Es una carpeta")

    data = content.encode("utf-8")

    if len(data) > MAX_EDIT_BYTES:
        raise FileError("Contenido demasiado grande")

    mode = os.stat(full).st_mode & 0o7777 if os.path.exists(full) else 0o664
    tmp = full + ".tmp-panel"

    with open(tmp, "wb") as f:
        f.write(data)

    os.chmod(tmp, mode)
    give_to_server(tmp)
    os.replace(tmp, full)

    return {"ok": True, "message": "Archivo guardado"}


def make_folder(relative, name):
    parent = safe_path(relative)
    target = safe_path(os.path.join(relative_path(parent), valid_name(name)), must_exist=False)

    if os.path.exists(target):
        raise FileError("Ya existe un elemento con ese nombre")

    os.mkdir(target, 0o775)
    give_to_server(target)

    return {"ok": True, "message": "Carpeta creada"}


def rename_item(relative, name):
    source = safe_path(relative)

    if source == os.path.realpath(DATA_DIR):
        raise FileError("No se puede renombrar la carpeta raíz")

    target = os.path.join(os.path.dirname(source), valid_name(name))
    safe_path(relative_path(os.path.dirname(source)) + "/" + os.path.basename(target), must_exist=False)

    if os.path.lexists(target):
        raise FileError("Ya existe un elemento con ese nombre")

    os.rename(source, target)

    return {"ok": True, "message": "Renombrado"}


def delete_item(relative):
    full = safe_path(relative)

    if full == os.path.realpath(DATA_DIR):
        raise FileError("No se puede borrar la carpeta raíz")

    if os.path.isdir(full) and not os.path.islink(full):
        shutil.rmtree(full)
    else:
        os.remove(full)

    return {"ok": True, "message": "Eliminado"}


def ensure_folder(relative):
    # Crea la carpeta (y las intermedias) si no existen; se usa al
    # soltar carpetas completas en el gestor
    folder = safe_path(relative, must_exist=False)
    root = os.path.realpath(DATA_DIR)
    missing = []
    current = folder

    while current != root and not os.path.lexists(current):
        missing.append(current)
        current = os.path.dirname(current)

    for path in reversed(missing):
        valid_name(os.path.basename(path))
        os.mkdir(path, 0o775)
        give_to_server(path)

    return folder


def move_items(paths, dest):
    target_dir = safe_path(dest)
    root = os.path.realpath(DATA_DIR)

    if not os.path.isdir(target_dir):
        raise FileError("El destino no es una carpeta")

    if not paths:
        raise FileError("No hay elementos seleccionados")

    sources = []

    # Se valida todo antes de mover nada
    for relative in paths:
        source = safe_path(relative)

        if source == root:
            raise FileError("No se puede mover la carpeta raíz")

        if target_dir == source or target_dir.startswith(source + os.sep):
            raise FileError("No se puede mover una carpeta dentro de sí misma")

        if os.path.dirname(source) == target_dir:
            raise FileError("El elemento ya está en esa carpeta")

        if os.path.lexists(os.path.join(target_dir, os.path.basename(source))):
            raise FileError("Ya existe un elemento con ese nombre")

        sources.append(source)

    for source in sources:
        shutil.move(source, os.path.join(target_dir, os.path.basename(source)))

    return {"ok": True, "message": "Movido", "count": len(sources)}


def delete_items(paths):
    root = os.path.realpath(DATA_DIR)

    if not paths:
        raise FileError("No hay elementos seleccionados")

    targets = []

    for relative in paths:
        full = safe_path(relative)

        if full == root:
            raise FileError("No se puede borrar la carpeta raíz")

        targets.append(full)

    for full in targets:
        if os.path.isdir(full) and not os.path.islink(full):
            shutil.rmtree(full)
        elif os.path.lexists(full):
            os.remove(full)

    return {"ok": True, "message": "Eliminado", "count": len(targets)}


def build_zip(paths):
    # Empaqueta archivos y carpetas en un ZIP temporal. Sin compresion:
    # los mods y el mundo ya vienen comprimidos y asi es mucho mas rapido
    if not paths:
        raise FileError("No hay elementos seleccionados")

    root = os.path.realpath(DATA_DIR)
    sources = [safe_path(p) for p in paths]

    if len(sources) == 1:
        name = (os.path.basename(sources[0]) or "minecraft-server") + ".zip"
    else:
        name = "minecraft-server-files.zip"

    tmp = tempfile.NamedTemporaryFile(prefix="mc-panel-", suffix=".zip", delete=False)

    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as archive:
            for source in sources:
                base = os.path.dirname(source) if source != root else root

                if os.path.isdir(source) and not os.path.islink(source):
                    for folder, dirs, files in os.walk(source):
                        if not dirs and not files:
                            archive.write(folder, os.path.relpath(folder, base))

                        for file_name in files:
                            full = os.path.join(folder, file_name)

                            if os.path.isfile(full) and not os.path.islink(full):
                                archive.write(full, os.path.relpath(full, base))
                elif os.path.isfile(source):
                    archive.write(source, os.path.relpath(source, base))

        tmp.close()
    except Exception:
        tmp.close()
        os.remove(tmp.name)
        raise

    return tmp.name, name


def receive_upload(handler, relative, name, length):
    folder = ensure_folder(relative)

    if not os.path.isdir(folder):
        raise FileError("El destino no es una carpeta")

    target = safe_path(
        relative_path(folder) + "/" + valid_name(name),
        must_exist=False
    )

    if os.path.isdir(target):
        raise FileError("Ya existe una carpeta con ese nombre")

    tmp = target + ".upload-panel"
    remaining = length

    try:
        with open(tmp, "wb") as f:
            while remaining > 0:
                chunk = handler.rfile.read(min(1024 * 1024, remaining))

                if not chunk:
                    raise FileError("La subida se interrumpió")

                f.write(chunk)
                remaining -= len(chunk)

        os.chmod(tmp, 0o664)
        give_to_server(tmp)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    return {"ok": True, "message": "Archivo subido"}


# ============================================================
# Jugadores
# ============================================================

PLAYER_NAME = re.compile(r"^\w{1,16}$")
TIMEOUTS_FILE = os.path.join(STATE_DIR, "timeouts.json")
ACTIONS_LOG = os.path.join(LOG_DIR, "actions.log")
GAMEMODES = ("survival", "creative", "adventure", "spectator")
_timeouts_lock = threading.Lock()


def read_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_file(path, data, owner=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-panel"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    if owner:
        give_to_server(tmp)

    os.replace(tmp, path)


def load_timeouts():
    return read_json_file(TIMEOUTS_FILE, {})


def rcon(*args):
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "rcon-cli"] + [str(a) for a in args],
        capture_output=True,
        text=True
    )

    # rcon-cli agrega codigos de color ANSI al final
    output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout).strip()

    return result.returncode == 0, output


def log_action(text):
    try:
        with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " | " + text + "\n")
    except Exception:
        pass


def list_players():
    data = os.path.realpath(DATA_DIR)
    cache = read_json_file(os.path.join(data, "usercache.json"), [])
    ops = read_json_file(os.path.join(data, "ops.json"), [])
    whitelist = read_json_file(os.path.join(data, "whitelist.json"), [])
    bans = read_json_file(os.path.join(data, "banned-players.json"), [])
    timeouts = load_timeouts()

    running, _, _ = container_info()
    online = []

    if running == "true":
        state = autostop_info()
        online = [n for n in state.get("names", []) if isinstance(n, str)]

    players = {}

    def entry(name, uuid=""):
        key = name.lower()

        if key not in players:
            players[key] = {
                "name": name,
                "uuid": uuid,
                "online": False,
                "op": False,
                "op_level": 0,
                "whitelisted": False,
                "ban": None,
                "first_seen": None,
                "last_seen": None,
                "joins": 0
            }

        if uuid and not players[key]["uuid"]:
            players[key]["uuid"] = uuid

        return players[key]

    # El cache puede tener el mismo nombre con varios UUID (modo
    # offline/online); se prefiere el que tiene datos de jugador
    playerdata = os.path.join(data, "world", "playerdata")

    for item in cache:
        name, uuid = item.get("name"), item.get("uuid", "")

        if not name:
            continue

        p = entry(name)

        if os.path.exists(os.path.join(playerdata, uuid + ".dat")) or not p["uuid"]:
            p["uuid"] = uuid

    for item in ops:
        if item.get("name"):
            p = entry(item["name"], item.get("uuid", ""))
            p["op"] = True
            p["op_level"] = item.get("level", 4)

    for item in whitelist:
        if item.get("name"):
            entry(item["name"], item.get("uuid", ""))["whitelisted"] = True

    for item in bans:
        if item.get("name"):
            p = entry(item["name"], item.get("uuid", ""))
            p["ban"] = {
                "reason": item.get("reason", ""),
                "created": item.get("created", ""),
                "source": item.get("source", ""),
                "until": timeouts.get(item["name"].lower())
            }

    for message in chat_history()["messages"]:
        if message["type"] not in ("join", "leave"):
            continue

        p = entry(message["name"])

        if message["type"] == "join":
            p["joins"] += 1
            p["first_seen"] = p["first_seen"] or message["ts"]

        p["last_seen"] = message["ts"]

    for name in online:
        p = entry(name)
        p["online"] = True
        p["last_seen"] = int(time.time())

    ordered = sorted(
        players.values(),
        key=lambda p: (not p["online"], -(p["last_seen"] or 0), p["name"].lower())
    )

    return {
        "running": running == "true",
        "online": online,
        "players": ordered
    }


def player_action(data):
    name = str(data.get("name", ""))
    action = str(data.get("action", ""))

    if not PLAYER_NAME.match(name):
        raise FileError("Nombre de jugador no válido")

    running, _, _ = container_info()

    if running != "true":
        raise FileError("El servidor está apagado")

    def reason_text(default):
        text = re.sub(r"[\x00-\x1f\x7f]", " ", str(data.get("reason", ""))).strip()[:120]
        return text or default

    if action == "kick":
        ok, out = rcon("kick", name, reason_text("Expulsado por un administrador"))

    elif action == "ban":
        ok, out = rcon("ban", name, reason_text("Baneado por un administrador"))

        with _timeouts_lock:
            timeouts = load_timeouts()
            timeouts.pop(name.lower(), None)
            write_json_file(TIMEOUTS_FILE, timeouts)

    elif action == "timeout":
        try:
            minutes = int(data.get("minutes", 0))
        except (TypeError, ValueError):
            minutes = 0

        if not 1 <= minutes <= 60 * 24 * 30:
            raise FileError("Duración no válida")

        until = int(time.time()) + minutes * 60
        ok, out = rcon("ban", name, reason_text("Suspensión temporal"))

        if ok:
            with _timeouts_lock:
                timeouts = load_timeouts()
                timeouts[name.lower()] = until
                write_json_file(TIMEOUTS_FILE, timeouts)

    elif action == "pardon":
        ok, out = rcon("pardon", name)

        with _timeouts_lock:
            timeouts = load_timeouts()
            timeouts.pop(name.lower(), None)
            write_json_file(TIMEOUTS_FILE, timeouts)

    elif action in ("op", "deop"):
        ok, out = rcon(action, name)

    elif action in ("whitelist_add", "whitelist_remove"):
        ok, out = rcon("whitelist", action.split("_")[1], name)

    elif action == "gamemode":
        mode = str(data.get("mode", ""))

        if mode not in GAMEMODES:
            raise FileError("Modo de juego no válido")

        ok, out = rcon("gamemode", mode, name)

    elif action == "message":
        text = re.sub(r"[\x00-\x1f\x7f]", " ", str(data.get("text", ""))).strip()[:240]

        if not text:
            raise FileError("Mensaje vacío")

        payload = json.dumps([
            "",
            {"text": "[Server -> " + name + "] ", "color": "gold"},
            {"text": text}
        ], ensure_ascii=False)

        ok, out = rcon("tellraw", name, payload)

    elif action == "tp":
        target = str(data.get("target", ""))

        if not PLAYER_NAME.match(target):
            raise FileError("Nombre de jugador no válido")

        ok, out = rcon("tp", name, target)

    elif action == "kill":
        ok, out = rcon("kill", name)

    else:
        raise FileError("Acción no válida")

    log_action(action + " " + name + (" | " + out if out else ""))

    if not ok:
        raise FileError("No se pudo ejecutar la acción", 500)

    # Minecraft responde en ingles: se devuelve tal cual para mostrarlo
    failed = re.search(
        r"No player was found|Unknown|Could not|not found|is not|Nothing changed|"
        r"already|Incorrect|Expected",
        out,
        re.I
    )

    return {
        "ok": not failed,
        "message": "Acción aplicada" if not failed else out,
        "output": out
    }


def timeout_loop():
    # Levanta los bans temporales vencidos. Con el servidor apagado se
    # edita banned-players.json directamente (Minecraft lo lee al arrancar).
    bans_file = os.path.join(DATA_DIR, "banned-players.json")

    while True:
        time.sleep(30)

        try:
            with _timeouts_lock:
                timeouts = load_timeouts()
                now = time.time()
                expired = [name for name, until in timeouts.items() if until <= now]

                if not expired:
                    continue

                running, _, _ = container_info()

                for name in expired:
                    if running == "true":
                        ok, out = rcon("pardon", name)
                    else:
                        bans = read_json_file(bans_file, [])
                        bans = [b for b in bans if str(b.get("name", "")).lower() != name]
                        write_json_file(bans_file, bans, owner=True)
                        ok = True

                    if ok:
                        timeouts.pop(name, None)
                        log_action("timeout vencido " + name)

                write_json_file(TIMEOUTS_FILE, timeouts)
        except Exception:
            pass


# ============================================================
# Ajustes del servidor (server.properties)
# ============================================================

PROPERTIES_FILE = os.path.join(DATA_DIR, "server.properties")

# Solo estas claves se pueden leer y cambiar desde el panel. Puertos y
# RCON quedan fuera a proposito: cambiarlos dejaria al panel sin conexion.
SETTINGS = {
    "difficulty": ("enum", ["peaceful", "easy", "normal", "hard"]),
    "gamemode": ("enum", ["survival", "creative", "adventure", "spectator"]),
    "force-gamemode": ("bool", None),
    "hardcore": ("bool", None),
    "pvp": ("bool", None),
    "allow-flight": ("bool", None),
    "enable-command-block": ("bool", None),
    "spawn-protection": ("int", (0, 256)),
    "player-idle-timeout": ("int", (0, 1440)),

    "spawn-monsters": ("bool", None),
    "spawn-animals": ("bool", None),
    "spawn-npcs": ("bool", None),
    "allow-nether": ("bool", None),
    "view-distance": ("int", (3, 32)),
    "simulation-distance": ("int", (3, 32)),

    "max-players": ("int", (1, 200)),
    "white-list": ("bool", None),
    "enforce-whitelist": ("bool", None),
    "online-mode": ("bool", None),
    "hide-online-players": ("bool", None),
    "motd": ("text", 59)
}

# Se aplican al momento por RCON; el resto necesita reiniciar
LIVE_SETTINGS = {
    "difficulty": lambda v: ["difficulty", v],
    "white-list": lambda v: ["whitelist", "on" if v == "true" else "off"]
}


def unescape_property(value):
    def replace(match):
        token = match.group(1)

        if token.startswith("u"):
            return chr(int(token[1:], 16))

        return {"n": "\n", "t": "\t"}.get(token, token)

    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", replace, value)


def escape_property(value):
    out = []

    for ch in value.replace("\\", "\\\\"):
        out.append(ch if 32 <= ord(ch) < 127 else "\\u%04x" % ord(ch))

    return "".join(out)


def read_properties():
    values = {}

    for line in read_lines(PROPERTIES_FILE):
        if line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        values[key.strip()] = unescape_property(value)

    return values


def clean_setting(key, value):
    kind, rule = SETTINGS[key]

    if kind == "bool":
        if value not in (True, False, "true", "false"):
            raise FileError("Valor no válido para " + key)
        return "true" if value in (True, "true") else "false"

    if kind == "enum":
        if value not in rule:
            raise FileError("Valor no válido para " + key)
        return value

    if kind == "int":
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise FileError("Valor no válido para " + key)

        if not rule[0] <= number <= rule[1]:
            raise FileError(
                "%s debe estar entre %d y %d" % (key, rule[0], rule[1])
            )

        return str(number)

    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value)).strip()

    if len(text) > rule:
        raise FileError("%s admite hasta %d caracteres" % (key, rule))

    return text


def get_settings():
    values = read_properties()
    running, _, _ = container_info()

    return {
        "running": running == "true",
        "values": {k: values.get(k, "") for k in SETTINGS},
        "live": list(LIVE_SETTINGS)
    }


def save_settings(changes):
    if not isinstance(changes, dict) or not changes:
        raise FileError("No hay cambios que guardar")

    if not os.path.isfile(PROPERTIES_FILE):
        raise FileError("No existe server.properties", 404)

    current = read_properties()
    updates = {}

    for key, value in changes.items():
        if key not in SETTINGS:
            raise FileError("Ajuste no permitido: " + str(key), 403)

        cleaned = clean_setting(key, value)

        if current.get(key) != cleaned:
            updates[key] = cleaned

    if not updates:
        return {"ok": True, "message": "Sin cambios", "changed": [], "restart": False}

    # Se reescriben solo las lineas cambiadas; el resto queda intacto
    with open(PROPERTIES_FILE, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    pending = dict(updates)

    for i, line in enumerate(lines):
        if line.startswith("#") or "=" not in line:
            continue

        key = line.partition("=")[0].strip()

        if key in pending:
            lines[i] = key + "=" + escape_property(pending.pop(key))

    for key, value in pending.items():
        lines.append(key + "=" + escape_property(value))

    mode = os.stat(PROPERTIES_FILE).st_mode & 0o7777
    tmp = PROPERTIES_FILE + ".tmp-panel"

    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    os.chmod(tmp, mode)
    give_to_server(tmp)
    os.replace(tmp, PROPERTIES_FILE)

    running, _, _ = container_info()
    applied = []

    if running == "true":
        for key, value in updates.items():
            if key not in LIVE_SETTINGS:
                continue

            result = subprocess.run(
                ["docker", "exec", CONTAINER, "rcon-cli"] + LIVE_SETTINGS[key](value),
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                applied.append(key)

    return {
        "ok": True,
        "message": "Ajustes guardados",
        "changed": sorted(updates),
        "applied": applied,
        # Con el servidor apagado todo se aplica en el proximo arranque
        "restart": running == "true" and any(k not in applied for k in updates)
    }


# ============================================================
# Respaldos
# ============================================================

BACKUP_NAME = re.compile(r"^mc-(auto|manual)-(\d{8}-\d{6})\.tar\.gz$")
BACKUP_LOG = os.path.join(LOG_DIR, "backup.log")


def backup_running():
    return command(
        "systemctl is-active mcpanel-backup@manual.service mcpanel-backup@auto.service"
    ).split().count("active") > 0


def list_backups():
    backups = []

    if os.path.isdir(BACKUP_DIR):
        for name in os.listdir(BACKUP_DIR):
            m = BACKUP_NAME.match(name)

            if not m:
                continue

            st = os.stat(os.path.join(BACKUP_DIR, name))

            backups.append({
                "name": name,
                "type": m.group(1),
                "size": st.st_size,
                "mtime": int(st.st_mtime)
            })

    backups.sort(key=lambda b: b["mtime"], reverse=True)

    # Mantiene al dia la grafica de almacenamiento sin esperar al du
    with _stats_lock:
        _stats["backup_size"] = sum(b["size"] for b in backups)

    timer = command(
        "systemctl show mcpanel-backup.timer -p NextElapseUSecRealtime --value"
    )

    next_ts = None

    try:
        next_ts = int(
            subprocess.run(
                ["date", "-d", timer, "+%s"],
                capture_output=True,
                text=True
            ).stdout.strip()
        )
    except Exception:
        pass

    log_lines = read_lines(BACKUP_LOG)

    return {
        "running": backup_running(),
        "next_auto": next_ts,
        "last_log": log_lines[-1] if log_lines else "",
        "backups": backups
    }


def start_backup():
    if backup_running():
        raise FileError("Ya hay un respaldo en curso")

    result = subprocess.run(
        ["systemctl", "start", "--no-block", "mcpanel-backup@manual.service"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise FileError("No se pudo iniciar el respaldo: " + result.stderr.strip(), 500)

    return {"ok": True, "message": "Respaldo iniciado"}


def backup_path(name):
    if not BACKUP_NAME.match(name or ""):
        raise FileError("Respaldo no válido", 404)

    full = os.path.join(BACKUP_DIR, name)

    if not os.path.isfile(full):
        raise FileError("El respaldo no existe", 404)

    return full


def delete_backup(name):
    os.remove(backup_path(name))
    return {"ok": True, "message": "Respaldo eliminado"}


# ============================================================
# Desinstalar
# ============================================================


def start_uninstall(data):
    confirm = str(data.get("confirm", "")).strip()

    if confirm != SERVER_NAME:
        raise FileError("El nombre no coincide")

    script = os.path.join(INSTALL_DIR, "uninstall.sh")

    if not os.path.isfile(script):
        raise FileError("No se encontró uninstall.sh", 404)

    args = [script, "--yes"]

    if data.get("purge_data"):
        args.append("--purge-data")

    if data.get("purge_backups"):
        args.append("--purge-backups")

    log_action("desinstalar " + " ".join(args[1:]))

    # Corre fuera de este servicio, que se va a detener y borrar
    result = subprocess.run(
        ["systemd-run", "--unit", "mcpanel-uninstall-%d" % int(time.time()),
         "--collect", "--quiet"] + args,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise FileError("No se pudo iniciar la desinstalación: " + result.stderr.strip(), 500)

    return {"ok": True, "message": "Desinstalando"}
HTML = r"""
<!DOCTYPE html>
<html lang="es">

<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>__SERVER_NAME__</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2016%2016%22%20shape-rendering%3D%22crispEdges%22%3E%3Crect%20width%3D%2216%22%20height%3D%2216%22%20rx%3D%223%22%20fill%3D%22%238a5a3b%22%2F%3E%3Cpath%20fill%3D%22%237a4e33%22%20d%3D%22M2%208h2v2H2zM9%209h2v2H9zM5%2012h2v2H5zM12%2012h2v2h-2zM7%207h1v1H7z%22%2F%3E%3Cpath%20fill%3D%22%23936240%22%20d%3D%22M11%207h2v1h-2zM3%2011h1v1H3zM9%2013h2v1H9z%22%2F%3E%3Cpath%20fill%3D%22%235fbf3f%22%20d%3D%22M3%200h10a3%203%200%200%201%203%203v3H0V3a3%203%200%200%201%203-3z%22%2F%3E%3Cpath%20fill%3D%22%234ea634%22%20d%3D%22M0%205h3v2H0zM6%205h2v3H6zM11%205h3v2h-3zM4%202h2v2H4zM10%201h2v2h-2z%22%2F%3E%3Cpath%20fill%3D%22%2362c444%22%20d%3D%22M8%202h2v2H8zM1%203h2v1H1zM13%203h2v1h-2z%22%2F%3E%3C%2Fsvg%3E">

<script>
try {
    var savedTheme = localStorage.getItem("mc-theme");
    document.documentElement.dataset.theme =
        savedTheme === "light" || savedTheme === "dark" ? savedTheme
        : (window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
} catch (e) {
    document.documentElement.dataset.theme = "dark";
}
</script>

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">

<style>

:root {
    color-scheme: dark;

    --on-green: #062b13;
    --green-hover: #6ee7a0;
    --on-blue: #06172e;
    --blue-hover: #7db6fb;
    --on-red: #2b0606;
    --red-hover: #fb8f8f;
    --on-amber: #2b1d02;
    --amber-hover: #fcd34d;
    --chart-cpu: #4ade80;
    --chart-mem: #60a5fa;

    --bg: #0a0d0b;
    --surface: #121614;
    --surface-2: #181d1a;
    --border: #232a26;
    --border-strong: #2f3833;
    --text: #e7ece9;
    --muted: #87928c;
    --dim: #5b655f;

    --green: #4ade80;
    --green-bg: rgba(74, 222, 128, .10);
    --amber: #fbbf24;
    --amber-bg: rgba(251, 191, 36, .10);
    --red: #f87171;
    --red-bg: rgba(248, 113, 113, .10);
    --blue: #60a5fa;
    --blue-bg: rgba(96, 165, 250, .10);

    --radius: 14px;
    --sans: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
    --mono: "JetBrains Mono", Consolas, "Cascadia Code", monospace;
}

* {
    box-sizing: border-box;
}

html, body {
    margin: 0;
    background: var(--bg);
}

body {
    min-height: 100vh;
    color: var(--text);
    font-family: var(--sans);
    font-size: 14px;
    -webkit-font-smoothing: antialiased;
    background:
        radial-gradient(900px 520px at 12% -8%, rgba(74, 222, 128, .10), transparent 62%),
        radial-gradient(820px 520px at 92% 0%, rgba(96, 165, 250, .08), transparent 60%),
        radial-gradient(900px 620px at 50% 112%, rgba(167, 139, 250, .06), transparent 60%),
        linear-gradient(180deg, #0b0f0d 0%, #090c0f 100%);
    background-attachment: fixed;
}

.container {
    max-width: 1280px;
    margin: 0 auto;
    padding: 28px 16px 60px;
}

svg {
    width: 16px;
    height: 16px;
    flex: none;
}

/* ---------- Header ---------- */

header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    margin-bottom: 22px;
}

.brand {
    display: flex;
    align-items: center;
    gap: 14px;
}

.logo {
    width: 42px;
    height: 42px;
    border-radius: 10px;
    overflow: hidden;
    display: grid;
    grid-template-rows: 11px 1fr;
    box-shadow: 0 0 0 1px var(--border-strong), 0 6px 18px rgba(0,0,0,.35);
}

.logo .grass {
    background:
        linear-gradient(90deg, #5fbf3f 0 25%, #4ea634 25% 50%, #62c444 50% 75%, #54ad38 75%);
}

.logo .dirt {
    background:
        linear-gradient(90deg, #8a5a3b 0 33%, #7a4e33 33% 66%, #936240 66%);
}

h1 {
    margin: 0;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -.01em;
}

.subtitle {
    color: var(--muted);
    font-size: 13px;
    margin-top: 2px;
}

.pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 7px 12px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--muted);
    white-space: nowrap;
}

.dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--dim);
    flex: none;
}

.is-green { color: var(--green); }
.is-amber { color: var(--amber); }
.is-red { color: var(--red); }

.is-green .dot, .dot.is-green { background: var(--green); box-shadow: 0 0 0 4px var(--green-bg); }
.is-amber .dot, .dot.is-amber { background: var(--amber); box-shadow: 0 0 0 4px var(--amber-bg); }
.is-red .dot, .dot.is-red { background: var(--red); box-shadow: 0 0 0 4px var(--red-bg); }

.pulse .dot {
    animation: pulse 1.6s ease-in-out infinite;
}

@keyframes pulse {
    50% { opacity: .45; }
}

/* ---------- Cards ---------- */

.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 14px;
}

.card-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
}

.card-title {
    display: flex;
    align-items: center;
    gap: 9px;
    font-size: 14px;
    font-weight: 600;
    margin: 0;
}

.card-title svg {
    color: var(--muted);
}

.hint {
    color: var(--dim);
    font-size: 12px;
}

/* ---------- Hero ---------- */

.hero {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 20px;
    flex-wrap: wrap;
    padding: 24px;
}

.status {
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -.02em;
    display: flex;
    align-items: center;
    gap: 12px;
}

.status .dot {
    width: 11px;
    height: 11px;
}

.address {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
    padding: 6px 8px 6px 12px;
    border-radius: 8px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    font-family: var(--mono);
    font-size: 13px;
    color: var(--muted);
}

.icon-btn {
    display: inline-grid;
    place-items: center;
    width: 26px;
    height: 26px;
    border-radius: 6px;
    border: 0;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    padding: 0;
}

.icon-btn:hover {
    background: var(--border);
    color: var(--text);
}

.icon-btn svg {
    width: 14px;
    height: 14px;
}

/* ---------- Online players ---------- */

.online {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 18px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    width: 100%;
}

.online-label {
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    margin-right: 4px;
}

.online-empty {
    color: var(--dim);
    font-size: 13px;
}

.player {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 4px 12px 4px 4px;
    border-radius: 999px;
    background: var(--green-bg);
    border: 1px solid rgba(74, 222, 128, .22);
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
}

.avatar {
    position: relative;
    width: 24px;
    height: 24px;
    border-radius: 6px;
    overflow: hidden;
    display: grid;
    place-items: center;
    background: #2a3a30;
    color: var(--green);
    font-size: 11px;
    font-weight: 700;
    image-rendering: pixelated;
}

.avatar img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
}

/* ---------- Buttons ---------- */

.buttons {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 10px 16px;
    font-family: inherit;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: background .15s, border-color .15s, opacity .15s, transform .05s;
}

.btn:active:not(:disabled) {
    transform: translateY(1px);
}

.btn:disabled {
    opacity: .35;
    cursor: not-allowed;
}

.btn-start {
    background: var(--green);
    color: var(--on-green);
}

.btn-start:hover:not(:disabled) {
    background: var(--green-hover);
}

.btn-stop {
    background: var(--red-bg);
    color: var(--red);
    border-color: rgba(248, 113, 113, .25);
}

.btn-stop:hover:not(:disabled) {
    background: rgba(248, 113, 113, .18);
}

.btn-ghost {
    background: var(--surface-2);
    color: var(--text);
    border-color: var(--border-strong);
}

.btn-ghost:hover:not(:disabled) {
    background: var(--border);
}

.btn-small {
    padding: 6px 11px;
    font-size: 12px;
    border-radius: 8px;
}

/* ---------- Stats ---------- */

.grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-bottom: 14px;
}

.stat {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
}

.label {
    display: flex;
    align-items: center;
    gap: 7px;
    color: var(--muted);
    font-size: 12px;
    font-weight: 500;
    margin-bottom: 10px;
}

.label svg {
    width: 14px;
    height: 14px;
}

.value {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -.01em;
    font-variant-numeric: tabular-nums;
}

.value-sub {
    color: var(--dim);
    font-size: 12px;
    margin-top: 4px;
}

/* ---------- Autostop ---------- */

.autostop {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 20px;
    flex-wrap: wrap;
}

.autostop-description {
    color: var(--muted);
    font-size: 13px;
    margin-top: 6px;
}

.timer {
    font-family: var(--mono);
    font-size: 32px;
    font-weight: 700;
    text-align: right;
    font-variant-numeric: tabular-nums;
    line-height: 1;
}

.timer-label {
    color: var(--dim);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .08em;
    text-transform: uppercase;
    text-align: right;
    margin-top: 6px;
}

.progress {
    height: 6px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 99px;
    overflow: hidden;
    margin-top: 18px;
}

.progress-bar {
    height: 100%;
    width: 0%;
    border-radius: 99px;
    background: var(--green);
    transition: width .25s linear, background .3s;
}

/* ---------- Console ---------- */

.console-wrap {
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    background: #070908;
}

/* Consola y chat comparten altura para que la tarjeta no cambie
   de tamano al alternar pestanas */
.console-wrap {
    --pane-height: 460px;
}

.console {
    height: var(--pane-height);
    overflow-y: auto;
    padding: 14px 16px;
    font-family: var(--mono);
    font-size: 12px;
    line-height: 1.65;
    color: #c9d1cc;
}

.console::-webkit-scrollbar {
    width: 10px;
}

.console::-webkit-scrollbar-thumb {
    background: #2f3833;
    border-radius: 10px;
    border: 3px solid #070908;
}

.line {
    white-space: pre-wrap;
    word-break: break-word;
}

.line .t { color: #5b655f; }
.line .src { color: #6b7a72; }
.line .lvl { font-weight: 700; }
.lvl-INFO { color: #7dd3a8; }
.lvl-WARN { color: #fbbf24; }
.lvl-ERROR, .lvl-FATAL { color: #f87171; }
.line.warn .msg { color: #f3dca0; }
.line.error .msg { color: #fca5a5; }
.line.chat .msg { color: #60a5fa; }

.console-empty {
    color: #5b655f;
}

.command {
    display: flex;
    align-items: center;
    gap: 10px;
    height: 50px;
    box-sizing: border-box;
    border-top: 1px solid var(--border);
    background: var(--surface-2);
    padding: 8px 8px 8px 16px;
}

.prompt {
    color: var(--green);
    font-family: var(--mono);
    font-weight: 700;
}

.command input {
    flex: 1;
    min-width: 0;
    background: transparent;
    color: var(--text);
    border: 0;
    outline: none;
    padding: 8px 0;
    font-family: var(--mono);
    font-size: 13px;
}

.command[hidden] {
    display: none;
}

.prompt.lock {
    color: var(--muted);
    display: grid;
    place-items: center;
}

.command input::placeholder {
    color: var(--dim);
}

.btn-send {
    background: var(--blue);
    color: var(--on-blue);
}

.btn-send:hover {
    background: var(--blue-hover);
}

/* ---------- Activity ---------- */

.events {
    display: flex;
    flex-direction: column;
    max-height: 440px;
    overflow-y: auto;
}

.event {
    display: grid;
    grid-template-columns: 150px 1fr;
    gap: 14px;
    align-items: center;
    padding: 10px 0;
    border-top: 1px solid var(--border);
    font-size: 13px;
}

.event:first-child {
    border-top: 0;
    padding-top: 0;
}

.event-time {
    color: var(--dim);
    font-family: var(--mono);
    font-size: 12px;
}

.event-body {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
}

.event-text {
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.tag {
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 6px;
    white-space: nowrap;
    background: var(--surface-2);
    color: var(--muted);
    border: 1px solid var(--border);
}

.tag.green { background: var(--green-bg); color: var(--green); border-color: transparent; }
.tag.blue { background: var(--blue-bg); color: var(--blue); border-color: transparent; }
.tag.red { background: var(--red-bg); color: var(--red); border-color: transparent; }
.tag.amber { background: var(--amber-bg); color: var(--amber); border-color: transparent; }

/* ---------- Toast ---------- */

.toast {
    position: fixed;
    left: 50%;
    bottom: 24px;
    transform: translate(-50%, 20px);
    opacity: 0;
    pointer-events: none;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 11px 16px;
    border-radius: 10px;
    background: var(--surface-2);
    border: 1px solid var(--border-strong);
    box-shadow: 0 12px 30px rgba(0,0,0,.45);
    font-size: 13px;
    font-weight: 500;
    transition: opacity .2s, transform .2s;
    max-width: calc(100vw - 32px);
}

.toast.show {
    opacity: 1;
    transform: translate(-50%, 0);
}

/* ---------- Tema claro ---------- */

:root[data-theme="light"] {
    color-scheme: light;

    --bg: #eef2ef;
    --surface: #ffffff;
    --surface-2: #f5f7f6;
    --border: #dfe5e1;
    --border-strong: #c9d2cd;
    --text: #17211c;
    --muted: #5a6660;
    --dim: #87928c;

    --green: #15803d;
    --green-bg: rgba(21, 128, 61, .10);
    --amber: #b45309;
    --amber-bg: rgba(180, 83, 9, .10);
    --red: #dc2626;
    --red-bg: rgba(220, 38, 38, .09);
    --blue: #2563eb;
    --blue-bg: rgba(37, 99, 235, .09);

    --on-green: #ffffff;
    --green-hover: #166534;
    --on-blue: #ffffff;
    --blue-hover: #1d4ed8;
    --on-red: #ffffff;
    --red-hover: #b91c1c;
    --on-amber: #ffffff;
    --amber-hover: #92400e;
    --chart-cpu: #16a34a;
    --chart-mem: #2563eb;

    /* Mismos tonos categoricos, en su paso para fondo claro */
    --part-server: #2a78d6;
    --part-backups: #eb6834;
    --part-docker: #1baf7a;
    --part-swap: #eda100;
    --part-system: #9aa39e;
    --part-reserved: repeating-linear-gradient(135deg, #c3cbc6 0 3px, #e6ebe8 3px 6px);
}

:root[data-theme="light"] body {
    background:
        radial-gradient(900px 520px at 10% -8%, rgba(34, 197, 94, .14), transparent 62%),
        radial-gradient(820px 520px at 92% 0%, rgba(59, 130, 246, .11), transparent 60%),
        radial-gradient(900px 620px at 50% 112%, rgba(168, 85, 247, .07), transparent 60%),
        linear-gradient(180deg, #f4f8f5 0%, #eef1f7 100%);
    background-attachment: fixed;
}

:root[data-theme="light"] .modal {
    background: rgba(20, 30, 25, .35);
}

:root[data-theme="light"] .card,
:root[data-theme="light"] .stat {
    box-shadow: 0 1px 2px rgba(20, 30, 25, .04);
}

/* ---------- Chat ---------- */

#consoleTools,
#chatTools:not([hidden]) {
    min-height: 30px;
    display: flex;
    align-items: center;
}

.chat {
    height: var(--pane-height);
    overflow-y: auto;
    padding: 10px 12px 14px;
    background: var(--surface);
    display: flex;
    flex-direction: column;
    gap: 1px;
    font-size: 13.5px;
}

.chat[hidden] {
    display: none;
}

.chat-empty {
    margin: auto;
    color: var(--dim);
}

.chat-day {
    align-self: center;
    margin: 14px 0 8px;
    padding: 3px 12px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--surface-2);
    color: var(--muted);
    font-size: 11.5px;
    font-weight: 600;
}

.chat-day:first-child {
    margin-top: 4px;
}

.chat-msg {
    display: grid;
    grid-template-columns: 48px 24px minmax(0, 1fr);
    gap: 10px;
    align-items: start;
    padding: 5px 8px;
    border-radius: 8px;
}

.chat-msg:hover {
    background: var(--surface-2);
}

.chat-time {
    color: var(--dim);
    font-family: var(--mono);
    font-size: 11.5px;
    padding-top: 3px;
    font-variant-numeric: tabular-nums;
}

.chat-avatar {
    width: 24px;
    height: 24px;
}

.chat-avatar.server {
    background: var(--green-bg);
    color: var(--green);
}

.chat-body {
    line-height: 1.5;
    overflow-wrap: anywhere;
}

.chat-name {
    font-weight: 700;
    margin-right: 8px;
    color: var(--text);
}

.chat-say .chat-name {
    color: var(--green);
}

.chat-text {
    color: var(--text);
}

.chat-sys {
    grid-template-columns: 48px 24px minmax(0, 1fr);
    padding-top: 3px;
    padding-bottom: 3px;
}

.chat-sys .chat-text {
    color: var(--muted);
    font-size: 12.5px;
    padding-top: 1px;
}

.chat-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    margin: 8px auto 0;
    background: var(--dim);
}

.chat-join .chat-dot { background: var(--green); }
.chat-leave .chat-dot { background: var(--amber); }
.chat-advancement .chat-dot { background: var(--blue); }

.chat-prompt {
    color: var(--blue);
    display: grid;
    place-items: center;
}

.badge {
    display: inline-grid;
    place-items: center;
    min-width: 17px;
    height: 17px;
    padding: 0 5px;
    border-radius: 999px;
    background: var(--green);
    color: var(--on-green);
    font-size: 10.5px;
    font-weight: 700;
}

.badge[hidden] {
    display: none;
}

/* ---------- Paneles chat / consola ---------- */

.pane-tabs {
    display: none;
    margin-bottom: 14px;
}

.panes {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 16px;
}

.pane {
    min-width: 0;
}

.pane-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    min-height: 30px;
    margin-bottom: 12px;
}

@media (max-width: 899px) {

    .pane-tabs {
        display: inline-flex;
    }

    .panes {
        grid-template-columns: 1fr;
    }

    .panes[data-pane="chat"] .pane-console,
    .panes[data-pane="console"] .pane-chat {
        display: none;
    }

    .pane-head .card-title {
        display: none;
    }

    .pane-head {
        justify-content: flex-end;
    }

    .pane-head:has(> .hint:empty) {
        display: none;
    }
}

/* ---------- Gestor de archivos ---------- */

.fm {
    position: relative;
}

.fm-nav {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
}

.fm-nav .breadcrumb {
    flex: 1;
    min-width: 0;
    margin: 0;
}

.fm-up {
    width: 32px;
    height: 32px;
    flex: none;
    border-radius: 8px;
    border: 1px solid var(--border-strong);
    background: var(--surface-2);
    color: var(--text);
}

.fm-up:disabled {
    opacity: .35;
    cursor: not-allowed;
}

/* .fm-nav delante: .input (mas abajo) fija width: 100% */
.fm-nav .fm-filter {
    width: 210px;
    flex: 0 0 210px;
    padding: 7px 11px;
    font-size: 13px;
}

.fm-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    padding: 8px 8px 8px 14px;
    margin-bottom: 12px;
    border-radius: 10px;
    background: var(--blue-bg);
    border: 1px solid color-mix(in srgb, var(--blue) 35%, transparent);
    animation: rise .2s ease both;
}

.fm-bar[hidden] {
    display: none;
}

.fm-bar-move {
    background: var(--amber-bg);
    border-color: color-mix(in srgb, var(--amber) 40%, transparent);
}

.fm-bar-text {
    font-size: 13px;
    font-weight: 600;
}

.fm-drop {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 14px;
    margin-bottom: 12px;
    border: 1.5px dashed var(--border-strong);
    border-radius: 12px;
    background: transparent;
    color: var(--muted);
    font-family: inherit;
    font-size: 13px;
    cursor: pointer;
    transition: border-color .15s, color .15s, background .15s;
}

.fm-drop:hover {
    border-color: var(--green);
    color: var(--text);
    background: var(--green-bg);
}

.fm-drop svg {
    width: 18px;
    height: 18px;
}

/* Aviso flotante mientras se arrastra un archivo del equipo */
.fm-overlay {
    position: sticky;
    bottom: 16px;
    z-index: 5;
    display: none;
    align-items: center;
    gap: 10px;
    width: fit-content;
    max-width: 100%;
    margin: 14px auto 0;
    padding: 11px 18px;
    border-radius: 999px;
    background: var(--green);
    color: var(--on-green);
    font-size: 13.5px;
    font-weight: 700;
    box-shadow: 0 12px 30px rgba(0, 0, 0, .3);
    pointer-events: none;
    animation: rise .18s ease both;
}

.fm.dragging .fm-overlay {
    display: flex;
}

/* Al arrastrar, todo el explorador se marca como zona para soltar */
.fm.dragging::after {
    content: "";
    position: absolute;
    inset: -1px;
    z-index: 4;
    border: 2px dashed var(--green);
    border-radius: var(--radius);
    background: color-mix(in srgb, var(--green) 9%, transparent);
    pointer-events: none;
    animation: fade .15s ease both;
}

.fm-hint {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin-top: 14px;
    color: var(--dim);
    font-size: 12.5px;
}

.fm-hint svg {
    width: 14px;
    height: 14px;
}

.files .row {
    grid-template-columns: 18px 24px minmax(0, 1fr) 100px 150px 118px;
    user-select: none;
    transition: background .12s;
}

.files .row-head {
    background: var(--surface-2);
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    padding-top: 8px;
    padding-bottom: 8px;
}

#fileList .row:first-child {
    border-top: 1px solid var(--border);
}

.col-btn {
    border: 0;
    padding: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
}

.col-btn.row-size {
    text-align: right;
}

.col-btn:hover {
    color: var(--text);
}

.sort-mark {
    color: var(--green);
}

.check {
    width: 16px;
    height: 16px;
    margin: 0;
    accent-color: var(--green);
    cursor: pointer;
}

.files .row.selected,
.files .row.selected:hover {
    background: var(--blue-bg);
}

.files .row-actions {
    opacity: .8;
}

.row.drop-target,
.breadcrumb a.drop-target {
    outline: 2px dashed var(--green);
    outline-offset: -2px;
    background: var(--green-bg);
}

@media (max-width: 700px) {

    .files .row {
        grid-template-columns: 18px 22px minmax(0, 1fr) auto;
    }

    .fm-nav {
        flex-wrap: wrap;
    }

    .fm-nav .fm-filter {
        width: 100%;
        flex: 1 1 100%;
    }
}

/* ---------- Ajustes ---------- */

.set-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 20px;
    padding: 14px 0;
    border-top: 1px solid var(--border);
}

.set-row:first-child {
    border-top: 0;
    padding-top: 0;
}

.set-row:last-child {
    padding-bottom: 0;
}

.set-text {
    min-width: 0;
}

.set-label {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    font-size: 14px;
    font-weight: 600;
}

.set-desc {
    color: var(--muted);
    font-size: 12.5px;
    line-height: 1.45;
    margin-top: 3px;
}

/* .set-row delante: .input fija width: 100% */
.set-row .set-input {
    width: 170px;
    flex: none;
    padding: 8px 11px;
    font-size: 13px;
}

.set-row .set-input.wide {
    width: 300px;
}

.set-input.invalid {
    border-color: var(--red);
}

.switch {
    position: relative;
    flex: none;
    width: 44px;
    height: 24px;
    padding: 0;
    border-radius: 999px;
    border: 1px solid var(--border-strong);
    background: var(--surface-2);
    cursor: pointer;
    transition: background-color .18s ease, border-color .18s ease;
}

.switch-knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--muted);
    transition: transform .18s ease, background-color .18s ease;
}

.switch.on {
    background: var(--green);
    border-color: var(--green);
}

.switch.on .switch-knob {
    transform: translateX(20px);
    background: var(--on-green);
}

.set-bar {
    position: sticky;
    bottom: 16px;
    z-index: 6;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    padding: 10px 10px 10px 16px;
    border-radius: 12px;
    background: var(--surface-2);
    border: 1px solid var(--border-strong);
    box-shadow: 0 14px 34px rgba(0, 0, 0, .35);
    animation: rise .2s ease both;
}

.set-bar[hidden],
.set-note[hidden] {
    display: none;
}

.set-note {
    margin-bottom: 14px;
    padding: 10px 14px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--muted);
    font-size: 13px;
}

@media (max-width: 600px) {

    .set-row {
        flex-direction: column;
        align-items: flex-start;
        gap: 10px;
    }

    .set-row .set-input,
    .set-row .set-input.wide {
        width: 100%;
    }
}

/* ---------- Jugadores ---------- */

.pl-head {
    flex-wrap: wrap;
}

.pl-head .card-title .hint {
    font-weight: 500;
    margin-left: 4px;
}

.pl-tools {
    flex-wrap: wrap;
}

.pl-filters .tab-btn {
    padding: 6px 11px;
    font-size: 12.5px;
}

.toolbar .pl-search {
    width: 190px;
    padding: 7px 11px;
    font-size: 13px;
}

.pl-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 10px;
}

.pl-list .list-empty {
    grid-column: 1 / -1;
}

.pl-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: var(--surface-2);
    cursor: pointer;
    transition: border-color .15s ease, transform .15s ease, background-color .25s ease;
}

.pl-row:hover {
    border-color: var(--border-strong);
    transform: translateY(-1px);
}

.pl-avatar {
    position: relative;
    width: 40px;
    height: 40px;
    flex: none;
    overflow: visible;
    border-radius: 8px;
}

.pl-avatar img {
    border-radius: 8px;
}

.pl-dot {
    position: absolute;
    right: -3px;
    bottom: -3px;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--dim);
    border: 2px solid var(--surface-2);
}

.pl-row.online .pl-dot {
    background: var(--green);
}

.pl-info {
    flex: 1;
    min-width: 0;
}

.pl-name {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    font-weight: 700;
    font-size: 14px;
}

.pl-badges {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 4px;
}

.pl-badges .tag {
    font-size: 10.5px;
    padding: 2px 6px;
}

.pl-sub {
    color: var(--muted);
    font-size: 12.5px;
    margin-top: 2px;
}

.pl-sub.is-green {
    color: var(--green);
}

.pl-actions {
    display: flex;
    align-items: center;
    gap: 4px;
}

/* Ficha del jugador */

.modal-box.player-modal {
    max-width: 880px;
}

.pl-sheet {
    display: grid;
    grid-template-columns: 240px minmax(0, 1fr);
    gap: 22px;
    color: var(--text);
    overflow-y: auto;
    max-height: calc(100vh - 170px);
}

.pl-side {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    text-align: center;
}

.pl-skin {
    width: 220px;
    height: 300px;
    border-radius: 14px;
    background:
        radial-gradient(circle at 50% 35%, var(--green-bg), transparent 65%),
        var(--surface-2);
    border: 1px solid var(--border);
    display: grid;
    place-items: center;
    cursor: grab;
    overflow: hidden;
}

.pl-skin:active {
    cursor: grabbing;
}

.pl-skin canvas {
    display: block;
}

.pl-skin-2d {
    max-height: 260px;
    image-rendering: pixelated;
}

.pl-sheet-name {
    font-size: 19px;
    font-weight: 800;
    margin-top: 8px;
}

.pl-facts {
    width: 100%;
    margin-top: 10px;
    border-top: 1px solid var(--border);
    padding-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.pl-fact {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    font-size: 12px;
    color: var(--muted);
}

.pl-fact b {
    color: var(--text);
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 150px;
}

.pl-panel {
    display: flex;
    flex-direction: column;
    gap: 14px;
    min-width: 0;
}

.pl-panel .set-note {
    margin: 0;
}

.pl-section {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: var(--surface-2);
}

.pl-section-title {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .05em;
    text-transform: uppercase;
    color: var(--muted);
}

.pl-section .input {
    padding: 8px 11px;
    font-size: 13px;
}

.pl-inline {
    display: flex;
    align-items: center;
    gap: 8px;
}

.pl-inline .input {
    flex: 1;
    min-width: 0;
}

.pl-inline-label {
    font-size: 13px;
    color: var(--muted);
    white-space: nowrap;
}

.pl-modes {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.pl-modes .pl-timeout {
    width: auto;
    padding: 6px 8px;
}

.pl-hint {
    font-size: 12px;
    color: var(--muted);
}

.pl-role {
    padding: 4px 0 !important;
    border: 0;
}

.btn.armed {
    box-shadow: 0 0 0 2px var(--red);
}

.btn:disabled,
.switch:disabled {
    opacity: .4;
    cursor: not-allowed;
}

@media (max-width: 760px) {

    .pl-sheet {
        grid-template-columns: 1fr;
    }

    .toolbar .pl-search {
        width: 100%;
    }
}

/* ---------- Desinstalar ---------- */

.danger-zone {
    border-color: color-mix(in srgb, var(--red) 35%, var(--border));
}

.un-check {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text);
    cursor: pointer;
}

.un-check input {
    accent-color: var(--red);
    width: 16px;
    height: 16px;
}

.un-done {
    max-width: 480px;
    margin: 18vh auto;
    padding: 0 16px;
    text-align: center;
    color: var(--text);
}

/* ---------- Animaciones ---------- */

@keyframes rise {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: none; }
}

@keyframes fade {
    from { opacity: 0; }
    to { opacity: 1; }
}

@keyframes pop {
    from { opacity: 0; transform: scale(.96) translateY(6px); }
    to { opacity: 1; transform: none; }
}

/* Entrada escalonada al abrir la pagina o cambiar de pestana */
.tab-page:not([hidden]) > * {
    animation: rise .45s cubic-bezier(.2, .7, .2, 1) both;
}

.tab-page > *:nth-child(2) { animation-delay: .05s; }
.tab-page > *:nth-child(3) { animation-delay: .10s; }
.tab-page > *:nth-child(4) { animation-delay: .15s; }
.tab-page > *:nth-child(5) { animation-delay: .20s; }
.tab-page > *:nth-child(n+6) { animation-delay: .25s; }

header {
    animation: fade .5s ease both;
}

.modal:not([hidden]) {
    animation: fade .18s ease both;
}

.modal:not([hidden]) .modal-box {
    animation: pop .22s cubic-bezier(.2, .7, .2, 1) both;
}

.player {
    animation: pop .25s ease both;
}

.stat,
.resource {
    transition: transform .18s ease, border-color .18s ease, background-color .25s ease;
}

.stat:hover {
    transform: translateY(-2px);
    border-color: var(--border-strong);
}

.tab-btn,
.lang-btn,
.icon-btn {
    transition: background-color .15s ease, color .15s ease, box-shadow .15s ease;
}

.row {
    transition: background-color .12s ease;
}

/* Cambio suave entre tema claro y oscuro */
body,
.card,
.stat,
.resource,
.pill,
.tabs,
.lang-switch,
.list,
.command,
.chat,
.input {
    transition: background-color .25s ease, border-color .25s ease, color .25s ease;
}

.status .dot {
    transition: background-color .3s ease, box-shadow .3s ease;
}

.is-green.status .dot {
    animation: glow 2.4s ease-in-out infinite;
}

@keyframes glow {
    50% { box-shadow: 0 0 0 7px transparent; }
}

@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        animation: none !important;
        transition: none !important;
    }
}

/* ---------- Idioma ---------- */

.lang-switch {
    display: inline-flex;
    padding: 3px;
    gap: 2px;
    border-radius: 999px;
    background: var(--surface);
    border: 1px solid var(--border);
}

.lang-btn {
    border: 0;
    border-radius: 999px;
    padding: 5px 9px;
    background: transparent;
    color: var(--muted);
    font-family: inherit;
    font-size: 11.5px;
    font-weight: 700;
    letter-spacing: .04em;
    cursor: pointer;
}

.lang-btn:hover {
    color: var(--text);
}

.lang-btn.active {
    background: var(--surface-2);
    color: var(--text);
    box-shadow: 0 0 0 1px var(--border-strong);
}

/* ---------- Tabs ---------- */

.header-right {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}

.tabs {
    display: inline-flex;
    padding: 3px;
    gap: 2px;
    border-radius: 11px;
    background: var(--surface);
    border: 1px solid var(--border);
}

.tab-btn {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    border: 0;
    border-radius: 8px;
    padding: 7px 13px;
    background: transparent;
    color: var(--muted);
    font-family: inherit;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
}

.tab-btn svg {
    width: 14px;
    height: 14px;
}

.tab-btn:hover {
    color: var(--text);
}

.tab-btn.active {
    background: var(--surface-2);
    color: var(--text);
    box-shadow: 0 0 0 1px var(--border-strong);
}

.toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}

/* ---------- Resources ---------- */

.resources {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 14px;
}

.sound-btn {
    width: 34px;
    height: 34px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--surface);
}

.sound-btn svg {
    width: 15px;
    height: 15px;
}

.temp-state {
    font-size: 11px;
    font-weight: 700;
    margin-left: 7px;
    letter-spacing: .04em;
    text-transform: uppercase;
    vertical-align: middle;
}

.resource.storage {
    grid-column: 1 / -1;
}

/* Colores por categoria (paleta categorica validada para
   fondo oscuro; los grises son neutros, no categorias) */
:root {
    --part-server: #3987e5;
    --part-backups: #d95926;
    --part-docker: #199e70;
    --part-swap: #c98500;
    --part-system: #6b7570;
    --part-reserved: repeating-linear-gradient(135deg, #4a534e 0 3px, #2c332f 3px 6px);
}

.resource {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    min-width: 0;
}

.resource-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 12px;
}

.resource-sub {
    color: var(--muted);
    font-size: 12px;
    text-align: right;
    line-height: 1.6;
    font-variant-numeric: tabular-nums;
}

.spark {
    position: relative;
    height: 70px;
}

.spark svg {
    width: 100%;
    height: 100%;
    display: block;
    overflow: visible;
}

.spark-axis {
    display: flex;
    justify-content: space-between;
    color: var(--dim);
    font-size: 11px;
    margin-top: 6px;
}

.spark-tip {
    position: absolute;
    top: -8px;
    transform: translate(-50%, -100%);
    background: var(--bg);
    border: 1px solid var(--border-strong);
    border-radius: 7px;
    padding: 5px 8px;
    font-size: 12px;
    white-space: nowrap;
    pointer-events: none;
    font-variant-numeric: tabular-nums;
}

.spark-tip b {
    color: var(--text);
}

.spark-tip span {
    color: var(--muted);
}

.disks {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 28px;
    margin-top: 6px;
}

.disk-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 10px;
}

.disk-name {
    font-size: 15px;
    font-weight: 700;
}

.disk-temp {
    margin-left: 10px;
    padding: 2px 7px;
    border-radius: 6px;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 11.5px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    vertical-align: 2px;
}

.disk-temp.is-amber { border-color: rgba(251, 191, 36, .35); }
.disk-temp.is-red { border-color: rgba(248, 113, 113, .4); }

.disk-total {
    color: var(--muted);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
}

.stack {
    display: flex;
    gap: 2px;
    height: 14px;
    border-radius: 5px;
    overflow: hidden;
    background: var(--bg);
    border: 1px solid var(--border);
}

.stack span {
    height: 100%;
    min-width: 3px;
    transition: width .5s, opacity .15s;
}

.stack span:first-child {
    border-radius: 4px 0 0 4px;
}

.legend {
    display: grid;
    grid-template-columns: 1fr auto auto;
    column-gap: 14px;
    row-gap: 2px;
    margin-top: 12px;
    font-size: 12.5px;
    font-variant-numeric: tabular-nums;
}

.legend-row {
    display: contents;
}

.legend-row > * {
    padding: 4px 0;
    transition: opacity .15s;
}

.legend-name {
    display: flex;
    align-items: center;
    gap: 9px;
    color: var(--text);
}

.legend-size {
    color: var(--text);
    text-align: right;
    font-weight: 600;
}

.legend-pct {
    color: var(--muted);
    text-align: right;
    min-width: 42px;
}

.swatch {
    width: 11px;
    height: 11px;
    border-radius: 3px;
    flex: none;
}

.swatch.free {
    background: var(--bg);
    box-shadow: inset 0 0 0 1px var(--border-strong);
}

.legend-row.free .legend-name,
.legend-row.free .legend-size {
    color: var(--muted);
}

.disk.focus .stack span:not(.on),
.disk.focus .legend-row:not(.on) > * {
    opacity: .3;
}

.disk-row {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 6px;
    gap: 8px;
}

.disk-row b {
    color: var(--text);
    font-weight: 600;
}

.meter {
    height: 8px;
    border-radius: 99px;
    background: var(--bg);
    border: 1px solid var(--border);
    overflow: hidden;
    display: flex;
    gap: 2px;
}

.meter span {
    height: 100%;
    border-radius: 99px;
    transition: width .5s;
}

/* ---------- Login ---------- */

.login {
    max-width: 380px;
    margin: 40px auto;
    text-align: center;
    padding: 30px 26px;
}

.login h3 {
    margin: 14px 0 4px;
    font-size: 17px;
}

.login p {
    margin: 0 0 20px;
}

.login form {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.login-icon {
    width: 46px;
    height: 46px;
    margin: 0 auto;
    border-radius: 12px;
    display: grid;
    place-items: center;
    background: var(--green-bg);
    color: var(--green);
}

.login-icon svg {
    width: 22px;
    height: 22px;
}

.login-error {
    color: var(--red);
    font-size: 13px;
    min-height: 18px;
    margin-top: 10px;
}

.input {
    width: 100%;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border-strong);
    border-radius: 10px;
    padding: 11px 13px;
    font-family: inherit;
    font-size: 14px;
    outline: none;
}

.input:focus {
    border-color: var(--green);
}

/* ---------- Lists (files / backups) ---------- */

.list {
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
}

.list:empty {
    display: none;
}

.row {
    display: grid;
    grid-template-columns: 28px minmax(0, 1fr) 100px 150px auto;
    align-items: center;
    gap: 12px;
    padding: 9px 12px;
    border-top: 1px solid var(--border);
    font-size: 13px;
}

.row:first-child {
    border-top: 0;
}

.row:hover {
    background: var(--surface-2);
}

.row-icon {
    display: grid;
    place-items: center;
    color: var(--muted);
}

.row-icon.folder {
    color: var(--amber);
}

.row-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.row-name a {
    color: var(--text);
    text-decoration: none;
    cursor: pointer;
}

.row-name a:hover {
    color: var(--green);
}

.row-meta {
    color: var(--dim);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}

.row-size {
    text-align: right;
}

.row-actions {
    display: flex;
    gap: 2px;
    justify-content: flex-end;
    opacity: .55;
}

.row:hover .row-actions {
    opacity: 1;
}

.icon-btn.danger:hover {
    color: var(--red);
    background: var(--red-bg);
}

.list-empty {
    padding: 22px;
    text-align: center;
    color: var(--dim);
}

.breadcrumb {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 2px;
    margin-bottom: 12px;
    font-size: 13px;
    font-family: var(--mono);
}

.breadcrumb a {
    color: var(--muted);
    cursor: pointer;
    padding: 3px 6px;
    border-radius: 6px;
}

.breadcrumb a:hover {
    background: var(--surface-2);
    color: var(--text);
}

.breadcrumb a:last-child {
    color: var(--text);
    font-weight: 700;
}

.breadcrumb .sep {
    color: var(--dim);
}

.backup-info {
    display: flex;
    gap: 18px;
    flex-wrap: wrap;
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 12px;
}

.backup-info b {
    color: var(--text);
    font-weight: 600;
}

.backup-row {
    grid-template-columns: 28px minmax(0, 1fr) 90px 150px auto;
}

.uploads {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 12px;
}

.uploads:empty {
    display: none;
}

.upload {
    font-size: 12px;
    color: var(--muted);
}

.upload .meter {
    margin-top: 5px;
    height: 5px;
}

#dropZone.dragging {
    border-color: var(--green);
    box-shadow: 0 0 0 3px var(--green-bg);
}

.spinner {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 2px solid currentColor;
    border-right-color: transparent;
    animation: spin .8s linear infinite;
    display: inline-block;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* ---------- Modal ---------- */

.modal {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, .6);
    display: grid;
    place-items: center;
    padding: 16px;
    z-index: 50;
}

.modal[hidden] {
    display: none;
}

.modal-box {
    width: 100%;
    max-width: 440px;
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    box-shadow: 0 30px 60px rgba(0,0,0,.5);
    display: flex;
    flex-direction: column;
    max-height: calc(100vh - 32px);
}

.modal-box.wide {
    max-width: 1000px;
    height: calc(100vh - 32px);
}

.modal-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
}

.modal-head h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.modal-body {
    padding: 18px;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.5;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.modal-foot {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    padding: 12px 18px;
    border-top: 1px solid var(--border);
}

.editor {
    flex: 1;
    width: 100%;
    min-height: 200px;
    resize: none;
    background: #070908;
    color: #d6ddd9;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    font-family: var(--mono);
    font-size: 12.5px;
    line-height: 1.6;
    outline: none;
    tab-size: 4;
    white-space: pre;
}

.editor:focus {
    border-color: var(--border-strong);
}

.btn-danger {
    background: var(--red);
    color: var(--on-red);
}

.btn-danger:hover {
    background: var(--red-hover);
}

.btn-warn {
    background: var(--amber);
    color: var(--on-amber);
}

.btn-warn:hover {
    background: var(--amber-hover);
}

/* ---------- Responsive ---------- */

@media (max-width: 900px) {
    .resources, .disks {
        grid-template-columns: 1fr;
    }
}

@media (max-width: 700px) {
    .row, .backup-row {
        grid-template-columns: 24px minmax(0, 1fr) auto;
    }

    .row .row-date, .row .row-size {
        display: none;
    }
}

@media (max-width: 820px) {
    .grid {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media (max-width: 520px) {
    header {
        flex-direction: column;
        align-items: flex-start;
    }

    .hero {
        padding: 20px;
    }

    .status {
        font-size: 22px;
    }

    .buttons, .buttons .btn {
        width: 100%;
    }

    .buttons .btn {
        justify-content: center;
    }

    .console-wrap {
        --pane-height: 380px;
    }

    .event {
        grid-template-columns: 1fr;
        gap: 4px;
    }
}

</style>
</head>


<body>

<div class="container">

<header>

<div class="brand">
<div class="logo"><div class="grass"></div><div class="dirt"></div></div>
<div>
<h1>__SERVER_NAME__</h1>
<div class="subtitle" data-i18n="app.subtitle">Admin panel</div>
</div>
</div>

<div class="header-right">

<nav class="tabs">
<button class="tab-btn active" data-tab="panel" onclick="showTab('panel')">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>
<span data-i18n="tab.panel">Panel</span>
</button>
<button class="tab-btn" data-tab="players" onclick="showTab('players')">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
<span data-i18n="tab.players">Players</span>
</button>
<button class="tab-btn" data-tab="files" onclick="showTab('files')">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
<span data-i18n="tab.files">Files</span>
</button>
<button class="tab-btn" data-tab="settings" onclick="showTab('settings')">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg>
<span data-i18n="tab.settings">Settings</span>
</button>
</nav>

<div class="lang-switch" data-i18n-title="lang.title">
<button class="lang-btn" data-lang="en" onclick="setLang('en')">EN</button>
<button class="lang-btn" data-lang="es" onclick="setLang('es')">ES</button>
</div>

<button id="themeBtn" class="icon-btn sound-btn" onclick="toggleTheme()"></button>

<button id="soundBtn" class="icon-btn sound-btn" onclick="toggleSound()"></button>

<div id="livePill" class="pill">
<span class="dot"></span>
<span id="liveText" data-i18n="live.connecting">Connecting</span>
</div>

</div>

</header>


<section id="tab-panel" class="tab-page">

<div class="card hero">

<div>

<div id="status" class="status">
<span class="dot"></span>
<span id="statusText" data-i18n="status.loading">Loading...</span>
</div>

<div class="address">
<span id="address">__PUBLIC_ADDRESS__</span>
<button class="icon-btn" data-i18n-title="addr.copy" title="Copy address" onclick="copyAddress()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
</button>
</div>

</div>


<div class="buttons">

<button id="start" class="btn btn-start" onclick="action('start')">
<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15a1 1 0 0 0 1.5.86l12-7.5a1 1 0 0 0 0-1.72l-12-7.5A1 1 0 0 0 7 4.5z"/></svg>
<span data-i18n="btn.start">Start</span>
</button>

<button id="restart" class="btn btn-ghost" onclick="confirmRestart()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/></svg>
<span data-i18n="btn.restart">Restart</span>
</button>

<button id="stop" class="btn btn-stop" onclick="confirmStop()">
<svg viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
<span data-i18n="btn.stop">Stop</span>
</button>

</div>

<div class="online">
<span class="online-label" data-i18n="online.label">Online</span>
<div id="online" style="display:contents">
<span class="online-empty">-</span>
</div>
</div>

</div>


<div class="grid">

<div class="stat">
<div class="label">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="M3.3 7 12 12l8.7-5M12 22V12"/></svg>
<span data-i18n="stat.container">Container</span>
</div>
<div id="docker" class="value">-</div>
<div class="value-sub">Docker</div>
</div>

<div class="stat">
<div class="label">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
<span data-i18n="stat.health">Health</span>
</div>
<div id="health" class="value">-</div>
<div class="value-sub">Healthcheck</div>
</div>

<div class="stat">
<div class="label">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
<span data-i18n="stat.players">Players</span>
</div>
<div id="players" class="value">-</div>
<div class="value-sub" data-i18n="stat.playersSub">Online now</div>
</div>

<div class="stat">
<div class="label">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.55a11 11 0 0 1 14.08 0M1.42 9a16 16 0 0 1 21.16 0M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1"/></svg>
<span data-i18n="stat.connections">Connections</span>
</div>
<div id="attempts" class="value">-</div>
<div class="value-sub" data-i18n="stat.connSub">Start requests</div>
</div>

</div>


<div class="card">

<div class="autostop">

<div>
<h3 class="card-title">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M9 2h6"/></svg>
<span data-i18n="autostop.title">Auto shutdown</span>
</h3>
<div id="autostopText" class="autostop-description">
<span data-i18n="autostop.checking">Checking...</span>
</div>
</div>

<div>
<div id="timer" class="timer">--:--</div>
<div id="timerLabel" class="timer-label" data-i18n="timer.remaining">Time left</div>
</div>

</div>

<div class="progress">
<div id="progress" class="progress-bar"></div>
</div>

</div>


<div class="card">

<div class="card-head">
<h3 class="card-title">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/></svg>
<span data-i18n="res.title">System resources</span>
</h3>
<span id="uptime" class="hint"></span>
</div>

<div class="resources">

<div class="resource">
<div class="resource-top">
<div>
<div class="label">CPU</div>
<div id="cpuValue" class="value">-</div>
</div>
<div id="tempBox" hidden>
<div class="label" data-i18n="res.temp">Temperature</div>
<div class="value"><span id="tempValue">-</span><span id="tempState" class="temp-state"></span></div>
</div>
<div id="cpuSub" class="resource-sub"></div>
</div>
<div id="cpuChart" class="spark" data-kind="cpu"></div>
<div class="spark-axis"><span data-i18n="res.ago3">3 min ago</span><span data-i18n="res.now">now</span></div>
</div>

<div class="resource">
<div class="resource-top">
<div>
<div class="label" data-i18n="res.memory">Memory</div>
<div id="memValue" class="value">-</div>
</div>
<div id="memSub" class="resource-sub"></div>
</div>
<div id="memChart" class="spark" data-kind="mem"></div>
<div class="spark-axis"><span data-i18n="res.ago3">3 min ago</span><span data-i18n="res.now">now</span></div>
</div>

<div class="resource storage">
<div class="label" data-i18n="res.storage">Storage</div>
<div id="disks" class="disks"></div>
</div>

</div>

</div>


<div class="card">

<!-- En celular se usan estas pestanas; en pantallas anchas se ocultan
     y los dos paneles se muestran lado a lado -->
<nav class="tabs pane-tabs">
<button class="tab-btn active" data-pane="chat" onclick="showPane('chat')">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12z"/></svg>
<span data-i18n="chat.title">Chat</span>
<span id="chatBadge" class="badge" hidden></span>
</button>
<button class="tab-btn" data-pane="console" onclick="showPane('console')">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m4 17 6-6-6-6M12 19h8"/></svg>
<span data-i18n="console.title">Console</span>
</button>
</nav>

<div id="panes" class="panes" data-pane="chat">

<div class="pane pane-chat">

<div class="pane-head">
<h3 class="card-title">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12z"/></svg>
<span data-i18n="chat.title">Chat</span>
</h3>
<span id="chatSince" class="hint"></span>
</div>

<div class="console-wrap">

<div id="chat" class="chat">
<div class="chat-empty" data-i18n="chat.loading">Loading chat...</div>
</div>

<div id="chatBar" class="command">
<span class="prompt chat-prompt">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12z"/></svg>
</span>
<input
id="chatInput"
data-i18n-placeholder="chat.placeholder"
placeholder="Message all players"
autocomplete="off"
maxlength="240"
onkeydown="if (event.key === 'Enter') sendChat()"
>
<button class="btn btn-send btn-small" onclick="sendChat()">
<span data-i18n="console.send">Send</span>
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
</button>
</div>

</div>

</div>


<div class="pane pane-console">

<div class="pane-head">
<h3 class="card-title">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m4 17 6-6-6-6M12 19h8"/></svg>
<span data-i18n="console.title">Console</span>
</h3>
<div class="toolbar">
<span class="hint" data-i18n="console.hidden">Player checks hidden</span>
<button class="btn btn-ghost btn-small" onclick="clearConsole()" data-i18n="console.clear">Clear</button>
</div>
</div>

<div class="console-wrap">

<div id="console" class="console">
<div class="console-empty" data-i18n="console.loading">Loading console...</div>
</div>

<div id="commandBar" class="command" hidden>
<span class="prompt">&gt;</span>
<input
id="command"
data-i18n-placeholder="console.placeholder"
placeholder="Type a command, e.g. say Hello"
autocomplete="off"
spellcheck="false"
onkeydown="onCommandKey(event)"
>
<button class="icon-btn" data-i18n-title="console.lock" title="Lock console and files" onclick="logout()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>
</button>
<button class="btn btn-send btn-small" onclick="sendCommand()">
<span data-i18n="console.send">Send</span>
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
</button>
</div>

<form id="commandLock" class="command" onsubmit="unlockConsole(event)">
<span class="prompt lock">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>
</span>
<input
id="consolePassword"
type="password"
data-i18n-placeholder="console.pwPlaceholder"
placeholder="Password to send commands"
autocomplete="current-password"
>
<button class="btn btn-ghost btn-small" type="submit" data-i18n="console.unlock">Unlock</button>
</form>

</div>

</div>

</div>

</div>


<div class="card">

<div class="card-head">
<h3 class="card-title">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8v4l3 3"/><circle cx="12" cy="12" r="9"/></svg>
<span data-i18n="act.title">Recent activity</span>
</h3>
<span id="lastStart" class="hint"></span>
</div>

<div id="events" class="events">
<div class="hint" data-i18n="act.none">No activity recorded.</div>
</div>

</div>

</section>


<section id="tab-files" class="tab-page" hidden>

<div id="loginCard" class="card login" hidden>
<div class="login-icon">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>
</div>
<h3 data-i18n="login.title">Protected area</h3>
<p class="hint" data-i18n="login.desc">Enter the password to manage files, backups and settings.</p>
<form onsubmit="login(event)">
<input id="password" type="password" class="input" data-i18n-placeholder="login.password" placeholder="Password" autocomplete="current-password">
<button class="btn btn-start" type="submit" style="width:100%;justify-content:center" data-i18n="login.enter">Sign in</button>
</form>
<div id="loginError" class="login-error"></div>
</div>


<div id="filesArea" hidden>

<div class="card">

<div class="card-head">
<h3 class="card-title">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/></svg>
<span data-i18n="bk.title">Backups</span>
</h3>
<div class="toolbar">
<button id="backupBtn" class="btn btn-start btn-small" onclick="createBackup()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M12 5v14M5 12h14"/></svg>
<span data-i18n="bk.now">Back up now</span>
</button>
<button class="btn btn-ghost btn-small" onclick="logout()" data-i18n="login.logout">Sign out</button>
</div>
</div>

<div id="backupInfo" class="backup-info"></div>
<div id="backups" class="list"></div>

</div>


<div id="dropZone" class="card fm">

<div class="card-head">
<h3 class="card-title">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
<span data-i18n="fm.title">Server files</span>
</h3>
<div class="toolbar">
<button class="btn btn-ghost btn-small" onclick="newFolder()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM12 11v5M9.5 13.5h5"/></svg>
<span data-i18n="fm.newFolder">New folder</span>
</button>
<button class="btn btn-start btn-small" onclick="$('uploadInput').click()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M12 16V4M6 10l6-6 6 6M4 20h16"/></svg>
<span data-i18n="fm.upload">Upload</span>
</button>
<input id="uploadInput" type="file" multiple hidden onchange="uploadFiles(this.files); this.value=''">
</div>
</div>

<div class="fm-nav">
<button id="fmUp" class="icon-btn fm-up" data-i18n-title="fm.up" title="Up one level" onclick="goUp()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
</button>
<div id="breadcrumb" class="breadcrumb"></div>
<input id="fmFilter" class="input fm-filter" data-i18n-placeholder="fm.filter" placeholder="Filter files..." autocomplete="off" oninput="renderFiles()">
</div>

<div id="fmSelection" class="fm-bar" hidden>
<span id="fmSelectionText" class="fm-bar-text"></span>
<div class="toolbar">
<button class="btn btn-ghost btn-small" onclick="bulkDownload()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M12 4v12M6 10l6 6 6-6M4 20h16"/></svg>
<span data-i18n="fm.download">Download</span>
</button>
<button id="fmRenameBtn" class="btn btn-ghost btn-small" onclick="bulkRename()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>
<span data-i18n="fm.rename">Rename</span>
</button>
<button class="btn btn-ghost btn-small" onclick="bulkMove()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM10 13h6M13.5 10.5 16 13l-2.5 2.5"/></svg>
<span data-i18n="fm.move">Move</span>
</button>
<button class="btn btn-stop btn-small" onclick="bulkDelete()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"/></svg>
<span data-i18n="fm.delete">Delete</span>
</button>
<button class="icon-btn" data-i18n-title="fm.clear" title="Clear selection" onclick="clearSelection()">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
</button>
</div>
</div>

<div id="fmMove" class="fm-bar fm-bar-move" hidden>
<span id="fmMoveText" class="fm-bar-text"></span>
<div class="toolbar">
<button class="btn btn-start btn-small" onclick="moveHere()" data-i18n="fm.moveHere">Move here</button>
<button class="btn btn-ghost btn-small" onclick="cancelMove()" data-i18n="modal.cancel">Cancel</button>
</div>
</div>

<div id="uploads" class="uploads"></div>

<div class="list files">
<div class="row row-head">
<input id="fmAll" type="checkbox" class="check" data-i18n-title="fm.selectAll" title="Select all" onchange="toggleAll(this.checked)">
<span></span>
<button class="col-btn" onclick="setSort('name')"><span data-i18n="fm.colName">Name</span><span id="sort-name" class="sort-mark"></span></button>
<button class="col-btn row-size" onclick="setSort('size')"><span data-i18n="fm.colSize">Size</span><span id="sort-size" class="sort-mark"></span></button>
<button class="col-btn row-date" onclick="setSort('mtime')"><span data-i18n="fm.colDate">Modified</span><span id="sort-mtime" class="sort-mark"></span></button>
<span></span>
</div>
<div id="fileList"></div>
</div>

<div class="fm-hint">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4M6 10l6-6 6 6M4 20h16"/></svg>
<span data-i18n="fm.dropStrip">Drag files or folders anywhere on this explorer to upload them</span>
</div>

<div class="fm-overlay">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4M6 10l6-6 6 6M4 20h16"/></svg>
<span id="fmOverlayText"></span>
</div>

</div>

</div>

</section>


<section id="tab-settings" class="tab-page" hidden>

<div id="settingsArea" hidden>

<div id="settingsNote" class="set-note" hidden></div>

<div id="settingsRestart" class="fm-bar fm-bar-move" hidden>
<span class="fm-bar-text" data-i18n="set.restartNeeded">Some changes will apply after the server restarts.</span>
<button class="btn btn-warn btn-small" onclick="restartFromSettings()" data-i18n="set.restartNow">Restart now</button>
</div>

<div id="settingsGroups"></div>

<div class="card danger-zone">
<div class="card-head">
<h3 class="card-title is-red" data-i18n="un.title">Danger zone</h3>
</div>
<div class="set-row">
<div class="set-text">
<div class="set-label" data-i18n="un.label">Uninstall everything</div>
<div class="set-desc" data-i18n="un.desc">Removes the panel, its services and the Minecraft container. You can choose to keep the world and the backups.</div>
</div>
<button class="btn btn-stop btn-small" onclick="openUninstall()" data-i18n="un.button">Uninstall</button>
</div>
</div>

<div id="settingsBar" class="set-bar" hidden>
<span id="settingsBarText" class="fm-bar-text"></span>
<div class="toolbar">
<button class="btn btn-ghost btn-small" onclick="discardSettings()" data-i18n="set.discard">Discard</button>
<button id="settingsSave" class="btn btn-start btn-small" onclick="saveSettings()" data-i18n="set.save">Save changes</button>
</div>
</div>

</div>

</section>


<section id="tab-players" class="tab-page" hidden>

<div id="playersArea" hidden>

<div id="playersNote" class="set-note" hidden></div>

<div class="card">

<div class="card-head pl-head">
<h3 class="card-title">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
<span data-i18n="tab.players">Players</span>
<span id="playersCount" class="hint"></span>
</h3>
<div class="toolbar pl-tools">
<nav class="tabs pl-filters">
<button class="tab-btn active" data-filter="all" onclick="setPlayerFilter('all')" data-i18n="pl.f.all">All</button>
<button class="tab-btn" data-filter="online" onclick="setPlayerFilter('online')" data-i18n="pl.f.online">Online</button>
<button class="tab-btn" data-filter="op" onclick="setPlayerFilter('op')" data-i18n="pl.f.op">Operators</button>
<button class="tab-btn" data-filter="banned" onclick="setPlayerFilter('banned')" data-i18n="pl.f.banned">Banned</button>
<button class="tab-btn" data-filter="whitelist" onclick="setPlayerFilter('whitelist')" data-i18n="pl.f.whitelist">Whitelist</button>
</nav>
<input id="playerSearch" class="input pl-search" data-i18n-placeholder="pl.search" placeholder="Search player..." autocomplete="off" oninput="renderPlayers()">
</div>
</div>

<div id="playerList" class="pl-list"></div>

</div>

</div>

</section>

</div>


<div id="toast" class="toast">
<span id="toastDot" class="dot"></span>
<span id="toastText"></span>
</div>


<div id="modal" class="modal" hidden onmousedown="if(event.target===this) closeModal()">
<div class="modal-box" id="modalBox">
<div class="modal-head">
<h3 id="modalTitle"></h3>
<button class="icon-btn" onclick="closeModal()" data-i18n-title="modal.close" title="Close">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
</button>
</div>
<div id="modalBody" class="modal-body"></div>
<div class="modal-foot">
<span id="modalHint" class="hint"></span>
<div class="toolbar">
<button id="modalCancel" class="btn btn-ghost btn-small" onclick="closeModal()" data-i18n="modal.cancel">Cancel</button>
<button id="modalOk" class="btn btn-start btn-small">OK</button>
</div>
</div>
</div>
</div>


<script>

// ============================================================
// Idiomas
// ============================================================

const I18N = {

    en: {
        "app.subtitle": "Admin panel",
        "tab.panel": "Panel",
        "tab.files": "Files",
        "live.on": "Live",
        "live.off": "Offline",
        "live.connecting": "Connecting",
        "theme.toLight": "Switch to light mode",
        "theme.toDark": "Switch to dark mode",
        "lang.title": "Language",

        "status.loading": "Loading...",
        "status.off": "Server offline",
        "status.starting": "Server starting",
        "status.online": "Server online",
        "status.disconnected": "Panel disconnected",
        "addr.copy": "Copy address",
        "addr.copied": "Address copied",
        "btn.start": "Start",
        "btn.restart": "Restart",
        "btn.stop": "Stop",
        "online.label": "Online",
        "online.serverOff": "Server offline",
        "online.nobody": "Nobody online",
        "online.count": "{n} player(s)",

        "stat.container": "Container",
        "stat.health": "Health",
        "stat.players": "Players",
        "stat.playersSub": "Online now",
        "stat.connections": "Connections",
        "stat.connSub": "Start requests",

        "docker.running": "Running",
        "docker.exited": "Stopped",
        "docker.created": "Created",
        "docker.restarting": "Restarting",
        "docker.paused": "Paused",
        "docker.dead": "Dead",
        "docker.removing": "Removing",
        "health.healthy": "Healthy",
        "health.starting": "Starting",
        "health.unhealthy": "Unhealthy",
        "health.no-health": "No check",
        "health.offline": "Offline",

        "autostop.title": "Auto shutdown",
        "autostop.checking": "Checking...",
        "autostop.off": "The server is offline.",
        "autostop.starting": "The server is starting. The countdown begins once it is ready.",
        "autostop.players.one": "1 player online. The server will stay on.",
        "autostop.players.other": "{n} players online. The server will stay on.",
        "autostop.empty": "No players online. The server will shut down when the countdown ends.",
        "timer.remaining": "Time left",
        "timer.waiting": "Waiting",
        "timer.noShutdown": "No shutdown",
        "timer.active": "Active",
        "timer.stopping": "Shutting down...",

        "res.title": "System resources",
        "res.temp": "Temperature",
        "res.memory": "Memory",
        "res.storage": "Storage",
        "res.ago3": "3 min ago",
        "res.now": "now",
        "res.agoSec": "{s}s ago",
        "res.collecting": "Collecting data...",
        "res.cores": "{n} cores",
        "res.load": "Load {v}",
        "res.uptime": "Up for {d}",
        "res.tempHigh": "High",
        "res.tempCrit": "Critical",
        "res.tempLimits": "High limit {h} °C · critical {c} °C",
        "res.cpuTip": "{v}% CPU",
        "res.serverUse": "Server {v}",

        "disk.usedOf": "{u} used of {t}",
        "disk.tempTitle": "Drive temperature · limit {h} °C",
        "disk.hot": "high",
        "disk.free": "Free",
        "disk.freeHint": "Available space",
        "disk.calculating": "calculating...",
        "part.server": "Server",
        "part.backups": "Backups",
        "part.docker": "Docker",
        "part.swap": "Swap",
        "part.system": "System",
        "part.other": "Other",
        "part.reserved": "Reserved",
        "hint.server": "Server folder: world, mods, config and libraries",
        "hint.backups": "Automatic and manual backups",
        "hint.docker": "Docker images and layers",
        "hint.swap": "Virtual memory file (/swap.img)",
        "hint.system": "Operating system, programs and logs",
        "hint.other": "Other files on this disk",
        "disk.role.data": "Server disk",
        "disk.role.backups": "Backups disk",
        "disk.role.system": "System disk",
        "hint.reserved": "Space ext4 sets aside for root (5%). It is empty, but regular programs cannot use it.",

        "console.title": "Console",
        "console.hidden": "Player checks hidden",
        "console.clear": "Clear",
        "console.loading": "Loading console...",
        "console.placeholder": "Type a command, e.g. say Hello",
        "console.pwPlaceholder": "Password to send commands",
        "console.unlock": "Unlock",
        "console.unlocked": "Console unlocked",
        "console.lock": "Lock console and files",
        "console.send": "Send",
        "console.cleared": "Console cleared. New messages will appear here.",
        "console.empty": "No messages.",
        "console.off": "Server is offline.",
        "console.expired": "Your session expired. Enter the password again.",
        "console.sent": "Command sent",
        "console.sendError": "Error sending command",

        "act.title": "Recent activity",
        "act.none": "No activity recorded.",
        "act.lastStart": "Last auto start: {d}",
        "act.today": "Today",
        "ev.join": "Joined",
        "ev.leave": "Left",
        "ev.request": "Connection",
        "ev.start": "Auto start",
        "ev.stop": "Auto shutdown",
        "ev.event": "Event",
        "ev.requestOn": "Connection attempt while the server was on",
        "ev.requestOff": "Connection attempt while the server was off",
        "ev.startText": "Started after detecting a connection",
        "ev.stopText": "No players for the time limit",

        "action.start": "Starting server...",
        "action.stop": "Stopping server...",
        "action.restart": "Restarting server...",
        "action.working": "Working...",
        "action.error": "Error running the action",
        "confirm.stopTitle": "Stop the server",
        "confirm.stopBody": "The server will stop. The world is saved automatically before shutting down.",
        "confirm.restartTitle": "Restart the server",
        "confirm.restartBody": "The server will shut down and start again. With the current mods it takes about a minute to be ready.",
        "confirm.noPlayers": "No players online.",
        "confirm.players.one": "1 player online: {names}. They will be disconnected.",
        "confirm.players.other": "{n} players online: {names}. They will be disconnected.",

        "sound.on": "Sound when the server starts: on",
        "sound.off": "Sound when the server starts: muted",

        "modal.ok": "OK",
        "modal.cancel": "Cancel",
        "modal.close": "Close",
        "modal.delete": "Delete",

        "login.title": "Protected area",
        "login.desc": "Enter the password to manage files, backups and settings.",
        "login.password": "Password",
        "login.enter": "Sign in",
        "login.logout": "Sign out",
        "login.noConnection": "Could not connect",

        "bk.title": "Backups",
        "bk.now": "Back up now",
        "bk.running": "Backing up...",
        "bk.nextAuto": "Daily automatic: ",
        "bk.notScheduled": "not scheduled",
        "bk.keep": "Only the most recent automatic backup is kept; manual backups stay until you delete them.",
        "bk.creatingFirst": "Creating the first backup...",
        "bk.none": "No backups yet.",
        "bk.auto": "Automatic",
        "bk.manual": "Manual",
        "bk.failed": "The backup failed",
        "bk.done": "Backup completed",
        "bk.started": "Backup started. It may take a few minutes.",
        "bk.deleteTitle": "Delete backup",
        "bk.deleteBody": "The backup from {d} ({s}) will be deleted. This cannot be undone.",
        "bk.deleted": "Backup deleted",

        "fm.title": "Server files",
        "fm.newFolder": "New folder",
        "fm.upload": "Upload",
        "fm.dropHint": "Drag files here to upload them to the current folder.",
        "fm.empty": "Empty folder",
        "fm.edit": "Edit",
        "fm.download": "Download",
        "fm.rename": "Rename",
        "fm.delete": "Delete",
        "fm.editorHint": "Ctrl+S to save. Some changes require restarting the server.",
        "fm.save": "Save",
        "fm.saved": "File saved",
        "fm.folderName": "Folder name",
        "fm.create": "Create",
        "fm.created": "Folder created",
        "fm.newName": "New name",
        "fm.renamed": "Renamed",
        "fm.deleteFolder": "The folder \"{name}\" and all its contents will be deleted. This cannot be undone.",
        "fm.deleteFile": "\"{name}\" will be deleted. This cannot be undone.",
        "fm.deleted": "Deleted",
        "fm.uploading": "Uploading {name}...",
        "fm.uploadProgress": "Uploading {name}  {done} / {total}",
        "fm.uploaded": "{name} uploaded",
        "fm.uploadError": "Error uploading {name}",
        "fm.badResponse": "Invalid response",

        "chat.title": "Chat",
        "chat.loading": "Loading chat...",
        "chat.empty": "No messages yet.",
        "chat.placeholder": "Message all players",
        "chat.server": "Server",
        "chat.yesterday": "Yesterday",
        "chat.since": "History since {d}",
        "chat.joined": "{name} joined the game",
        "chat.left": "{name} left the game",
        "chat.advancement": "{name} made the advancement [{a}]",
        "chat.pwPlaceholder": "Password to send messages",

        "fm.up": "Up one level",
        "fm.filter": "Filter files...",
        "fm.colName": "Name",
        "fm.colSize": "Size",
        "fm.colDate": "Modified",
        "fm.selectAll": "Select all",
        "fm.selected.one": "1 item selected",
        "fm.selected.other": "{n} items selected",
        "fm.move": "Move",
        "fm.clear": "Clear selection",
        "fm.moving.one": "Moving 1 item. Open the destination folder and press Move here.",
        "fm.moving.other": "Moving {n} items. Open the destination folder and press Move here.",
        "fm.moveHere": "Move here",
        "fm.moved.one": "1 item moved",
        "fm.moved.other": "{n} items moved",
        "fm.deleteMany": "{n} items will be deleted, including everything inside the folders. This cannot be undone.",
        "fm.deletedMany": "{n} items deleted",
        "fm.dropStrip": "Drag files or folders anywhere on this explorer to upload them",
        "fm.dropOverlay": "Drop to upload to {folder}",
        "fm.noMatch": "No files match the filter.",
        "fm.downloadZip": "Download as ZIP",
        "fm.preparingZip": "Preparing ZIP. The download will start shortly.",
        "fm.uploadedCount.one": "1 file uploaded",
        "fm.uploadedCount.other": "{n} files uploaded",

        "tab.settings": "Settings",
        "set.group.game": "Gameplay",
        "set.group.world": "World",
        "set.group.players": "Players and access",
        "set.live": "Applies instantly",
        "set.unsaved.one": "1 unsaved change",
        "set.unsaved.other": "{n} unsaved changes",
        "set.discard": "Discard",
        "set.save": "Save changes",
        "set.saved": "Settings saved",
        "set.savedApplied": "Settings saved and applied",
        "set.savedRestart": "Settings saved. Restart the server to apply them.",
        "set.restartNeeded": "Some changes will apply after the server restarts.",
        "set.restartNow": "Restart now",
        "set.offNote": "The server is off. Changes will apply the next time it starts.",

        "set.difficulty": "Difficulty",
        "set.difficulty.d": "How hard monsters hit and whether hunger can kill.",
        "set.gamemode": "Default game mode",
        "set.gamemode.d": "Mode players get when they join for the first time.",
        "set.force-gamemode": "Force game mode",
        "set.force-gamemode.d": "Put every player back in the default mode each time they join.",
        "set.hardcore": "Hardcore",
        "set.hardcore.d": "Players who die become spectators. Difficulty is locked to hard.",
        "set.pvp": "PvP",
        "set.pvp.d": "Let players damage each other.",
        "set.allow-flight": "Allow flight",
        "set.allow-flight.d": "Do not kick players who fly in survival. Some mods need it.",
        "set.enable-command-block": "Command blocks",
        "set.enable-command-block.d": "Let command blocks run.",
        "set.spawn-protection": "Spawn protection",
        "set.spawn-protection.d": "Radius in blocks around spawn that only operators can change. 0 turns it off.",
        "set.player-idle-timeout": "Idle timeout",
        "set.player-idle-timeout.d": "Minutes without activity before a player is kicked. 0 turns it off.",
        "set.spawn-monsters": "Monsters",
        "set.spawn-monsters.d": "Hostile creatures spawn naturally.",
        "set.spawn-animals": "Animals",
        "set.spawn-animals.d": "Animals spawn naturally.",
        "set.spawn-npcs": "Villagers",
        "set.spawn-npcs.d": "Villagers spawn naturally.",
        "set.allow-nether": "Nether",
        "set.allow-nether.d": "Players can travel to the Nether.",
        "set.view-distance": "View distance",
        "set.view-distance.d": "Chunks sent to each player (3 to 32). Higher values use more CPU and memory.",
        "set.simulation-distance": "Simulation distance",
        "set.simulation-distance.d": "Chunks around each player where mobs, crops and redstone stay active (3 to 32).",
        "set.max-players": "Max players",
        "set.max-players.d": "How many players can be online at once.",
        "set.white-list": "Whitelist",
        "set.white-list.d": "Only players on the whitelist can join.",
        "set.enforce-whitelist": "Enforce whitelist",
        "set.enforce-whitelist.d": "When the whitelist is on, kick online players who are not on it.",
        "set.online-mode": "Account verification",
        "set.online-mode.d": "Check every player with Mojang's servers. If you turn it off, anyone can join with any name.",
        "set.hide-online-players": "Hide player list",
        "set.hide-online-players.d": "Do not show who is online in the multiplayer server list.",
        "set.motd": "Server message",
        "set.motd.d": "Text shown under the server name in the multiplayer list (up to 59 characters).",

        "opt.peaceful": "Peaceful",
        "opt.easy": "Easy",
        "opt.normal": "Normal",
        "opt.hard": "Hard",
        "opt.survival": "Survival",
        "opt.creative": "Creative",
        "opt.adventure": "Adventure",
        "opt.spectator": "Spectator",

        "tab.players": "Players",
        "pl.f.all": "All",
        "pl.f.online": "Online",
        "pl.f.op": "Operators",
        "pl.f.banned": "Banned",
        "pl.f.whitelist": "Whitelist",
        "pl.search": "Search player...",
        "pl.count": "{online} online · {total} total",
        "pl.none": "No players match.",
        "pl.offNote": "The server is off. You can see the players, but actions need the server running.",
        "pl.onlineNow": "Online now",
        "pl.lastSeen": "Last seen {d}",
        "pl.neverJoined": "Has not joined yet",
        "pl.never": "never",
        "pl.timeoutUntil": "Suspended until {d}",
        "pl.badge.op": "Operator",
        "pl.badge.whitelist": "Whitelist",
        "pl.badge.banned": "Banned",
        "pl.badge.timeout": "Suspended",
        "pl.manage": "Manage",
        "pl.sheetTitle": "Player",
        "pl.firstSeen": "First joined",
        "pl.lastSeenLabel": "Last seen",
        "pl.joins": "Sessions",
        "pl.message": "Private message",
        "pl.messagePh": "Message only {name} will see",
        "pl.needsOnline": "The player must be online",
        "pl.gamemode": "Game mode",
        "pl.teleport": "Teleport",
        "pl.teleportTo": "Teleport to",
        "pl.noOthers": "Nobody else online",
        "pl.moderation": "Moderation",
        "pl.reasonPh": "Reason (optional, the player will see it)",
        "pl.kick": "Kick",
        "pl.timeout": "Suspend",
        "pl.ban": "Ban",
        "pl.pardon": "Remove ban",
        "pl.kill": "Kill",
        "pl.killHint": "The player dies and respawns. Useful if they are stuck.",
        "pl.confirm": "Click again to confirm",
        "pl.banReason": "Reason: {r}",
        "pl.role": "Role and access",
        "pl.operator": "Operator",
        "pl.operatorHint": "Can use every command and is not affected by spawn protection.",
        "pl.whitelist": "Whitelist",
        "pl.whitelistHint": "Can join when the whitelist is on.",
        "pl.dur.min": "{n} min",
        "pl.dur.hour": "{n} h",
        "pl.dur.day": "{n} d",
        "pl.done.kick": "{name} was kicked",
        "pl.done.ban": "{name} was banned",
        "pl.done.timeout": "{name} was suspended",
        "pl.done.pardon": "Ban removed for {name}",
        "pl.done.op": "{name} is now an operator",
        "pl.done.deop": "{name} is no longer an operator",
        "pl.done.whitelist_add": "{name} was added to the whitelist",
        "pl.done.whitelist_remove": "{name} was removed from the whitelist",
        "pl.done.gamemode": "Game mode changed for {name}",
        "pl.done.message": "Message sent to {name}",
        "pl.done.tp": "{name} was teleported",
        "pl.done.kill": "{name} was killed",

        "un.title": "Danger zone",
        "un.label": "Uninstall everything",
        "un.desc": "Removes the panel, its services and the Minecraft container. You can choose to keep the world and the backups.",
        "un.button": "Uninstall",
        "un.modalDesc": "The panel, its services, the Minecraft container and the configuration will be removed. By default the world and the backups are kept.",
        "un.purgeData": "Also delete the world and server files",
        "un.purgeBackups": "Also delete all backups",
        "un.typeName": "Type the server name to confirm: {name}",
        "un.doneTitle": "Uninstalling",
        "un.doneDesc": "The panel is being removed. This page will stop working in a few seconds."
    },

    es: {
        "app.subtitle": "Panel de administración",
        "tab.panel": "Panel",
        "tab.files": "Archivos",
        "live.on": "En vivo",
        "live.off": "Sin conexión",
        "live.connecting": "Conectando",
        "theme.toLight": "Cambiar a modo claro",
        "theme.toDark": "Cambiar a modo oscuro",
        "lang.title": "Idioma",

        "status.loading": "Cargando...",
        "status.off": "Servidor apagado",
        "status.starting": "Servidor arrancando",
        "status.online": "Servidor en línea",
        "status.disconnected": "Panel desconectado",
        "addr.copy": "Copiar dirección",
        "addr.copied": "Dirección copiada",
        "btn.start": "Iniciar",
        "btn.restart": "Reiniciar",
        "btn.stop": "Apagar",
        "online.label": "En línea",
        "online.serverOff": "Servidor apagado",
        "online.nobody": "Nadie conectado",
        "online.count": "{n} jugador(es)",

        "stat.container": "Contenedor",
        "stat.health": "Salud",
        "stat.players": "Jugadores",
        "stat.playersSub": "Conectados ahora",
        "stat.connections": "Conexiones",
        "stat.connSub": "Peticiones de arranque",

        "docker.running": "En ejecución",
        "docker.exited": "Detenido",
        "docker.created": "Creado",
        "docker.restarting": "Reiniciando",
        "docker.paused": "Pausado",
        "docker.dead": "Caído",
        "docker.removing": "Eliminando",
        "health.healthy": "Saludable",
        "health.starting": "Arrancando",
        "health.unhealthy": "Con fallas",
        "health.no-health": "Sin chequeo",
        "health.offline": "Apagado",

        "autostop.title": "Apagado automático",
        "autostop.checking": "Comprobando...",
        "autostop.off": "El servidor está apagado.",
        "autostop.starting": "El servidor está arrancando. La cuenta regresiva empieza cuando esté listo.",
        "autostop.players.one": "1 jugador conectado. El servidor se mantendrá encendido.",
        "autostop.players.other": "{n} jugadores conectados. El servidor se mantendrá encendido.",
        "autostop.empty": "No hay jugadores. El servidor se apagará al terminar la cuenta regresiva.",
        "timer.remaining": "Tiempo restante",
        "timer.waiting": "En espera",
        "timer.noShutdown": "Sin apagado",
        "timer.active": "Activo",
        "timer.stopping": "Apagando...",

        "res.title": "Recursos del sistema",
        "res.temp": "Temperatura",
        "res.memory": "Memoria",
        "res.storage": "Almacenamiento",
        "res.ago3": "hace 3 min",
        "res.now": "ahora",
        "res.agoSec": "hace {s} s",
        "res.collecting": "Recopilando datos...",
        "res.cores": "{n} núcleos",
        "res.load": "Carga {v}",
        "res.uptime": "Encendido hace {d}",
        "res.tempHigh": "Alta",
        "res.tempCrit": "Crítica",
        "res.tempLimits": "Límite alto {h} °C · crítico {c} °C",
        "res.cpuTip": "{v}% CPU",
        "res.serverUse": "Servidor {v}",

        "disk.usedOf": "{u} usados de {t}",
        "disk.tempTitle": "Temperatura del disco · límite {h} °C",
        "disk.hot": "alta",
        "disk.free": "Libre",
        "disk.freeHint": "Espacio disponible",
        "disk.calculating": "calculando...",
        "part.server": "Servidor",
        "part.backups": "Respaldos",
        "part.docker": "Docker",
        "part.swap": "Swap",
        "part.system": "Sistema",
        "part.other": "Otros",
        "part.reserved": "Reservado",
        "hint.server": "Carpeta del servidor: mundo, mods, configuración y librerías",
        "hint.backups": "Respaldos automáticos y manuales",
        "hint.docker": "Imágenes y capas de Docker",
        "hint.swap": "Archivo de memoria virtual (/swap.img)",
        "hint.system": "Sistema operativo, programas y logs",
        "hint.other": "Otros archivos de este disco",
        "disk.role.data": "Disco del servidor",
        "disk.role.backups": "Disco de respaldos",
        "disk.role.system": "Disco del sistema",
        "hint.reserved": "Espacio que ext4 aparta para root (5%). Está vacío, pero los programas normales no pueden usarlo.",

        "console.title": "Consola",
        "console.hidden": "Comprobaciones de jugadores ocultas",
        "console.clear": "Limpiar",
        "console.loading": "Cargando consola...",
        "console.placeholder": "Escribe un comando, por ejemplo: say Hola",
        "console.pwPlaceholder": "Contraseña para enviar comandos",
        "console.unlock": "Desbloquear",
        "console.unlocked": "Consola desbloqueada",
        "console.lock": "Bloquear consola y archivos",
        "console.send": "Enviar",
        "console.cleared": "Consola limpia. Los nuevos mensajes aparecerán aquí.",
        "console.empty": "Sin mensajes.",
        "console.off": "El servidor está apagado.",
        "console.expired": "La sesión expiró. Ingresa la contraseña de nuevo.",
        "console.sent": "Comando enviado",
        "console.sendError": "Error enviando comando",

        "act.title": "Actividad reciente",
        "act.none": "Sin actividad registrada.",
        "act.lastStart": "Último inicio automático: {d}",
        "act.today": "Hoy",
        "ev.join": "Entró",
        "ev.leave": "Salió",
        "ev.request": "Conexión",
        "ev.start": "Inicio automático",
        "ev.stop": "Apagado automático",
        "ev.event": "Evento",
        "ev.requestOn": "Intento de conexión con el servidor encendido",
        "ev.requestOff": "Intento de conexión con el servidor apagado",
        "ev.startText": "Se encendió al detectar una conexión",
        "ev.stopText": "Sin jugadores durante el tiempo límite",

        "action.start": "Iniciando servidor...",
        "action.stop": "Apagando servidor...",
        "action.restart": "Reiniciando servidor...",
        "action.working": "Procesando...",
        "action.error": "Error ejecutando la acción",
        "confirm.stopTitle": "Apagar el servidor",
        "confirm.stopBody": "El servidor se detendrá. El mundo se guarda automáticamente antes de apagar.",
        "confirm.restartTitle": "Reiniciar el servidor",
        "confirm.restartBody": "El servidor se apagará y volverá a arrancar. Con los mods actuales tarda alrededor de un minuto en estar listo.",
        "confirm.noPlayers": "No hay jugadores conectados.",
        "confirm.players.one": "Hay 1 jugador conectado: {names}. Se desconectará.",
        "confirm.players.other": "Hay {n} jugadores conectados: {names}. Se desconectarán.",

        "sound.on": "Sonido al iniciar el servidor: activado",
        "sound.off": "Sonido al iniciar el servidor: silenciado",

        "modal.ok": "Aceptar",
        "modal.cancel": "Cancelar",
        "modal.close": "Cerrar",
        "modal.delete": "Eliminar",

        "login.title": "Área protegida",
        "login.desc": "Ingresa la contraseña para administrar archivos, respaldos y ajustes.",
        "login.password": "Contraseña",
        "login.enter": "Entrar",
        "login.logout": "Cerrar sesión",
        "login.noConnection": "No se pudo conectar",

        "bk.title": "Respaldos",
        "bk.now": "Respaldar ahora",
        "bk.running": "Respaldando...",
        "bk.nextAuto": "Automático diario: ",
        "bk.notScheduled": "no programado",
        "bk.keep": "Se conserva solo el automático más reciente; los manuales se guardan hasta que los borres.",
        "bk.creatingFirst": "Creando el primer respaldo...",
        "bk.none": "Todavía no hay respaldos.",
        "bk.auto": "Automático",
        "bk.manual": "Manual",
        "bk.failed": "El respaldo falló",
        "bk.done": "Respaldo completado",
        "bk.started": "Respaldo iniciado. Puede tardar unos minutos.",
        "bk.deleteTitle": "Eliminar respaldo",
        "bk.deleteBody": "Se eliminará el respaldo del {d} ({s}). Esta acción no se puede deshacer.",
        "bk.deleted": "Respaldo eliminado",

        "fm.title": "Archivos del servidor",
        "fm.newFolder": "Nueva carpeta",
        "fm.upload": "Subir",
        "fm.dropHint": "Arrastra archivos aquí para subirlos a la carpeta actual.",
        "fm.empty": "Carpeta vacía",
        "fm.edit": "Editar",
        "fm.download": "Descargar",
        "fm.rename": "Renombrar",
        "fm.delete": "Eliminar",
        "fm.editorHint": "Ctrl+S para guardar. Algunos cambios requieren reiniciar el servidor.",
        "fm.save": "Guardar",
        "fm.saved": "Archivo guardado",
        "fm.folderName": "Nombre de la carpeta",
        "fm.create": "Crear",
        "fm.created": "Carpeta creada",
        "fm.newName": "Nuevo nombre",
        "fm.renamed": "Renombrado",
        "fm.deleteFolder": "Se eliminará la carpeta \"{name}\" y todo su contenido. Esta acción no se puede deshacer.",
        "fm.deleteFile": "Se eliminará \"{name}\". Esta acción no se puede deshacer.",
        "fm.deleted": "Eliminado",
        "fm.uploading": "Subiendo {name}...",
        "fm.uploadProgress": "Subiendo {name}  {done} / {total}",
        "fm.uploaded": "{name} subido",
        "fm.uploadError": "Error subiendo {name}",
        "fm.badResponse": "Respuesta no válida",

        "chat.title": "Chat",
        "chat.loading": "Cargando chat...",
        "chat.empty": "Todavía no hay mensajes.",
        "chat.placeholder": "Mensaje para todos los jugadores",
        "chat.server": "Servidor",
        "chat.yesterday": "Ayer",
        "chat.since": "Historial desde el {d}",
        "chat.joined": "{name} entró al juego",
        "chat.left": "{name} salió del juego",
        "chat.advancement": "{name} obtuvo el logro [{a}]",
        "chat.pwPlaceholder": "Contraseña para enviar mensajes",

        "fm.up": "Subir un nivel",
        "fm.filter": "Filtrar archivos...",
        "fm.colName": "Nombre",
        "fm.colSize": "Tamaño",
        "fm.colDate": "Modificado",
        "fm.selectAll": "Seleccionar todo",
        "fm.selected.one": "1 elemento seleccionado",
        "fm.selected.other": "{n} elementos seleccionados",
        "fm.move": "Mover",
        "fm.clear": "Quitar selección",
        "fm.moving.one": "Moviendo 1 elemento. Abre la carpeta de destino y presiona Mover aquí.",
        "fm.moving.other": "Moviendo {n} elementos. Abre la carpeta de destino y presiona Mover aquí.",
        "fm.moveHere": "Mover aquí",
        "fm.moved.one": "1 elemento movido",
        "fm.moved.other": "{n} elementos movidos",
        "fm.deleteMany": "Se eliminarán {n} elementos, incluido todo el contenido de las carpetas. Esta acción no se puede deshacer.",
        "fm.deletedMany": "{n} elementos eliminados",
        "fm.dropStrip": "Arrastra archivos o carpetas a cualquier parte de este explorador para subirlos",
        "fm.dropOverlay": "Suelta para subir a {folder}",
        "fm.noMatch": "Ningún archivo coincide con el filtro.",
        "fm.downloadZip": "Descargar como ZIP",
        "fm.preparingZip": "Preparando el ZIP. La descarga empezará en un momento.",
        "fm.uploadedCount.one": "1 archivo subido",
        "fm.uploadedCount.other": "{n} archivos subidos",

        "tab.settings": "Ajustes",
        "set.group.game": "Juego",
        "set.group.world": "Mundo",
        "set.group.players": "Jugadores y acceso",
        "set.live": "Se aplica al instante",
        "set.unsaved.one": "1 cambio sin guardar",
        "set.unsaved.other": "{n} cambios sin guardar",
        "set.discard": "Descartar",
        "set.save": "Guardar cambios",
        "set.saved": "Ajustes guardados",
        "set.savedApplied": "Ajustes guardados y aplicados",
        "set.savedRestart": "Ajustes guardados. Reinicia el servidor para aplicarlos.",
        "set.restartNeeded": "Algunos cambios se aplicarán cuando el servidor se reinicie.",
        "set.restartNow": "Reiniciar ahora",
        "set.offNote": "El servidor está apagado. Los cambios se aplicarán la próxima vez que arranque.",

        "set.difficulty": "Dificultad",
        "set.difficulty.d": "Qué tan fuerte pegan los monstruos y si el hambre puede matar.",
        "set.gamemode": "Modo de juego por defecto",
        "set.gamemode.d": "Modo que reciben los jugadores al entrar por primera vez.",
        "set.force-gamemode": "Forzar modo de juego",
        "set.force-gamemode.d": "Devuelve a cada jugador al modo por defecto cada vez que entra.",
        "set.hardcore": "Hardcore",
        "set.hardcore.d": "Quien muere pasa a espectador. La dificultad queda fija en difícil.",
        "set.pvp": "PvP",
        "set.pvp.d": "Permite que los jugadores se hagan daño entre sí.",
        "set.allow-flight": "Permitir vuelo",
        "set.allow-flight.d": "No expulsa a quien vuela en supervivencia. Algunos mods lo necesitan.",
        "set.enable-command-block": "Bloques de comandos",
        "set.enable-command-block.d": "Permite que funcionen los bloques de comandos.",
        "set.spawn-protection": "Protección del spawn",
        "set.spawn-protection.d": "Radio en bloques alrededor del spawn que solo los operadores pueden modificar. 0 la desactiva.",
        "set.player-idle-timeout": "Expulsar por inactividad",
        "set.player-idle-timeout.d": "Minutos sin actividad antes de expulsar a un jugador. 0 lo desactiva.",
        "set.spawn-monsters": "Monstruos",
        "set.spawn-monsters.d": "Aparecen criaturas hostiles.",
        "set.spawn-animals": "Animales",
        "set.spawn-animals.d": "Aparecen animales.",
        "set.spawn-npcs": "Aldeanos",
        "set.spawn-npcs.d": "Aparecen aldeanos.",
        "set.allow-nether": "Nether",
        "set.allow-nether.d": "Los jugadores pueden viajar al Nether.",
        "set.view-distance": "Distancia de visión",
        "set.view-distance.d": "Chunks que se envían a cada jugador (3 a 32). Valores altos usan más CPU y memoria.",
        "set.simulation-distance": "Distancia de simulación",
        "set.simulation-distance.d": "Chunks alrededor de cada jugador donde siguen activos los mobs, cultivos y redstone (3 a 32).",
        "set.max-players": "Máximo de jugadores",
        "set.max-players.d": "Cuántos jugadores pueden estar conectados a la vez.",
        "set.white-list": "Lista blanca",
        "set.white-list.d": "Solo pueden entrar los jugadores de la lista blanca.",
        "set.enforce-whitelist": "Aplicar lista blanca",
        "set.enforce-whitelist.d": "Con la lista blanca activa, expulsa a quien esté conectado y no esté en ella.",
        "set.online-mode": "Verificar cuentas",
        "set.online-mode.d": "Comprueba cada jugador con los servidores de Mojang. Si lo desactivas, cualquiera puede entrar con cualquier nombre.",
        "set.hide-online-players": "Ocultar lista de jugadores",
        "set.hide-online-players.d": "No muestra quién está conectado en la lista de servidores.",
        "set.motd": "Mensaje del servidor",
        "set.motd.d": "Texto que aparece bajo el nombre del servidor en la lista multijugador (hasta 59 caracteres).",

        "opt.peaceful": "Pacífico",
        "opt.easy": "Fácil",
        "opt.normal": "Normal",
        "opt.hard": "Difícil",
        "opt.survival": "Supervivencia",
        "opt.creative": "Creativo",
        "opt.adventure": "Aventura",
        "opt.spectator": "Espectador",

        "tab.players": "Jugadores",
        "pl.f.all": "Todos",
        "pl.f.online": "En línea",
        "pl.f.op": "Operadores",
        "pl.f.banned": "Baneados",
        "pl.f.whitelist": "Lista blanca",
        "pl.search": "Buscar jugador...",
        "pl.count": "{online} en línea · {total} en total",
        "pl.none": "Ningún jugador coincide.",
        "pl.offNote": "El servidor está apagado. Puedes ver a los jugadores, pero las acciones necesitan el servidor encendido.",
        "pl.onlineNow": "En línea ahora",
        "pl.lastSeen": "Visto {d}",
        "pl.neverJoined": "Todavía no ha entrado",
        "pl.never": "nunca",
        "pl.timeoutUntil": "Suspendido hasta {d}",
        "pl.badge.op": "Operador",
        "pl.badge.whitelist": "Lista blanca",
        "pl.badge.banned": "Baneado",
        "pl.badge.timeout": "Suspendido",
        "pl.manage": "Administrar",
        "pl.sheetTitle": "Jugador",
        "pl.firstSeen": "Primera vez",
        "pl.lastSeenLabel": "Última vez",
        "pl.joins": "Sesiones",
        "pl.message": "Mensaje privado",
        "pl.messagePh": "Mensaje que solo verá {name}",
        "pl.needsOnline": "El jugador tiene que estar en línea",
        "pl.gamemode": "Modo de juego",
        "pl.teleport": "Teletransportar",
        "pl.teleportTo": "Llevar con",
        "pl.noOthers": "No hay nadie más en línea",
        "pl.moderation": "Moderación",
        "pl.reasonPh": "Motivo (opcional, el jugador lo verá)",
        "pl.kick": "Expulsar",
        "pl.timeout": "Suspender",
        "pl.ban": "Banear",
        "pl.pardon": "Quitar ban",
        "pl.kill": "Matar",
        "pl.killHint": "El jugador muere y reaparece. Útil si se quedó atorado.",
        "pl.confirm": "Clic otra vez para confirmar",
        "pl.banReason": "Motivo: {r}",
        "pl.role": "Rol y acceso",
        "pl.operator": "Operador",
        "pl.operatorHint": "Puede usar todos los comandos y no le afecta la protección del spawn.",
        "pl.whitelist": "Lista blanca",
        "pl.whitelistHint": "Puede entrar cuando la lista blanca está activa.",
        "pl.dur.min": "{n} min",
        "pl.dur.hour": "{n} h",
        "pl.dur.day": "{n} días",
        "pl.done.kick": "{name} fue expulsado",
        "pl.done.ban": "{name} fue baneado",
        "pl.done.timeout": "{name} fue suspendido",
        "pl.done.pardon": "Se quitó el ban a {name}",
        "pl.done.op": "{name} ahora es operador",
        "pl.done.deop": "{name} ya no es operador",
        "pl.done.whitelist_add": "{name} se agregó a la lista blanca",
        "pl.done.whitelist_remove": "{name} se quitó de la lista blanca",
        "pl.done.gamemode": "Se cambió el modo de juego de {name}",
        "pl.done.message": "Mensaje enviado a {name}",
        "pl.done.tp": "{name} fue teletransportado",
        "pl.done.kill": "{name} murió",

        "un.title": "Zona de peligro",
        "un.label": "Desinstalar todo",
        "un.desc": "Quita el panel, sus servicios y el contenedor de Minecraft. Puedes elegir conservar el mundo y los respaldos.",
        "un.button": "Desinstalar",
        "un.modalDesc": "Se eliminarán el panel, sus servicios, el contenedor de Minecraft y la configuración. Por defecto se conservan el mundo y los respaldos.",
        "un.purgeData": "Borrar también el mundo y los archivos del servidor",
        "un.purgeBackups": "Borrar también todos los respaldos",
        "un.typeName": "Escribe el nombre del servidor para confirmar: {name}",
        "un.doneTitle": "Desinstalando",
        "un.doneDesc": "Se está quitando el panel. Esta página dejará de funcionar en unos segundos."
    }
};


// Mensajes que devuelve el servidor (en espanol) -> ingles
const SERVER_MESSAGES_EN = {
    "Acción no válida": "Invalid action",
    "Archivo guardado": "File saved",
    "Archivo subido": "File uploaded",
    "Carpeta creada": "Folder created",
    "Comando enviado": "Command sent",
    "Comando vacío": "Empty command",
    "Contraseña incorrecta": "Wrong password",
    "Demasiados intentos. Espera 5 minutos.": "Too many attempts. Wait 5 minutes.",
    "Eliminado": "Deleted",
    "Error ejecutando Docker": "Error running Docker",
    "Error procesando comando": "Error processing command",
    "El servidor está apagado": "Server is offline",
    "No encontrado": "Not found",
    "No se pudo ejecutar el comando": "The command could not be run",
    "Renombrado": "Renamed",
    "Respaldo eliminado": "Backup deleted",
    "Respaldo iniciado": "Backup started",
    "Sesión no válida": "Invalid session",
    "Servidor iniciado": "Server started",
    "Servidor apagado": "Server stopped",
    "Servidor reiniciado": "Server restarted",
    "Contenido demasiado grande": "Content too large",
    "El archivo es demasiado grande para editarlo aquí (máx. 2 MB)": "The file is too large to edit here (max. 2 MB)",
    "El destino no es una carpeta": "The destination is not a folder",
    "El respaldo no existe": "The backup does not exist",
    "Es un archivo binario; descárgalo para verlo": "This is a binary file; download it to view it",
    "Es una carpeta": "It is a folder",
    "La subida se interrumpió": "The upload was interrupted",
    "No es un archivo": "Not a file",
    "No es una carpeta": "Not a folder",
    "No se puede borrar la carpeta raíz": "The root folder cannot be deleted",
    "No se puede renombrar la carpeta raíz": "The root folder cannot be renamed",
    "Nombre demasiado largo": "Name too long",
    "Nombre no válido": "Invalid name",
    "Respaldo no válido": "Invalid backup",
    "Ruta fuera de la carpeta del servidor": "Path outside the server folder",
    "Solo se pueden descargar archivos": "Only files can be downloaded",
    "Ya existe un elemento con ese nombre": "An item with that name already exists",
    "Ya existe una carpeta con ese nombre": "A folder with that name already exists",
    "Ya hay un respaldo en curso": "A backup is already running",
    "Ajustes guardados": "Settings saved",
    "El nombre no coincide": "The name does not match",
    "Desinstalando": "Uninstalling",
    "Acción aplicada": "Done",
    "No se pudo ejecutar la acción": "The action could not be run",
    "Nombre de jugador no válido": "Invalid player name",
    "Modo de juego no válido": "Invalid game mode",
    "Duración no válida": "Invalid duration",
    "Sin cambios": "No changes",
    "No hay cambios que guardar": "No changes to save",
    "No existe server.properties": "server.properties does not exist",
    "Movido": "Moved",
    "No hay elementos seleccionados": "No items selected",
    "No se puede mover la carpeta raíz": "The root folder cannot be moved",
    "No se puede mover una carpeta dentro de sí misma": "A folder cannot be moved into itself",
    "El elemento ya está en esa carpeta": "The item is already in that folder",
    "Petición no válida": "Invalid request",
    "Mensaje enviado": "Message sent",
    "Mensaje vacío": "Empty message",
    "No se pudo enviar el mensaje": "The message could not be sent",
    "Estás enviando mensajes muy rápido. Espera un momento.": "You are sending messages too fast. Wait a moment."
};

const SERVER_PREFIXES_EN = [
    ["No existe: ", "Does not exist: "],
    ["Valor no válido para ", "Invalid value for "],
    ["Ajuste no permitido: ", "Setting not allowed: "],
    ["No se pudo iniciar el respaldo: ", "The backup could not be started: "],
    ["Error: ", "Error: "]
];


let lang = "__DEFAULT_LANG__";

try {
    const saved = localStorage.getItem("mc-lang");
    if (saved === "es" || saved === "en") lang = saved;
} catch (error) {
}


function t(key, vars) {

    let text = I18N[lang][key];

    if (text === undefined) text = I18N.en[key];
    if (text === undefined) return "";

    if (vars) {
        text = text.replace(/\{(\w+)\}/g, function(match, name) {
            return name in vars ? vars[name] : match;
        });
    }

    return text;
}


function tn(key, n, vars) {
    return t(key + (n === 1 ? ".one" : ".other"), Object.assign({ n: n }, vars || {}));
}


function serverText(message) {

    if (!message || lang === "es") return message;

    if (SERVER_MESSAGES_EN[message]) return SERVER_MESSAGES_EN[message];

    for (const [es, en] of SERVER_PREFIXES_EN) {
        if (message.startsWith(es)) return en + message.slice(es.length);
    }

    return message;
}


function eventLabel(event) {
    if (event.type === "request") return t(event.text === "off" ? "ev.requestOff" : "ev.requestOn");
    if (event.type === "start") return t("ev.startText");
    if (event.type === "stop") return t("ev.stopText");
    return event.text;
}


function locale() {
    return lang === "es" ? "es-MX" : "en-US";
}


function applyI18n() {

    document.documentElement.lang = lang;

    document.querySelectorAll("[data-i18n]").forEach(function(node) {
        node.textContent = t(node.dataset.i18n);
    });

    document.querySelectorAll("[data-i18n-placeholder]").forEach(function(node) {
        node.placeholder = t(node.dataset.i18nPlaceholder);
    });

    document.querySelectorAll("[data-i18n-title]").forEach(function(node) {
        node.title = t(node.dataset.i18nTitle);
    });

    document.querySelectorAll(".lang-btn").forEach(function(btn) {
        btn.classList.toggle("active", btn.dataset.lang === lang);
    });
}


function setLang(next) {

    if (next === lang) return;

    lang = next;

    try {
        localStorage.setItem("mc-lang", lang);
    } catch (error) {
    }

    applyI18n();

    // Fuerza a redibujar todo lo que se genera desde JS
    $("events").dataset.key = "";
    $("online").dataset.key = "";
    lastConsole = "";

    renderSoundButton();
    renderThemeButton();
    update();
    updateConsole();
    updateStats();
    loadChat();

    if (filesReady && !$("tab-files").hidden) {
        loadFolder(currentPath);
        loadBackups();
    }

    if (!$("tab-settings").hidden) {
        renderSettings();
    }

    if (!$("tab-players").hidden && playersData) {
        renderPlayers();
    }
}


// ============================================================
// Tema claro / oscuro
// ============================================================

let theme = null;

try {
    const saved = localStorage.getItem("mc-theme");
    if (saved === "light" || saved === "dark") theme = saved;
} catch (error) {
}


function systemTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark";
}


function currentTheme() {
    return theme || systemTheme();
}


function applyTheme() {
    document.documentElement.dataset.theme = currentTheme();
}


const THEME_ICONS = {
    sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    moon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
};


function renderThemeButton() {
    const dark = currentTheme() === "dark";
    const btn = $("themeBtn");
    btn.innerHTML = dark ? THEME_ICONS.sun : THEME_ICONS.moon;
    btn.title = dark ? t("theme.toLight") : t("theme.toDark");
}


function toggleTheme() {

    theme = currentTheme() === "dark" ? "light" : "dark";

    try {
        localStorage.setItem("mc-theme", theme);
    } catch (error) {
    }

    applyTheme();
    renderThemeButton();

    // Las graficas leen colores del tema al dibujarse
    updateStats();
}


if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", function() {
        if (!theme) {
            applyTheme();
            renderThemeButton();
            updateStats();
        }
    });
}


function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}


applyTheme();



let lastConsole = "";
let clearedAfter = null;
let autoScroll = true;
let toastTimer = null;
let cmdHistory = [];
let cmdHistoryIndex = -1;




function $(id) {
    return document.getElementById(id);
}


function formatTime(seconds) {

    seconds = Math.max(0, Number(seconds) || 0);

    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;

    return String(minutes).padStart(2, "0")
        + ":"
        + String(secs).padStart(2, "0");
}


function setTone(el, tone) {
    el.classList.remove("is-green", "is-amber", "is-red");
    if (tone) {
        el.classList.add("is-" + tone);
    }
}


function showToast(text, tone) {

    $("toastText").textContent = text;

    const dot = $("toastDot");
    dot.className = "dot";
    if (tone) {
        dot.classList.add("is-" + tone);
    }

    $("toast").classList.add("show");

    clearTimeout(toastTimer);
    toastTimer = setTimeout(function() {
        $("toast").classList.remove("show");
    }, 3000);
}


async function update() {

    try {

        const response = await fetch("/api?t=" + Date.now());
        const data = await response.json();

        let label, tone;

        if (!data.running) {
            label = t("status.off");
            tone = "red";
        } else if (data.health !== "healthy") {
            label = t("status.starting");
            tone = "amber";
        } else {
            label = t("status.online");
            tone = "green";
        }

        // Solo suena en la transicion a "en linea" vista en esta sesion,
        // no al abrir la pagina con el servidor ya encendido
        if (lastStatusTone !== null && lastStatusTone !== "green" && tone === "green") {
            playChime();
        }

        lastStatusTone = tone;

        currentPlayers =
            data.running && Array.isArray(data.autostop.names) ? data.autostop.names : [];

        $("statusText").textContent = label;
        setTone($("status"), tone);

        $("liveText").textContent = t("live.on");
        setTone($("livePill"), "green");
        $("livePill").classList.add("pulse");

        $("docker").textContent =
            t("docker." + data.status) || data.status;

        $("health").textContent =
            data.running
                ? (t("health." + data.health) || data.health)
                : "-";

        $("players").textContent =
            data.running ? data.autostop.players : "-";

        $("attempts").textContent = data.attempts;

        $("start").disabled = data.running;
        $("stop").disabled = !data.running;
        $("restart").disabled = !data.running;

        updateAutostop(data.autostop);
        updateOnline(data.running, data.autostop);
        updateEvents(data.events || []);

    } catch (error) {

        $("statusText").textContent = t("status.disconnected");
        setTone($("status"), "red");

        $("liveText").textContent = t("live.off");
        setTone($("livePill"), "red");
        $("livePill").classList.remove("pulse");
    }
}


// Contador de apagado: el servidor solo actualiza el estado
// cada 10s, asi que aqui se calcula la hora exacta de apagado
// y se anima localmente
let countdown = {
    mode: "off",
    end: 0,
    total: 600
};


function updateAutostop(data) {

    const text = $("autostopText");

    if (!data.running) {
        countdown.mode = "off";
        text.textContent = t("autostop.off");
    } else if (data.health && data.health !== "healthy" && !data.players) {
        countdown.mode = "waiting";
        text.textContent = t("autostop.starting");
    } else if (data.players > 0) {
        countdown.mode = "players";
        text.textContent = tn("autostop.players", data.players);
    } else {

        const remaining =
            (Number(data.remaining_seconds) || 0) - (Number(data.age) || 0);

        const end = Date.now() + remaining * 1000;

        // Solo se corrige si se desvio; evita saltos pequenos
        if (countdown.mode !== "counting" || Math.abs(end - countdown.end) > 1500) {
            countdown.end = end;
        }

        countdown.mode = "counting";
        countdown.total = Number(data.timeout_seconds) || 600;

        text.textContent =
            t("autostop.empty");
    }

    renderCountdown();
}


function renderCountdown() {

    const timer = $("timer");
    const label = $("timerLabel");
    const progress = $("progress");

    setTone(timer, null);

    if (countdown.mode === "off" || countdown.mode === "waiting") {
        timer.textContent = "--:--";
        label.textContent = countdown.mode === "off" ? t("timer.remaining") : t("timer.waiting");
        progress.style.width = "0%";
        return;
    }

    if (countdown.mode === "players") {
        timer.textContent = t("timer.active");
        setTone(timer, "green");
        label.textContent = t("timer.noShutdown");
        progress.style.width = "100%";
        progress.style.background = "var(--green)";
        return;
    }

    const msLeft = Math.max(0, countdown.end - Date.now());
    const seconds = Math.ceil(msLeft / 1000);
    const percent = Math.min(100, msLeft / (countdown.total * 1000) * 100);

    timer.textContent = formatTime(seconds);
    label.textContent = t("timer.remaining");
    progress.style.width = percent + "%";

    if (msLeft <= 0) {
        timer.textContent = "00:00";
        label.textContent = t("timer.stopping");
        setTone(timer, "red");
        progress.style.background = "var(--red)";
        return;
    }

    const tone = percent < 20 ? "red" : "amber";
    setTone(timer, tone);
    progress.style.background =
        tone === "red" ? "var(--red)" : "var(--amber)";
}


function updateOnline(running, data) {

    const box = $("online");
    const names = (data && Array.isArray(data.names)) ? data.names : [];
    const key = running + "|" + names.join(",");

    if (box.dataset.key === key) {
        return;
    }

    box.dataset.key = key;
    box.textContent = "";

    if (!names.length) {
        const empty = document.createElement("span");
        empty.className = "online-empty";
        empty.textContent =
            !running ? t("online.serverOff")
            : data.players > 0 ? t("online.count", { n: data.players })
            : t("online.nobody");
        box.append(empty);
        return;
    }

    names.forEach(function(name) {

        const chip = document.createElement("span");
        chip.className = "player";

        const avatar = document.createElement("span");
        avatar.className = "avatar";
        avatar.textContent = name.charAt(0).toUpperCase();

        const img = document.createElement("img");
        img.alt = "";
        img.src = "https://mc-heads.net/avatar/" + encodeURIComponent(name) + "/48";
        img.onerror = function() { img.remove(); };
        avatar.append(img);

        const label = document.createElement("span");
        label.textContent = name;

        chip.append(avatar, label);
        box.append(chip);
    });
}


const EVENT_TYPES = {
    join: ["ev.join", "green"],
    leave: ["ev.leave", "amber"],
    request: ["ev.request", "blue"],
    start: ["ev.start", "green"],
    stop: ["ev.stop", "red"]
};


function formatDate(ts) {

    const d = new Date(ts * 1000);
    const today = new Date();

    const time = d.toLocaleTimeString(locale(), {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
    });

    if (d.toDateString() === today.toDateString()) {
        return t("act.today") + " " + time;
    }

    return d.toLocaleDateString(locale(), {
        day: "2-digit",
        month: "short"
    }) + " " + time;
}


function updateEvents(events) {

    const box = $("events");

    const starts = events.filter(function(e) { return e.type === "start"; });
    $("lastStart").textContent =
        starts.length
            ? t("act.lastStart", { d: formatDate(starts[starts.length - 1].ts) })
            : "";

    const key = events.map(function(e) { return e.ts + e.type + e.text; }).join("|");

    if (box.dataset.key === key) {
        return;
    }

    box.dataset.key = key;

    if (!events.length) {
        box.textContent = "";
        box.append(el("div", "hint", t("act.none")));
        return;
    }

    box.textContent = "";

    events.slice().reverse().forEach(function(event) {

        const [tagKey, tone] = EVENT_TYPES[event.type] || ["ev.event", ""];
        const tag = t(tagKey);
        const eventText = eventLabel(event);

        const row = document.createElement("div");
        row.className = "event";

        const timeEl = document.createElement("div");
        timeEl.className = "event-time";
        timeEl.textContent = event.ts ? formatDate(event.ts) : "";

        const body = document.createElement("div");
        body.className = "event-body";

        const tagEl = document.createElement("span");
        tagEl.className = "tag " + tone;
        tagEl.textContent = tag;

        const textEl = document.createElement("span");
        textEl.className = "event-text";
        textEl.textContent = eventText;
        textEl.title = eventText;

        if (event.type === "join" || event.type === "leave") {
            textEl.style.color = "var(--text)";
            textEl.style.fontWeight = "600";
        }

        body.append(tagEl, textEl);
        row.append(timeEl, body);
        box.append(row);
    });
}


const LOG_LINE =
    /^\[(\d\d:\d\d:\d\d)\] \[([^\]]*?)\/(INFO|WARN|ERROR|FATAL|DEBUG)\](?: \[([^\]]*)\])?:?\s?(.*)$/;


function renderLine(text) {

    const line = document.createElement("div");
    line.className = "line";

    if (text === "El servidor está apagado.") {
        line.textContent = t("console.off");
        return line;
    }

    const m = LOG_LINE.exec(text);

    if (!m) {
        line.textContent = text;
        return line;
    }

    const [, time, thread, level, source, msg] = m;

    if (level === "WARN") line.classList.add("warn");
    if (level === "ERROR" || level === "FATAL") line.classList.add("error");
    if (/^<[^>]+> /.test(msg)) line.classList.add("chat");

    const parts = [
        ["t", time + " "],
        ["lvl lvl-" + level, level.padEnd(5) + " "],
        ["src", (source ? source.replace(/\/$/, "") : thread) + " "],
        ["msg", msg]
    ];

    parts.forEach(function([cls, value]) {
        const span = document.createElement("span");
        span.className = cls;
        span.textContent = value;
        line.append(span);
    });

    return line;
}


async function updateConsole() {

    try {

        const response = await fetch("/console?t=" + Date.now());
        const text = await response.text();

        if (text === lastConsole) {
            return;
        }

        lastConsole = text;

        let lines = text.split("\n").filter(function(x) {
            return x.trim();
        });

        if (clearedAfter !== null) {
            const index = lines.lastIndexOf(clearedAfter);
            if (index !== -1) {
                lines = lines.slice(index + 1);
            }
        }

        const box = $("console");

        const atBottom =
            box.scrollHeight - box.scrollTop - box.clientHeight < 60;

        box.textContent = "";

        if (!lines.length) {
            const empty = document.createElement("div");
            empty.className = "console-empty";
            empty.textContent =
                clearedAfter !== null
                    ? t("console.cleared")
                    : t("console.empty");
            box.append(empty);
        } else {
            const frag = document.createDocumentFragment();
            lines.forEach(function(x) {
                frag.append(renderLine(x));
            });
            box.append(frag);
        }

        if (autoScroll || atBottom) {
            box.scrollTop = box.scrollHeight;
        }

    } catch (error) {
    }
}


async function action(type) {

    const names = {
        start: t("action.start"),
        stop: t("action.stop"),
        restart: t("action.restart")
    };

    ["start", "stop", "restart"].forEach(function(id) {
        $(id).disabled = true;
    });

    showToast(names[type] || t("action.working"), "amber");

    try {

        const response = await fetch("/action/" + type, { method: "POST" });
        const data = await response.json();

        showToast(serverText(data.message), data.ok ? "green" : "red");

    } catch (error) {
        showToast(t("action.error"), "red");
    }

    setTimeout(update, 300);
    setTimeout(updateConsole, 300);
}


function onCommandKey(event) {

    const input = $("command");

    if (event.key === "Enter") {
        sendCommand();
        return;
    }

    if (event.key === "ArrowUp" && cmdHistory.length) {
        event.preventDefault();
        cmdHistoryIndex = Math.max(0, cmdHistoryIndex === -1 ? cmdHistory.length - 1 : cmdHistoryIndex - 1);
        input.value = cmdHistory[cmdHistoryIndex];
    }

    if (event.key === "ArrowDown" && cmdHistoryIndex !== -1) {
        event.preventDefault();
        cmdHistoryIndex++;
        if (cmdHistoryIndex >= cmdHistory.length) {
            cmdHistoryIndex = -1;
            input.value = "";
        } else {
            input.value = cmdHistory[cmdHistoryIndex];
        }
    }
}


async function sendCommand() {

    const input = $("command");
    const command = input.value.trim().replace(/^\//, "");

    if (!command) {
        return;
    }

    try {

        const response = await fetch("/command", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded"
            },
            body: "command=" + encodeURIComponent(command)
        });

        if (response.status === 401) {
            setConsoleLocked(true);
            showToast(t("console.expired"), "red");
            return;
        }

        const data = await response.json();

        if (data.ok) {
            cmdHistory.push(command);
            cmdHistoryIndex = -1;
            input.value = "";
            showToast(data.output ? data.output : t("console.sent"), "green");
        } else {
            showToast(serverText(data.message), "red");
        }

        autoScroll = true;
        setTimeout(updateConsole, 300);

    } catch (error) {
        showToast(t("console.sendError"), "red");
    }
}


let currentPlayers = [];


function playersWarning() {

    if (!currentPlayers.length) {
        return t("confirm.noPlayers");
    }

    return tn("confirm.players", currentPlayers.length, { names: currentPlayers.join(", ") });
}


async function confirmStop() {

    const ok = await openModal({
        title: t("confirm.stopTitle"),
        body: [
            t("confirm.stopBody"),
            el("div", currentPlayers.length ? "is-amber" : "", playersWarning())
        ],
        okText: t("btn.stop"),
        danger: true
    });

    if (ok) action("stop");
}


async function confirmRestart() {

    const ok = await openModal({
        title: t("confirm.restartTitle"),
        body: [
            t("confirm.restartBody"),
            el("div", currentPlayers.length ? "is-amber" : "", playersWarning())
        ],
        okText: t("btn.restart"),
        okClass: "btn-warn"
    });

    if (ok) action("restart");

    return ok;
}


function clearConsole() {

    const lines = lastConsole.split("\n").filter(function(x) {
        return x.trim();
    });

    clearedAfter = lines.length ? lines[lines.length - 1] : null;
    lastConsole = "";
    updateConsole();
}


function copyAddress() {

    const text = $("address").textContent.trim();

    const done = function() {
        showToast(t("addr.copied"), "green");
    };

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done);
        return;
    }

    const area = document.createElement("textarea");
    area.value = text;
    document.body.append(area);
    area.select();
    try {
        document.execCommand("copy");
        done();
    } catch (error) {
    }
    area.remove();
}


$("console").addEventListener("scroll", function() {
    autoScroll =
        this.scrollHeight - this.scrollTop - this.clientHeight < 60;
});


// ============================================================
// Sonido de "servidor en linea"
// ============================================================

let lastStatusTone = null;
let audioCtx = null;
let soundOn = true;

try {
    soundOn = localStorage.getItem("mc-sound") !== "off";
} catch (error) {
}


const SOUND_ICONS = {
    on: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/></svg>',
    off: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="m22 9-6 6M16 9l6 6"/></svg>'
};


function renderSoundButton() {
    const btn = $("soundBtn");
    btn.innerHTML = soundOn ? SOUND_ICONS.on : SOUND_ICONS.off;
    btn.title = soundOn
        ? t("sound.on")
        : t("sound.off");
}


function getAudio() {

    if (!audioCtx) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return null;
        audioCtx = new Ctx();
    }

    if (audioCtx.state === "suspended") {
        audioCtx.resume();
    }

    return audioCtx;
}


// Los navegadores solo permiten audio despues de una interaccion;
// el primer clic o tecla en la pagina lo habilita
["pointerdown", "keydown"].forEach(function(type) {
    document.addEventListener(type, function() {
        if (soundOn) getAudio();
    }, { once: true, capture: true });
});


function playChime() {

    if (!soundOn) return;

    const ctx = getAudio();
    if (!ctx || ctx.state !== "running") return;

    const now = ctx.currentTime + 0.02;

    const master = ctx.createGain();
    master.gain.value = 0.16;

    // Eco suave para darle cuerpo
    const delay = ctx.createDelay();
    delay.delayTime.value = 0.19;
    const feedback = ctx.createGain();
    feedback.gain.value = 0.28;
    const tone = ctx.createBiquadFilter();
    tone.type = "lowpass";
    tone.frequency.value = 2600;

    delay.connect(tone);
    tone.connect(feedback);
    feedback.connect(delay);
    tone.connect(master);
    master.connect(ctx.destination);

    // Arpegio de sol mayor: G5, B5, D6
    [783.99, 987.77, 1174.66].forEach(function(freq, i) {

        const start = now + i * 0.12;
        const length = 1.6 - i * 0.2;

        [[freq, 1], [freq * 2, 0.12]].forEach(function([f, level]) {

            const osc = ctx.createOscillator();
            osc.type = "sine";
            osc.frequency.value = f;

            const env = ctx.createGain();
            env.gain.setValueAtTime(0.0001, start);
            env.gain.exponentialRampToValueAtTime(level, start + 0.012);
            env.gain.exponentialRampToValueAtTime(0.0001, start + length);

            osc.connect(env);
            env.connect(master);
            env.connect(delay);

            osc.start(start);
            osc.stop(start + length + 0.05);
        });
    });

    setTimeout(function() {
        master.disconnect();
        delay.disconnect();
        feedback.disconnect();
        tone.disconnect();
    }, 4000);
}


function toggleSound() {

    soundOn = !soundOn;

    try {
        localStorage.setItem("mc-sound", soundOn ? "on" : "off");
    } catch (error) {
    }

    renderSoundButton();

    if (soundOn) {
        getAudio();
        setTimeout(playChime, 60);
    }
}


renderSoundButton();


// ============================================================
// Utilidades
// ============================================================

function formatBytes(bytes, decimals) {

    if (bytes === null || bytes === undefined) return "-";

    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    let value = Number(bytes);

    while (value >= 1024 && i < units.length - 1) {
        value /= 1024;
        i++;
    }

    const d = decimals !== undefined ? decimals : (value < 10 && i > 0 ? 1 : 0);
    return value.toFixed(d) + " " + units[i];
}


function formatDuration(seconds) {

    const d = Math.floor(seconds / 86400);
    const h = Math.floor(seconds % 86400 / 3600);
    const m = Math.floor(seconds % 3600 / 60);

    if (d > 0) return d + " d " + h + " h";
    if (h > 0) return h + " h " + m + " min";
    return m + " min";
}


function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}


const ICONS = {
    folder: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/></svg>',
    text: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/></svg>',
    archive: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/></svg>',
    edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8l6 6v2"/><path d="M14 3v6h6"/><path d="M18.4 13.6a1.7 1.7 0 0 1 2.4 2.4L15.5 21.3l-3.2.8.8-3.2z"/></svg>',
    download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v12M6 10l6 6 6-6M4 20h16"/></svg>',
    rename: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',
    message: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12z"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"/></svg>'
};


function iconButton(icon, title, onClick, danger) {
    const btn = el("button", "icon-btn" + (danger ? " danger" : ""));
    btn.innerHTML = ICONS[icon];
    btn.title = title;
    btn.onclick = function(event) {
        event.stopPropagation();
        onClick();
    };
    return btn;
}


// ============================================================
// Pestanas
// ============================================================

let activeTab = "panel";

const TAB_HASH = {
    players: "#jugadores",
    files: "#archivos",
    settings: "#ajustes"
};


function showTab(name) {

    activeTab = name;

    document.querySelectorAll(".tab-btn[data-tab]").forEach(function(btn) {
        btn.classList.toggle("active", btn.dataset.tab === name);
    });

    ["panel", "players", "files", "settings"].forEach(function(tab) {
        $("tab-" + tab).hidden = tab !== name;
    });

    try {
        history.replaceState(null, "", TAB_HASH[name] || "#");
    } catch (error) {
    }

    // Archivos y Ajustes piden contrasena
    if (name !== "panel") {
        openProtected();
    }
}


// ============================================================
// Monitor de recursos
// ============================================================

function renderSpark(box, points, max, color, format) {

    const width = box.clientWidth || 300;
    const height = box.clientHeight || 70;

    box._spark = { points: points, max: max, format: format, color: color };

    if (points.length < 2) {
        box.innerHTML = '<div class="hint" style="padding-top:26px"></div>';
        box.firstChild.textContent = t("res.collecting");
        return;
    }

    const n = points.length;
    const x = function(i) { return (i / (n - 1)) * width; };
    const y = function(v) { return height - 2 - Math.min(1, v / max) * (height - 4); };

    let line = "";
    points.forEach(function(p, i) {
        line += (i ? "L" : "M") + x(i).toFixed(1) + " " + y(p[1]).toFixed(1);
    });

    const area = line + "L" + width + " " + height + "L0 " + height + "Z";
    const id = "g" + box.id;

    box.innerHTML =
        '<svg viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none">'
        + '<defs><linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1">'
        + '<stop offset="0" stop-color="' + color + '" stop-opacity=".28"/>'
        + '<stop offset="1" stop-color="' + color + '" stop-opacity="0"/>'
        + '</linearGradient></defs>'
        + '<line x1="0" x2="' + width + '" y1="' + (height / 2) + '" y2="' + (height / 2) + '" stroke="' + cssVar("--border") + '" stroke-dasharray="3 4"/>'
        + '<line x1="0" x2="' + width + '" y1="' + (height - 0.5) + '" y2="' + (height - 0.5) + '" stroke="' + cssVar("--border-strong") + '"/>'
        + '<path d="' + area + '" fill="url(#' + id + ')"/>'
        + '<path d="' + line + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        + '<g class="hover" style="display:none">'
        + '<line class="hl" y1="0" y2="' + height + '" stroke="' + cssVar("--dim") + '"/>'
        + '<circle class="hc" r="4" fill="' + color + '" stroke="' + cssVar("--surface-2") + '" stroke-width="2"/>'
        + '</g>'
        + '</svg>';

    if (box._hoverX !== undefined) {
        sparkHover(box, box._hoverX);
    }
}


function sparkHover(box, px) {

    const s = box._spark;
    if (!s || s.points.length < 2) return;

    const width = box.clientWidth;
    const height = box.clientHeight;
    const n = s.points.length;
    const i = Math.max(0, Math.min(n - 1, Math.round(px / width * (n - 1))));
    const point = s.points[i];
    const cx = i / (n - 1) * width;
    const cy = height - 2 - Math.min(1, point[1] / s.max) * (height - 4);

    const group = box.querySelector(".hover");
    if (!group) return;

    group.style.display = "";
    group.querySelector(".hl").setAttribute("x1", cx);
    group.querySelector(".hl").setAttribute("x2", cx);
    group.querySelector(".hc").setAttribute("cx", cx);
    group.querySelector(".hc").setAttribute("cy", cy);

    let tip = box.querySelector(".spark-tip");
    if (!tip) {
        tip = el("div", "spark-tip");
        box.append(tip);
    }

    const ago = Math.max(0, Math.round(Date.now() / 1000 - point[0]));
    tip.innerHTML = "";
    tip.append(el("b", "", s.format(point[1])));
    tip.append(el("span", "", "  " + (ago < 3 ? t("res.now") : t("res.agoSec", { s: ago }))));
    tip.style.left = Math.max(50, Math.min(width - 50, cx)) + "px";
}


["cpuChart", "memChart"].forEach(function(id) {

    const box = $(id);

    box.addEventListener("mousemove", function(event) {
        box._hoverX = event.clientX - box.getBoundingClientRect().left;
        sparkHover(box, box._hoverX);
    });

    box.addEventListener("mouseleave", function() {
        delete box._hoverX;
        const group = box.querySelector(".hover");
        if (group) group.style.display = "none";
        const tip = box.querySelector(".spark-tip");
        if (tip) tip.remove();
    });
});


const PART_COLORS = {
    server: "var(--part-server)",
    backups: "var(--part-backups)",
    docker: "var(--part-docker)",
    swap: "var(--part-swap)",
    system: "var(--part-system)",
    reserved: "var(--part-reserved)"
};


// Parte resaltada por disco; sobrevive a los redibujos cada 2 s
const diskFocus = {};


function setDiskFocus(diskEl, id) {

    diskFocus[diskEl.dataset.disk] = id;
    diskEl.classList.toggle("focus", !!id);

    diskEl.querySelectorAll("[data-part]").forEach(function(node) {
        node.classList.toggle("on", node.dataset.part === id);
    });
}


function renderDisks(disks) {

    const box = $("disks");
    box.textContent = "";

    disks.forEach(function(disk) {

        const wrap = el("div", "disk");
        wrap.dataset.disk = disk.id;

        const head = el("div", "disk-head");
        const title = el("span", "disk-name", t("disk.role." + disk.role));
        title.title = disk.label + " · " + disk.mount;

        if (disk.temp) {
            const dt = disk.temp;
            const hot = dt.current >= dt.high;
            const warm = dt.current >= dt.high - 10;
            const badge = el("span", "disk-temp " + (hot ? "is-red" : warm ? "is-amber" : ""),
                Math.round(dt.current) + " °C" + (hot ? " " + t("disk.hot") : ""));
            badge.title = t("disk.tempTitle", { h: dt.high });
            title.append(badge);
        }

        head.append(
            title,
            el("span", "disk-total",
                t("disk.usedOf", { u: formatBytes(disk.used, 1), t: formatBytes(disk.total, 0) }))
        );

        const stack = el("div", "stack");
        const legend = el("div", "legend");

        const pct = function(size) {
            return size / disk.total * 100;
        };

        const addLegend = function(id, label, size, color, isFree) {

            const row = el("div", "legend-row" + (isFree ? " free" : ""));
            row.dataset.part = id;
            row.title = isFree ? t("disk.freeHint") : t("hint." + id);

            const name = el("span", "legend-name");
            const swatch = el("span", "swatch" + (isFree ? " free" : ""));
            if (color) swatch.style.background = color;
            name.append(swatch, document.createTextNode(label));

            row.append(
                name,
                el("span", "legend-size", size === null ? t("disk.calculating") : formatBytes(size, 1)),
                el("span", "legend-pct", size === null ? "" : pct(size).toFixed(1) + "%")
            );

            row.onmouseenter = function() { setDiskFocus(wrap, id); };
            row.onmouseleave = function() { setDiskFocus(wrap, null); };

            legend.append(row);
        };

        disk.parts.forEach(function(part) {

            const size = part.size;
            const partLabel = t("part." + part.id);
            const color = PART_COLORS[part.id] || "var(--part-system)";

            // Partes vacias (p. ej. reserva en 0%) no se muestran
            if (size !== null && size <= 0) return;

            if (size) {
                const seg = el("span");
                seg.dataset.part = part.id;
                seg.style.width = pct(size) + "%";
                seg.style.background = color;
                seg.title = partLabel + ": " + formatBytes(size, 1) + " (" + pct(size).toFixed(1) + "%)";
                seg.onmouseenter = function() { setDiskFocus(wrap, part.id); };
                seg.onmouseleave = function() { setDiskFocus(wrap, null); };
                stack.append(seg);
            }

            addLegend(part.id, partLabel, size, color, false);
        });

        addLegend("free", t("disk.free"), disk.free, null, true);

        wrap.append(head, stack, legend);
        box.append(wrap);

        if (diskFocus[disk.id]) {
            setDiskFocus(wrap, diskFocus[disk.id]);
        }
    });
}


async function updateStats() {

    if ($("tab-panel").hidden) return;

    try {

        const response = await fetch("/stats?t=" + Date.now());
        const data = await response.json();

        const cpu = data.cpu;
        $("cpuValue").textContent = cpu.percent.toFixed(0) + "%";
        $("cpuSub").innerHTML = "";
        $("cpuSub").append(
            el("div", "", t("res.cores", { n: cpu.cores })),
            el("div", "", t("res.load", { v: cpu.load[0].toFixed(2) })),
            // docker stats mide por nucleo (100% = 1 nucleo); se pasa a % del total
            el("div", "", data.container ? t("res.serverUse", { v: (data.container.cpu / cpu.cores).toFixed(0) + "%" }) : "")
        );

        if (cpu.temp) {

            const ct = cpu.temp;
            const tone = ct.current >= ct.crit ? "red" : ct.current >= ct.high ? "amber" : "green";

            $("tempBox").hidden = false;
            $("tempValue").textContent = Math.round(ct.current) + " °C";
            $("tempState").textContent =
                tone === "red" ? t("res.tempCrit") : tone === "amber" ? t("res.tempHigh") : "";
            setTone($("tempBox").querySelector(".value"), tone);
            $("tempBox").title =
                t("res.tempLimits", { h: ct.high, c: ct.crit });
        }

        renderSpark($("cpuChart"), cpu.history, 100, cssVar("--chart-cpu"), function(v) {
            return t("res.cpuTip", { v: v.toFixed(0) });
        });

        const mem = data.memory;
        $("memValue").textContent = (mem.used / mem.total * 100).toFixed(0) + "%";
        $("memSub").innerHTML = "";
        $("memSub").append(
            el("div", "", formatBytes(mem.used, 1) + " / " + formatBytes(mem.total, 1)),
            el("div", "", data.container ? t("res.serverUse", { v: formatBytes(data.container.mem_used, 1) }) : "")
        );

        renderSpark($("memChart"), mem.history, mem.total, cssVar("--chart-mem"), function(v) {
            return formatBytes(v, 1) + " (" + (v / mem.total * 100).toFixed(0) + "%)";
        });

        renderDisks(data.disks);

        $("uptime").textContent =
            data.uptime ? t("res.uptime", { d: formatDuration(data.uptime) }) : "";

    } catch (error) {
    }
}


// ============================================================
// Modal
// ============================================================

let modalResolve = null;


function openModal(options) {

    $("modalTitle").textContent = options.title || "";
    $("modalHint").textContent = options.hint || "";
    $("modalBox").classList.toggle("wide", !!options.wide);
    $("modalBox").classList.toggle("player-modal", options.cls === "player-modal");
    $("modalCancel").hidden = !!options.hideCancel;

    const body = $("modalBody");
    body.textContent = "";
    (options.body || []).forEach(function(node) {
        body.append(typeof node === "string" ? el("div", "", node) : node);
    });

    const ok = $("modalOk");
    ok.textContent = options.okText || t("modal.ok");
    ok.className = "btn btn-small " + (options.okClass || (options.danger ? "btn-danger" : "btn-start"));
    ok.onclick = function() {
        const value = options.onOk ? options.onOk() : true;
        if (value === false) return;
        closeModal(value);
    };

    $("modal").hidden = false;

    const focus = body.querySelector("input, textarea");
    setTimeout(function() {
        (focus || ok).focus();
    }, 30);

    return new Promise(function(resolve) {
        modalResolve = resolve;
    });
}


function closeModal(value) {

    if ($("modal").hidden) return;

    $("modal").hidden = true;

    if (modalResolve) {
        const resolve = modalResolve;
        modalResolve = null;
        resolve(value === undefined ? null : value);
    }
}


function askText(title, label, value, okText) {

    const input = el("input", "input");
    input.value = value || "";
    input.onkeydown = function(event) {
        if (event.key === "Enter") $("modalOk").click();
    };

    return openModal({
        title: title,
        body: [label, input],
        okText: okText,
        onOk: function() {
            return input.value.trim() || false;
        }
    });
}


function confirmDialog(title, message, okText) {
    return openModal({
        title: title,
        body: [message],
        okText: okText || t("modal.delete"),
        danger: true
    });
}


document.addEventListener("keydown", function(event) {
    if (event.key === "Escape") closeModal();
});


// ============================================================
// Sesion
// ============================================================

let filesReady = false;
let currentPath = "";


async function api(url, options) {

    const response = await fetch(url, options);

    if (response.status === 401) {
        showLogin();
        throw new Error("auth");
    }

    const data = await response.json().catch(function() {
        return { ok: false, message: t("fm.badResponse") };
    });

    if (!response.ok || data.ok === false) {
        throw new Error(serverText(data.message) || "Error");
    }

    return data;
}


// La consola comparte la sesion del area de archivos
let consoleLocked = true;
let consolePane = "chat";


// En pantallas angostas los paneles se alternan con pestanas
function isNarrow() {
    return window.matchMedia("(max-width: 899px)").matches;
}


function setConsoleLocked(locked) {
    consoleLocked = locked;
    renderConsoleBars();
    if (locked) $("consolePassword").value = "";
}


function renderConsoleBars() {

    // Solo la consola pide contrasena; el chat esta abierto
    $("commandBar").hidden = consoleLocked;
    $("commandLock").hidden = !consoleLocked;
}


async function checkConsoleSession() {
    try {
        const response = await fetch("/files/session");
        const data = await response.json();
        setConsoleLocked(!data.authorized);
    } catch (error) {
        setConsoleLocked(true);
    }
}


async function unlockConsole(event) {

    event.preventDefault();

    try {
        const response = await fetch("/files/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: $("consolePassword").value })
        });

        const data = await response.json();

        if (!data.ok) {
            showToast(serverText(data.message), "red");
            $("consolePassword").select();
            return;
        }

        setConsoleLocked(false);
        showToast(t("console.unlocked"), "green");
        $("command").focus();

    } catch (error) {
        showToast(t("login.noConnection"), "red");
    }
}


let authorized = false;


function showLogin() {

    authorized = false;
    filesReady = false;
    setConsoleLocked(true);

    $("filesArea").hidden = true;
    $("settingsArea").hidden = true;
    $("playersArea").hidden = true;

    const card = $("loginCard");

    // Al bloquear desde la consola (pestana Panel) no se muestra el formulario
    if (activeTab === "panel") {
        card.hidden = true;
        return;
    }

    $("tab-" + activeTab).prepend(card);
    card.hidden = false;
    $("password").value = "";
    $("loginError").textContent = "";
    setTimeout(function() { $("password").focus(); }, 30);
}


function enterTab() {

    authorized = true;
    setConsoleLocked(false);
    $("loginCard").hidden = true;

    if (activeTab === "files") {
        filesReady = true;
        $("filesArea").hidden = false;
        loadFolder(currentPath);
        loadBackups();
    } else if (activeTab === "players") {
        $("playersArea").hidden = false;
        loadPlayers();
    } else if (activeTab === "settings") {
        $("settingsArea").hidden = false;

        // No se pisan los cambios sin guardar al volver a la pestana
        if (settingsSaved && Object.keys(settingsChanges()).length) renderSettings();
        else loadSettings();
    }
}


async function openProtected() {

    if (authorized) {
        enterTab();
        return;
    }

    try {
        const response = await fetch("/files/session");
        const data = await response.json();

        if (!data.authorized) {
            showLogin();
            return;
        }

        enterTab();

    } catch (error) {
        showLogin();
    }
}


async function login(event) {

    event.preventDefault();

    $("loginError").textContent = "";

    try {
        const response = await fetch("/files/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: $("password").value })
        });

        const data = await response.json();

        if (!data.ok) {
            $("loginError").textContent = serverText(data.message);
            $("password").select();
            return;
        }

        enterTab();

    } catch (error) {
        $("loginError").textContent = t("login.noConnection");
    }
}


async function logout() {
    await fetch("/files/logout", { method: "POST" }).catch(function() {});
    showLogin();
}


// ============================================================
// Gestor de archivos
// ============================================================

const TEXT_EXT = [
    "txt", "properties", "json", "json5", "toml", "yml", "yaml", "cfg",
    "conf", "ini", "log", "md", "sh", "bat", "ps1", "mcmeta", "js",
    "snbt", "csv", "xml", "env", "list"
];


function isText(name) {
    const ext = name.toLowerCase().split(".").pop();
    return name.startsWith(".") && !name.slice(1).includes(".") || TEXT_EXT.includes(ext);
}


function joinPath(folder, name) {
    return folder ? folder + "/" + name : name;
}


function formatStamp(ts) {
    return new Date(ts * 1000).toLocaleString(locale(), {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
    });
}


function renderBreadcrumb(path) {

    const box = $("breadcrumb");
    box.textContent = "";

    const parts = path ? path.split("/") : [];
    const crumbs = [["minecraft-server", ""]];

    parts.forEach(function(part, i) {
        crumbs.push([part, parts.slice(0, i + 1).join("/")]);
    });

    crumbs.forEach(function([label, target], i) {
        if (i) box.append(el("span", "sep", "/"));
        const link = el("a", "", label);
        link.onclick = function() { loadFolder(target); };
        makeDropTarget(link, target);
        box.append(link);
    });
}


let fmEntries = [];
let fmSelected = new Set();
let fmSort = { key: "name", dir: 1 };
let fmClipboard = null;
let fmLastClicked = null;

const DRAG_TYPE = "application/x-mc-paths";


function parentPath(path) {
    return path.split("/").slice(0, -1).join("/");
}


function goUp() {
    if (currentPath) loadFolder(parentPath(currentPath));
}


async function loadFolder(path) {

    try {

        const data = await api("/files/list?path=" + encodeURIComponent(path));

        if (data.path !== currentPath) {
            fmSelected.clear();
            fmLastClicked = null;
            $("fmFilter").value = "";
        }

        currentPath = data.path;
        fmEntries = data.entries;

        // Quita de la seleccion lo que ya no existe
        const names = new Set(fmEntries.map(function(e) { return e.name; }));
        fmSelected.forEach(function(name) {
            if (!names.has(name)) fmSelected.delete(name);
        });

        renderBreadcrumb(currentPath);
        renderFiles();

    } catch (error) {
        if (error.message !== "auth") {
            showToast(error.message, "red");
            if (path) loadFolder("");
        }
    }
}


function visibleEntries() {

    const filter = $("fmFilter").value.trim().toLowerCase();
    const key = fmSort.key;

    return fmEntries
        .filter(function(e) {
            return !filter || e.name.toLowerCase().includes(filter);
        })
        .sort(function(a, b) {
            // Las carpetas siempre van primero
            if (a.dir !== b.dir) return a.dir ? -1 : 1;

            const x = key === "name" ? a.name.toLowerCase() : a[key];
            const y = key === "name" ? b.name.toLowerCase() : b[key];

            if (x < y) return -fmSort.dir;
            if (x > y) return fmSort.dir;
            return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1;
        });
}


function setSort(key) {
    fmSort = {
        key: key,
        dir: fmSort.key === key ? -fmSort.dir : 1
    };
    renderFiles();
}


function renderFiles() {

    const list = $("fileList");
    const entries = visibleEntries();

    list.textContent = "";

    $("fmUp").disabled = !currentPath;

    ["name", "size", "mtime"].forEach(function(key) {
        $("sort-" + key).textContent =
            fmSort.key === key ? (fmSort.dir === 1 ? " ↑" : " ↓") : "";
    });

    if (!entries.length) {
        list.append(el("div", "list-empty",
            fmEntries.length ? t("fm.noMatch") : t("fm.empty")));
    }

    entries.forEach(function(entry) {
        list.append(fileRow(entry));
    });

    renderSelection();
}


function renderSelection() {

    const count = fmSelected.size;
    const visible = visibleEntries();

    document.querySelectorAll("#fileList .row").forEach(function(row) {
        const on = fmSelected.has(row.dataset.name);
        row.classList.toggle("selected", on);
        const box = row.querySelector(".check");
        if (box) box.checked = on;
    });

    const all = $("fmAll");
    const selectedVisible = visible.filter(function(e) { return fmSelected.has(e.name); }).length;
    all.checked = visible.length > 0 && selectedVisible === visible.length;
    all.indeterminate = selectedVisible > 0 && selectedVisible < visible.length;

    $("fmSelection").hidden = count === 0 || !!fmClipboard;
    $("fmSelectionText").textContent = tn("fm.selected", count);
    $("fmRenameBtn").hidden = count !== 1;

    $("fmMove").hidden = !fmClipboard;

    if (fmClipboard) {
        $("fmMoveText").textContent = tn("fm.moving", fmClipboard.paths.length);
    }
}


function toggleSelect(name, on) {
    if (on === undefined ? !fmSelected.has(name) : on) fmSelected.add(name);
    else fmSelected.delete(name);
}


function toggleAll(on) {
    visibleEntries().forEach(function(e) { toggleSelect(e.name, on); });
    renderSelection();
}


function clearSelection() {
    fmSelected.clear();
    fmLastClicked = null;
    renderSelection();
}


function selectedPaths() {
    return Array.from(fmSelected).map(function(name) {
        return joinPath(currentPath, name);
    });
}


function openEntry(entry) {

    const full = joinPath(currentPath, entry.name);

    if (entry.dir) loadFolder(full);
    else if (isText(entry.name)) editFile(full);
    else downloadFile(full);
}


function fileRow(entry) {

    const full = joinPath(currentPath, entry.name);
    const row = el("div", "row");
    row.dataset.name = entry.name;
    row.draggable = true;

    const check = el("input", "check");
    check.type = "checkbox";
    check.onclick = function(event) { event.stopPropagation(); };
    check.onchange = function() {
        toggleSelect(entry.name, check.checked);
        fmLastClicked = entry.name;
        renderSelection();
    };

    const icon = el("span", "row-icon" + (entry.dir ? " folder" : ""));
    icon.innerHTML = entry.dir ? ICONS.folder
        : /\.(zip|jar|gz|tar|7z|rar)$/i.test(entry.name) ? ICONS.archive
        : isText(entry.name) ? ICONS.text
        : ICONS.file;

    const name = el("span", "row-name");
    const link = el("a", "", entry.name);
    link.title = entry.name;
    link.onclick = function(event) {
        event.stopPropagation();
        openEntry(entry);
    };
    name.append(link);

    const size = el("span", "row-meta row-size", entry.dir ? "" : formatBytes(entry.size));
    const date = el("span", "row-meta row-date", formatStamp(entry.mtime));

    const actions = el("span", "row-actions");

    if (!entry.dir && isText(entry.name)) {
        actions.append(iconButton("edit", t("fm.edit"), function() { editFile(full); }));
    }

    actions.append(iconButton("download", entry.dir ? t("fm.downloadZip") : t("fm.download"), function() {
        if (entry.dir) downloadZip([full]);
        else downloadFile(full);
    }));
    actions.append(iconButton("rename", t("fm.rename"), function() { renameItem(full, entry.name); }));
    actions.append(iconButton("trash", t("fm.delete"), function() { deleteItem(full, entry); }, true));

    row.append(check, icon, name, size, date, actions);

    // Clic en la fila: seleccionar. Con Shift selecciona el rango.
    row.onclick = function(event) {

        if (event.shiftKey && fmLastClicked) {
            const names = visibleEntries().map(function(e) { return e.name; });
            const a = names.indexOf(fmLastClicked);
            const b = names.indexOf(entry.name);

            if (a !== -1 && b !== -1) {
                names.slice(Math.min(a, b), Math.max(a, b) + 1).forEach(function(n) {
                    toggleSelect(n, true);
                });
            }
        } else {
            toggleSelect(entry.name);
            fmLastClicked = entry.name;
        }

        renderSelection();
    };

    row.ondblclick = function() {
        openEntry(entry);
    };

    // Arrastrar filas para moverlas a otra carpeta
    row.addEventListener("dragstart", function(event) {

        if (!fmSelected.has(entry.name)) {
            fmSelected.clear();
            fmSelected.add(entry.name);
            renderSelection();
        }

        event.dataTransfer.setData(DRAG_TYPE, JSON.stringify(selectedPaths()));
        event.dataTransfer.effectAllowed = "move";
    });

    if (entry.dir) {
        makeDropTarget(row, full);
    }

    return row;
}


function isInternalDrag(event) {
    return Array.from(event.dataTransfer.types || []).includes(DRAG_TYPE);
}


function hasFiles(event) {
    return Array.from(event.dataTransfer.types || []).includes("Files");
}


// Una carpeta (fila o miga de pan) acepta filas arrastradas (mover)
// y archivos del equipo (subir a esa carpeta)
function makeDropTarget(node, folder) {

    node.addEventListener("dragover", function(event) {
        if (isInternalDrag(event) || hasFiles(event)) {
            event.preventDefault();
            event.stopPropagation();
            node.classList.add("drop-target");
            $("fmOverlayText").textContent =
                t("fm.dropOverlay", { folder: folder || "minecraft-server" });
        }
    });

    node.addEventListener("dragleave", function() {
        node.classList.remove("drop-target");
    });

    node.addEventListener("drop", function(event) {

        node.classList.remove("drop-target");

        if (isInternalDrag(event)) {
            event.preventDefault();
            event.stopPropagation();

            let paths = [];
            try { paths = JSON.parse(event.dataTransfer.getData(DRAG_TYPE)); } catch (error) {}

            movePaths(paths, folder);

        } else if (hasFiles(event)) {
            event.preventDefault();
            event.stopPropagation();
            endExternalDrag();
            uploadDropped(event.dataTransfer, folder);
        }
    });
}


async function movePaths(paths, dest) {

    if (!paths.length) return;

    try {
        const data = await api("/files/move", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ paths: paths, dest: dest })
        });

        showToast(tn("fm.moved", data.count), "green");
        fmSelected.clear();
        fmClipboard = null;
        loadFolder(currentPath);

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


function bulkMove() {
    if (!fmSelected.size) return;
    fmClipboard = { paths: selectedPaths() };
    fmSelected.clear();
    renderSelection();
}


function moveHere() {
    if (fmClipboard) movePaths(fmClipboard.paths, currentPath);
}


function cancelMove() {
    fmClipboard = null;
    renderSelection();
}


function bulkRename() {
    if (fmSelected.size !== 1) return;
    const name = Array.from(fmSelected)[0];
    renameItem(joinPath(currentPath, name), name);
}


function bulkDownload() {

    const names = Array.from(fmSelected);
    if (!names.length) return;

    const entry = fmEntries.find(function(e) { return e.name === names[0]; });

    if (names.length === 1 && entry && !entry.dir) {
        downloadFile(joinPath(currentPath, names[0]));
    } else {
        downloadZip(selectedPaths());
    }
}


function downloadZip(paths) {
    showToast(t("fm.preparingZip"), "amber");
    const link = document.createElement("a");
    link.href = "/files/zip?paths=" + encodeURIComponent(JSON.stringify(paths));
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
}


async function bulkDelete() {

    const paths = selectedPaths();
    if (!paths.length) return;

    if (paths.length === 1) {
        const name = Array.from(fmSelected)[0];
        const entry = fmEntries.find(function(e) { return e.name === name; });
        if (entry) deleteItem(paths[0], entry);
        return;
    }

    const ok = await confirmDialog(t("modal.delete"), t("fm.deleteMany", { n: paths.length }));
    if (!ok) return;

    try {
        const data = await api("/files/delete-many", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ paths: paths })
        });

        showToast(t("fm.deletedMany", { n: data.count }), "green");
        fmSelected.clear();
        loadFolder(currentPath);

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


// Atajos: Supr borra la seleccion, Esc la quita, Ctrl+A selecciona todo
document.addEventListener("keydown", function(event) {

    if ($("tab-files").hidden || !filesReady || !$("modal").hidden) return;
    if (/^(INPUT|TEXTAREA)$/.test(event.target.tagName)) return;

    if (event.key === "Delete" && fmSelected.size) {
        event.preventDefault();
        bulkDelete();
    } else if (event.key === "F2" && fmSelected.size === 1) {
        event.preventDefault();
        bulkRename();
    } else if (event.key === "Escape") {
        if (fmClipboard) cancelMove();
        else clearSelection();
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
        event.preventDefault();
        toggleAll(true);
    }
});


function downloadFile(path) {
    const link = document.createElement("a");
    link.href = "/files/download?path=" + encodeURIComponent(path);
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
}


async function editFile(path) {

    let data;

    try {
        data = await api("/files/read?path=" + encodeURIComponent(path));
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
        return;
    }

    const editor = el("textarea", "editor");
    editor.value = data.content;
    editor.spellcheck = false;

    editor.addEventListener("keydown", function(event) {

        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
            event.preventDefault();
            $("modalOk").click();
        }

        if (event.key === "Tab") {
            event.preventDefault();
            const start = editor.selectionStart;
            editor.setRangeText("    ", start, editor.selectionEnd, "end");
        }
    });

    const original = data.content;

    await openModal({
        title: path,
        body: [editor],
        wide: true,
        okText: t("fm.save"),
        hint: t("fm.editorHint"),
        onOk: function() {
            if (editor.value === original) return true;
            saveFile(path, editor.value);
            return true;
        }
    });
}


async function saveFile(path, content) {

    try {
        await api("/files/write?path=" + encodeURIComponent(path), {
            method: "POST",
            headers: { "Content-Type": "text/plain; charset=utf-8" },
            body: content
        });

        showToast(t("fm.saved"), "green");
        loadFolder(currentPath);

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function newFolder() {

    const name = await askText(t("fm.newFolder"), t("fm.folderName"), "", t("fm.create"));
    if (!name) return;

    try {
        await api(
            "/files/mkdir?path=" + encodeURIComponent(currentPath)
            + "&name=" + encodeURIComponent(name),
            { method: "POST" }
        );
        showToast(t("fm.created"), "green");
        loadFolder(currentPath);
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function renameItem(path, current) {

    const name = await askText(t("fm.rename"), t("fm.newName"), current, t("fm.rename"));
    if (!name || name === current) return;

    try {
        await api(
            "/files/rename?path=" + encodeURIComponent(path)
            + "&name=" + encodeURIComponent(name),
            { method: "POST" }
        );
        showToast(t("fm.renamed"), "green");
        loadFolder(currentPath);
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function deleteItem(path, entry) {

    const message = entry.dir
        ? t("fm.deleteFolder", { name: entry.name })
        : t("fm.deleteFile", { name: entry.name });

    const ok = await confirmDialog(t("modal.delete"), message);
    if (!ok) return;

    try {
        await api("/files/delete?path=" + encodeURIComponent(path), { method: "POST" });
        showToast(t("fm.deleted"), "green");
        loadFolder(currentPath);
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


// Cola de subidas: como mucho 3 a la vez
const uploadQueue = [];
let uploadsActive = 0;
let uploadsDone = 0;
let uploadsFailed = 0;


function uploadFiles(files, folder) {

    const target = folder === undefined ? currentPath : folder;

    Array.from(files).forEach(function(file) {
        uploadQueue.push({ file: file, folder: target });
    });

    pumpUploads();
}


function pumpUploads() {

    while (uploadsActive < 3 && uploadQueue.length) {
        const job = uploadQueue.shift();
        uploadsActive++;
        uploadOne(job.file, job.folder, function(ok) {
            uploadsActive--;
            if (ok) uploadsDone++;
            else uploadsFailed++;
            pumpUploads();
        });
    }

    // Al terminar toda la tanda se avisa una sola vez
    if (!uploadsActive && !uploadQueue.length && (uploadsDone || uploadsFailed)) {

        if (uploadsDone) {
            showToast(tn("fm.uploadedCount", uploadsDone), uploadsFailed ? "amber" : "green");
        }

        uploadsDone = 0;
        uploadsFailed = 0;

        if (filesReady) loadFolder(currentPath);
    }
}


function uploadOne(file, folder, done) {

    const item = el("div", "upload");
    const label = el("div", "", t("fm.uploading", { name: file.name }));
    const meter = el("div", "meter");
    const bar = el("span");
    bar.style.width = "0%";
    bar.style.background = "var(--blue)";
    meter.append(bar);
    item.append(label, meter);
    $("uploads").append(item);

    const xhr = new XMLHttpRequest();

    xhr.open(
        "POST",
        "/files/upload?path=" + encodeURIComponent(folder)
        + "&name=" + encodeURIComponent(file.name)
    );

    xhr.upload.onprogress = function(event) {
        if (event.lengthComputable) {
            const pct = event.loaded / event.total * 100;
            bar.style.width = pct + "%";
            label.textContent =
                t("fm.uploadProgress", { name: file.name, done: formatBytes(event.loaded), total: formatBytes(event.total) });
        }
    };

    xhr.onload = function() {

        item.remove();

        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (error) {}

        if (xhr.status === 401) {
            uploadQueue.length = 0;
            showLogin();
            done(false);
            return;
        }

        if (xhr.status === 200 && data.ok) {
            done(true);
        } else {
            showToast(file.name + ": " + (serverText(data.message) || t("fm.uploadError", { name: file.name })), "red");
            done(false);
        }
    };

    xhr.onerror = function() {
        item.remove();
        showToast(t("fm.uploadError", { name: file.name }), "red");
        done(false);
    };

    xhr.send(file);
}


// Recorre una carpeta soltada y devuelve sus archivos con su subcarpeta
function readEntry(entry, folder) {

    return new Promise(function(resolve) {

        if (entry.isFile) {
            entry.file(function(file) {
                resolve([{ file: file, folder: folder }]);
            }, function() {
                resolve([]);
            });
            return;
        }

        if (!entry.isDirectory) {
            resolve([]);
            return;
        }

        const reader = entry.createReader();
        const sub = joinPath(folder, entry.name);
        let all = [];

        // readEntries entrega los resultados por tandas
        (function next() {
            reader.readEntries(function(batch) {

                if (!batch.length) {
                    Promise.all(all.map(function(child) {
                        return readEntry(child, sub);
                    })).then(function(lists) {
                        resolve([].concat.apply([], lists));
                    });
                    return;
                }

                all = all.concat(Array.from(batch));
                next();

            }, function() {
                resolve([]);
            });
        })();
    });
}


async function uploadDropped(dataTransfer, folder) {

    const items = Array.from(dataTransfer.items || []);
    const entries = items
        .map(function(item) {
            return item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
        })
        .filter(Boolean);

    // Navegadores sin soporte de carpetas: solo archivos sueltos
    if (!entries.length) {
        uploadFiles(dataTransfer.files, folder);
        return;
    }

    const lists = await Promise.all(entries.map(function(entry) {
        return readEntry(entry, folder);
    }));

    [].concat.apply([], lists).forEach(function(job) {
        uploadQueue.push(job);
    });

    pumpUploads();
}


let fmDragDepth = 0;


function endExternalDrag() {
    fmDragDepth = 0;
    $("dropZone").classList.remove("dragging");
}


// Se puede soltar en cualquier parte de la pestana de Archivos: todo
// el explorador es la zona de subida. Soltar sobre una carpeta de la
// lista sube ahi (lo maneja makeDropTarget).
(function() {

    const zone = $("dropZone");

    function active(event) {
        return filesReady && !$("tab-files").hidden && $("modal").hidden
            && hasFiles(event) && !isInternalDrag(event);
    }

    document.addEventListener("dragenter", function(event) {
        if (!active(event)) return;
        event.preventDefault();
        fmDragDepth++;
        zone.classList.add("dragging");
    });

    document.addEventListener("dragleave", function(event) {
        if (!active(event)) return;
        fmDragDepth = Math.max(0, fmDragDepth - 1);
        if (!fmDragDepth) zone.classList.remove("dragging");
    });

    document.addEventListener("dragover", function(event) {
        if (!active(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        $("fmOverlayText").textContent =
            t("fm.dropOverlay", { folder: currentPath || "minecraft-server" });
    });

    document.addEventListener("drop", function(event) {

        const ok = active(event);
        endExternalDrag();

        if (!ok) return;

        event.preventDefault();
        uploadDropped(event.dataTransfer, currentPath);
    });

    // Fuera de la pestana de Archivos el navegador no debe abrir el archivo
    ["dragover", "drop"].forEach(function(type) {
        window.addEventListener(type, function(event) {
            if (hasFiles(event)) event.preventDefault();
        });
    });
})();


// ============================================================
// Respaldos
// ============================================================

let backupWasRunning = false;


async function loadBackups() {

    if (!filesReady || $("tab-files").hidden) return;

    try {

        const data = await api("/backups?t=" + Date.now());

        const btn = $("backupBtn");
        btn.disabled = data.running;
        btn.innerHTML = data.running
            ? '<span class="spinner"></span> ' + t("bk.running")
            : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M12 5v14M5 12h14"/></svg> ' + t("bk.now");

        if (backupWasRunning && !data.running) {
            const failed = /ERROR|cancelado/i.test(data.last_log);
            showToast(failed ? t("bk.failed") : t("bk.done"), failed ? "red" : "green");
        }

        backupWasRunning = data.running;

        const info = $("backupInfo");
        info.textContent = "";

        const next = el("span");
        next.append(t("bk.nextAuto"));
        next.append(el("b", "", data.next_auto ? formatStamp(data.next_auto) : t("bk.notScheduled")));

        const keep = el("span", "", t("bk.keep"));

        info.append(next, keep);

        const list = $("backups");
        list.textContent = "";

        if (!data.backups.length) {
            list.append(el("div", "list-empty", data.running ? t("bk.creatingFirst") : t("bk.none")));
            return;
        }

        data.backups.forEach(function(backup) {

            const row = el("div", "row backup-row");

            const icon = el("span", "row-icon");
            icon.innerHTML = ICONS.archive;

            const name = el("span", "row-name");
            const tag = el("span", "tag " + (backup.type === "auto" ? "blue" : "green"),
                backup.type === "auto" ? t("bk.auto") : t("bk.manual"));
            tag.style.marginRight = "10px";
            name.append(tag, document.createTextNode(formatStamp(backup.mtime)));
            name.title = backup.name;

            const actions = el("span", "row-actions");
            actions.append(
                iconButton("download", t("fm.download"), function() {
                    const link = document.createElement("a");
                    link.href = "/backups/download?name=" + encodeURIComponent(backup.name);
                    link.download = backup.name;
                    document.body.append(link);
                    link.click();
                    link.remove();
                }),
                iconButton("trash", t("fm.delete"), function() { deleteBackup(backup); }, true)
            );

            row.append(
                icon,
                name,
                el("span", "row-meta row-size", formatBytes(backup.size, 1)),
                el("span", "row-meta row-date", backup.name.replace(/\.tar\.gz$/, "")),
                actions
            );

            list.append(row);
        });

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function createBackup() {

    try {
        await api("/backups/create", { method: "POST" });
        backupWasRunning = true;
        showToast(t("bk.started"), "amber");
        setTimeout(loadBackups, 800);
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function deleteBackup(backup) {

    const ok = await confirmDialog(
        t("bk.deleteTitle"),
        t("bk.deleteBody", { d: formatStamp(backup.mtime), s: formatBytes(backup.size, 1) })
    );

    if (!ok) return;

    try {
        await api("/backups/delete?name=" + encodeURIComponent(backup.name), { method: "POST" });
        showToast(t("bk.deleted"), "green");
        loadBackups();
    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


// ============================================================
// Ajustes del servidor
// ============================================================

// Debe coincidir con SETTINGS del servidor, que vuelve a validar todo
const SETTINGS_GROUPS = [
    {
        id: "game",
        keys: ["difficulty", "gamemode", "force-gamemode", "hardcore", "pvp",
            "allow-flight", "enable-command-block", "spawn-protection", "player-idle-timeout"]
    },
    {
        id: "world",
        keys: ["spawn-monsters", "spawn-animals", "spawn-npcs", "allow-nether",
            "view-distance", "simulation-distance"]
    },
    {
        id: "players",
        keys: ["max-players", "white-list", "enforce-whitelist", "online-mode",
            "hide-online-players", "motd"]
    }
];

const SETTINGS_TYPES = {
    "difficulty": { type: "enum", options: ["peaceful", "easy", "normal", "hard"] },
    "gamemode": { type: "enum", options: ["survival", "creative", "adventure", "spectator"] },
    "spawn-protection": { type: "int", min: 0, max: 256 },
    "player-idle-timeout": { type: "int", min: 0, max: 1440 },
    "view-distance": { type: "int", min: 3, max: 32 },
    "simulation-distance": { type: "int", min: 3, max: 32 },
    "max-players": { type: "int", min: 1, max: 200 },
    "motd": { type: "text", max: 59 }
};

let settingsSaved = null;
let settingsDraft = {};
let settingsLive = [];
let settingsRunning = false;
let settingsRestart = false;


function settingType(key) {
    return SETTINGS_TYPES[key] || { type: "bool" };
}


function settingsChanges() {

    const changes = {};

    Object.keys(settingsDraft).forEach(function(key) {
        if (settingsSaved && settingsDraft[key] !== settingsSaved[key]) {
            changes[key] = settingsDraft[key];
        }
    });

    return changes;
}


async function loadSettings() {

    try {
        const data = await api("/settings?t=" + Date.now());

        settingsSaved = data.values;
        settingsDraft = Object.assign({}, data.values);
        settingsLive = data.live || [];
        settingsRunning = data.running;

        renderSettings();

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


function settingControl(key) {

    const info = settingType(key);
    const value = settingsDraft[key];

    if (info.type === "bool") {

        const btn = el("button", "switch" + (value === "true" ? " on" : ""));
        btn.type = "button";
        btn.setAttribute("role", "switch");
        btn.setAttribute("aria-checked", value === "true" ? "true" : "false");
        btn.setAttribute("aria-label", t("set." + key));
        btn.append(el("span", "switch-knob"));

        btn.onclick = function() {
            settingsDraft[key] = settingsDraft[key] === "true" ? "false" : "true";
            const on = settingsDraft[key] === "true";
            btn.classList.toggle("on", on);
            btn.setAttribute("aria-checked", on ? "true" : "false");
            renderSettingsBar();
        };

        return btn;
    }

    if (info.type === "enum") {

        const select = el("select", "input set-input");

        info.options.forEach(function(option) {
            const node = el("option", "", t("opt." + option) || option);
            node.value = option;
            select.append(node);
        });

        select.value = value;
        select.onchange = function() {
            settingsDraft[key] = select.value;
            renderSettingsBar();
        };

        return select;
    }

    const input = el("input", "input set-input" + (info.type === "text" ? " wide" : ""));

    if (info.type === "int") {
        input.type = "number";
        input.min = info.min;
        input.max = info.max;
        input.step = 1;
    } else {
        input.type = "text";
        input.maxLength = info.max;
    }

    input.value = value;

    input.oninput = function() {

        let next = input.value;
        let valid = true;

        if (info.type === "int") {
            const number = Number(next);
            valid = /^\d+$/.test(next.trim()) && number >= info.min && number <= info.max;
            next = valid ? String(number) : next;
        }

        input.classList.toggle("invalid", !valid);
        settingsDraft[key] = next;
        renderSettingsBar();
    };

    return input;
}


function renderSettings() {

    const box = $("settingsGroups");
    box.textContent = "";

    if (!settingsSaved) return;

    SETTINGS_GROUPS.forEach(function(group) {

        const card = el("div", "card");
        const head = el("div", "card-head");
        head.append(el("h3", "card-title", t("set.group." + group.id)));
        card.append(head);

        const list = el("div", "set-list");

        group.keys.forEach(function(key) {

            const row = el("div", "set-row");
            const text = el("div", "set-text");
            const label = el("div", "set-label", t("set." + key));

            if (settingsLive.includes(key)) {
                label.append(el("span", "tag green set-live", t("set.live")));
            }

            text.append(label, el("div", "set-desc", t("set." + key + ".d")));
            row.append(text, settingControl(key));
            list.append(row);
        });

        card.append(list);
        box.append(card);
    });

    $("settingsNote").textContent = settingsRunning ? "" : t("set.offNote");
    $("settingsNote").hidden = settingsRunning;

    renderSettingsBar();
}


function settingsValid() {
    return !document.querySelector("#settingsGroups .invalid");
}


function renderSettingsBar() {

    const count = Object.keys(settingsChanges()).length;

    $("settingsBar").hidden = count === 0;
    $("settingsBarText").textContent = tn("set.unsaved", count);
    $("settingsSave").disabled = !settingsValid();

    $("settingsRestart").hidden = !settingsRestart || count > 0;
}


function discardSettings() {
    settingsDraft = Object.assign({}, settingsSaved);
    renderSettings();
}


async function saveSettings() {

    const changes = settingsChanges();

    if (!Object.keys(changes).length || !settingsValid()) return;

    $("settingsSave").disabled = true;

    try {
        const data = await api("/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ values: changes })
        });

        settingsRestart = settingsRestart || data.restart;

        showToast(
            data.restart ? t("set.savedRestart")
                : data.applied && data.applied.length ? t("set.savedApplied")
                : t("set.saved"),
            data.restart ? "amber" : "green"
        );

        await loadSettings();

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
        $("settingsSave").disabled = false;
    }
}


async function openUninstall() {

    const name = document.querySelector("h1").textContent.trim();

    const keepData = el("label", "un-check");
    const dataBox = el("input");
    dataBox.type = "checkbox";
    keepData.append(dataBox, document.createTextNode(" " + t("un.purgeData")));

    const keepBackups = el("label", "un-check");
    const backupsBox = el("input");
    backupsBox.type = "checkbox";
    keepBackups.append(backupsBox, document.createTextNode(" " + t("un.purgeBackups")));

    const input = el("input", "input");
    input.placeholder = name;

    const ok = await openModal({
        title: t("un.label"),
        body: [
            t("un.modalDesc"),
            keepData,
            keepBackups,
            t("un.typeName", { name: name }),
            input
        ],
        okText: t("un.button"),
        danger: true,
        onOk: function() {
            return input.value.trim() === name ? true : false;
        }
    });

    if (!ok) return;

    try {
        await api("/system/uninstall", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                confirm: input.value.trim(),
                purge_data: dataBox.checked,
                purge_backups: backupsBox.checked
            })
        });

        document.body.innerHTML = "";
        const done = el("div", "un-done");
        done.append(el("h2", "", t("un.doneTitle")), el("p", "", t("un.doneDesc")));
        document.body.append(done);

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


async function restartFromSettings() {

    if (await confirmRestart()) {
        settingsRestart = false;
        renderSettingsBar();
    }
}


// ============================================================
// Jugadores
// ============================================================

let playersData = null;
let playerFilter = "all";
let openPlayerName = null;
let skinViewer = null;
let skinLibPromise = null;
let playerPanelDirty = false;

const TIMEOUT_OPTIONS = [5, 15, 60, 360, 1440, 10080];


function loadSkinLib() {

    if (window.skinview3d) return Promise.resolve();

    if (!skinLibPromise) {
        skinLibPromise = new Promise(function(resolve, reject) {
            const script = document.createElement("script");
            script.src = "https://cdn.jsdelivr.net/npm/skinview3d@3.1.0/bundles/skinview3d.bundle.js";
            script.onload = resolve;
            script.onerror = function() {
                skinLibPromise = null;
                reject(new Error("skinview3d"));
            };
            document.head.append(script);
        });
    }

    return skinLibPromise;
}


function timeAgo(ts) {

    if (!ts) return t("pl.never");

    const seconds = Math.round(ts - Date.now() / 1000);
    const abs = Math.abs(seconds);
    const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: "auto" });

    if (abs < 60) return rtf.format(Math.round(seconds), "second");
    if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
    if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
    return rtf.format(Math.round(seconds / 86400), "day");
}


function formatMinutes(minutes) {
    if (minutes < 60) return t("pl.dur.min", { n: minutes });
    if (minutes < 1440) return t("pl.dur.hour", { n: minutes / 60 });
    return t("pl.dur.day", { n: minutes / 1440 });
}


async function loadPlayers() {

    try {
        playersData = await api("/players?t=" + Date.now());
        renderPlayers();

        if (openPlayerName) {
            const player = findPlayer(openPlayerName);
            if (player && !$("modal").hidden) {
                // Tras una accion se redibuja todo; en la recarga periodica solo
                // el estado, para no borrar lo que se este escribiendo
                if (playerPanelDirty) renderPlayerPanel(player);
                else renderPlayerSide(player);
                playerPanelDirty = false;
            }
        }

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
    }
}


function findPlayer(name) {
    return playersData && playersData.players.find(function(p) {
        return p.name.toLowerCase() === name.toLowerCase();
    });
}


function setPlayerFilter(filter) {
    playerFilter = filter;
    document.querySelectorAll(".pl-filters .tab-btn").forEach(function(btn) {
        btn.classList.toggle("active", btn.dataset.filter === filter);
    });
    renderPlayers();
}


function playerBadges(player) {

    const box = el("span", "pl-badges");

    if (player.op) box.append(el("span", "tag amber", t("pl.badge.op")));
    if (player.whitelisted) box.append(el("span", "tag blue", t("pl.badge.whitelist")));

    if (player.ban) {
        box.append(el("span", "tag red",
            player.ban.until ? t("pl.badge.timeout") : t("pl.badge.banned")));
    }

    return box;
}


function playerStatus(player) {
    if (player.online) return t("pl.onlineNow");
    if (player.ban && player.ban.until) {
        return t("pl.timeoutUntil", { d: new Date(player.ban.until * 1000).toLocaleString(locale(), {
            day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"
        }) });
    }
    return player.last_seen ? t("pl.lastSeen", { d: timeAgo(player.last_seen) }) : t("pl.neverJoined");
}


function renderPlayers() {

    if (!playersData) return;

    const list = $("playerList");
    const query = $("playerSearch").value.trim().toLowerCase();
    const all = playersData.players;

    $("playersCount").textContent = t("pl.count", {
        online: playersData.online.length,
        total: all.length
    });

    $("playersNote").hidden = playersData.running;
    $("playersNote").textContent = playersData.running ? "" : t("pl.offNote");

    const filtered = all.filter(function(p) {
        if (query && !p.name.toLowerCase().includes(query)) return false;
        if (playerFilter === "online") return p.online;
        if (playerFilter === "op") return p.op;
        if (playerFilter === "banned") return !!p.ban;
        if (playerFilter === "whitelist") return p.whitelisted;
        return true;
    });

    list.textContent = "";

    if (!filtered.length) {
        list.append(el("div", "list-empty", t("pl.none")));
        return;
    }

    filtered.forEach(function(player) {

        const row = el("div", "pl-row" + (player.online ? " online" : ""));

        const avatar = el("span", "avatar pl-avatar", player.name.charAt(0).toUpperCase());
        const img = document.createElement("img");
        img.alt = "";
        img.src = "https://mc-heads.net/avatar/" + encodeURIComponent(player.name) + "/64";
        img.onerror = function() { img.remove(); };
        avatar.append(img, el("span", "pl-dot"));

        const info = el("div", "pl-info");
        const top = el("div", "pl-name");
        top.append(el("span", "", player.name), playerBadges(player));
        info.append(top, el("div", "pl-sub", playerStatus(player)));

        const actions = el("div", "pl-actions");

        if (player.online && playersData.running) {
            actions.append(iconButton("message", t("pl.message"), function() {
                openPlayer(player.name, "message");
            }));
        }

        const manage = el("button", "btn btn-ghost btn-small", t("pl.manage"));
        manage.onclick = function(event) {
            event.stopPropagation();
            openPlayer(player.name);
        };
        actions.append(manage);

        row.append(avatar, info, actions);
        row.onclick = function() { openPlayer(player.name); };

        list.append(row);
    });
}


async function playerAction(name, action, extra) {

    try {
        const data = await api("/players/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(Object.assign({ name: name, action: action }, extra || {}))
        });

        showToast(t("pl.done." + action, { name: name }) || serverText(data.message), "green");
        playerPanelDirty = true;
        setTimeout(loadPlayers, 600);
        return true;

    } catch (error) {
        if (error.message !== "auth") showToast(error.message, "red");
        return false;
    }
}


// Botones peligrosos: el primer clic pide confirmacion en el mismo boton
function armedButton(label, confirmLabel, className, onConfirm) {

    const btn = el("button", "btn btn-small " + className, label);
    let timer = null;

    btn.onclick = function() {

        if (btn.classList.contains("armed")) {
            clearTimeout(timer);
            btn.classList.remove("armed");
            btn.textContent = label;
            onConfirm();
            return;
        }

        btn.classList.add("armed");
        btn.textContent = confirmLabel;
        timer = setTimeout(function() {
            btn.classList.remove("armed");
            btn.textContent = label;
        }, 4000);
    };

    return btn;
}


function plSection(title) {
    const section = el("div", "pl-section");
    section.append(el("div", "pl-section-title", title));
    return section;
}


function renderPlayerSide(player) {

    if (!$("playerName")) return;

    $("playerName").textContent = player.name;
    $("playerStatus").textContent = playerStatus(player);
    $("playerStatus").className = "pl-sub" + (player.online ? " is-green" : "");

    const badges = $("playerBadges");
    badges.textContent = "";
    badges.append(playerBadges(player));

    const facts = $("playerFacts");
    facts.textContent = "";

    [
        [t("pl.firstSeen"), player.first_seen ? new Date(player.first_seen * 1000).toLocaleDateString(locale(), { day: "numeric", month: "short", year: "numeric" }) : "-"],
        [t("pl.lastSeenLabel"), player.online ? t("pl.onlineNow") : timeAgo(player.last_seen)],
        [t("pl.joins"), String(player.joins)],
        ["UUID", player.uuid || "-"]
    ].forEach(function([label, value]) {
        const row = el("div", "pl-fact");
        row.append(el("span", "", label), el("b", "", value));
        facts.append(row);
    });
}


function renderPlayerPanel(player) {

    const panel = $("playerPanel");
    if (!panel) return;

    const live = playersData.running;
    const online = player.online && live;

    renderPlayerSide(player);

    panel.textContent = "";

    if (!live) {
        panel.append(el("div", "set-note", t("pl.offNote")));
    }

    // Mensaje privado
    const msg = plSection(t("pl.message"));
    const msgRow = el("div", "pl-inline");
    const msgInput = el("input", "input");
    msgInput.id = "playerMessage";
    msgInput.maxLength = 240;
    msgInput.placeholder = online ? t("pl.messagePh", { name: player.name }) : t("pl.needsOnline");
    msgInput.disabled = !online;
    const msgBtn = el("button", "btn btn-send btn-small", t("console.send"));
    msgBtn.disabled = !online;
    const sendMsg = async function() {
        const text = msgInput.value.trim();
        if (!text) return;
        if (await playerAction(player.name, "message", { text: text })) msgInput.value = "";
    };
    msgBtn.onclick = sendMsg;
    msgInput.onkeydown = function(event) { if (event.key === "Enter") sendMsg(); };
    msgRow.append(msgInput, msgBtn);
    msg.append(msgRow);
    panel.append(msg);

    // Modo de juego y teletransporte
    const play = plSection(t("pl.gamemode"));
    const modes = el("div", "pl-modes");

    ["survival", "creative", "adventure", "spectator"].forEach(function(mode) {
        const btn = el("button", "btn btn-ghost btn-small", t("opt." + mode));
        btn.disabled = !online;
        btn.onclick = function() { playerAction(player.name, "gamemode", { mode: mode }); };
        modes.append(btn);
    });

    play.append(modes);

    const others = playersData.online.filter(function(n) {
        return n.toLowerCase() !== player.name.toLowerCase();
    });

    const tpRow = el("div", "pl-inline");
    const tpSelect = el("select", "input");
    tpSelect.disabled = !online || !others.length;

    if (!others.length) {
        tpSelect.append(el("option", "", t("pl.noOthers")));
    }

    others.forEach(function(n) {
        const option = el("option", "", n);
        option.value = n;
        tpSelect.append(option);
    });

    const tpBtn = el("button", "btn btn-ghost btn-small", t("pl.teleport"));
    tpBtn.disabled = tpSelect.disabled;
    tpBtn.onclick = function() { playerAction(player.name, "tp", { target: tpSelect.value }); };
    tpRow.append(el("span", "pl-inline-label", t("pl.teleportTo")), tpSelect, tpBtn);
    play.append(tpRow);
    panel.append(play);

    // Moderacion
    const mod = plSection(t("pl.moderation"));
    const reason = el("input", "input");
    reason.maxLength = 120;
    reason.placeholder = t("pl.reasonPh");
    reason.disabled = !live;
    mod.append(reason);

    const modRow = el("div", "pl-modes");

    const kick = armedButton(t("pl.kick"), t("pl.confirm"), "btn-ghost", function() {
        playerAction(player.name, "kick", { reason: reason.value });
    });
    kick.disabled = !online;

    const timeoutSelect = el("select", "input pl-timeout");
    TIMEOUT_OPTIONS.forEach(function(minutes) {
        const option = el("option", "", formatMinutes(minutes));
        option.value = minutes;
        timeoutSelect.append(option);
    });
    timeoutSelect.value = "60";
    timeoutSelect.disabled = !live;

    const timeoutBtn = armedButton(t("pl.timeout"), t("pl.confirm"), "btn-warn", function() {
        playerAction(player.name, "timeout", { minutes: Number(timeoutSelect.value), reason: reason.value });
    });
    timeoutBtn.disabled = !live;

    modRow.append(kick, timeoutSelect, timeoutBtn);

    if (player.ban) {
        const pardon = el("button", "btn btn-start btn-small", t("pl.pardon"));
        pardon.disabled = !live;
        pardon.onclick = function() { playerAction(player.name, "pardon"); };
        modRow.append(pardon);
    } else {
        const ban = armedButton(t("pl.ban"), t("pl.confirm"), "btn-danger", function() {
            playerAction(player.name, "ban", { reason: reason.value });
        });
        ban.disabled = !live;
        modRow.append(ban);
    }

    mod.append(modRow);

    if (player.ban && player.ban.reason) {
        mod.append(el("div", "pl-hint", t("pl.banReason", { r: player.ban.reason })));
    }

    const kill = armedButton(t("pl.kill"), t("pl.confirm"), "btn-ghost", function() {
        playerAction(player.name, "kill");
    });
    kill.disabled = !online;
    kill.title = t("pl.killHint");
    modRow.append(kill);

    panel.append(mod);

    // Rol y acceso
    const role = plSection(t("pl.role"));

    [
        ["op", player.op, "op", "deop", t("pl.operator"), t("pl.operatorHint")],
        ["whitelist", player.whitelisted, "whitelist_add", "whitelist_remove", t("pl.whitelist"), t("pl.whitelistHint")]
    ].forEach(function([id, on, enable, disable, label, hint]) {

        const row = el("div", "set-row pl-role");
        const text = el("div", "set-text");
        text.append(el("div", "set-label", label), el("div", "set-desc", hint));

        const sw = el("button", "switch" + (on ? " on" : ""));
        sw.type = "button";
        sw.setAttribute("role", "switch");
        sw.setAttribute("aria-checked", on ? "true" : "false");
        sw.setAttribute("aria-label", label);
        sw.append(el("span", "switch-knob"));
        sw.disabled = !live;
        sw.onclick = function() { playerAction(player.name, on ? disable : enable); };

        row.append(text, sw);
        role.append(row);
    });

    panel.append(role);
}


async function openPlayer(name, focus) {

    const player = findPlayer(name);
    if (!player) return;

    openPlayerName = player.name;

    const layout = el("div", "pl-sheet");

    const side = el("div", "pl-side");
    const stage = el("div", "pl-skin");
    const canvas = document.createElement("canvas");
    stage.append(canvas);

    const name1 = el("div", "pl-sheet-name");
    name1.id = "playerName";
    const status = el("div", "pl-sub");
    status.id = "playerStatus";
    const badges = el("div");
    badges.id = "playerBadges";
    const facts = el("div", "pl-facts");
    facts.id = "playerFacts";

    side.append(stage, name1, status, badges, facts);

    const panel = el("div", "pl-panel");
    panel.id = "playerPanel";

    layout.append(side, panel);

    const done = openModal({
        title: t("pl.sheetTitle"),
        body: [layout],
        okText: t("modal.close"),
        hideCancel: true,
        cls: "player-modal"
    });

    renderPlayerPanel(player);

    if (focus === "message") {
        setTimeout(function() {
            const input = $("playerMessage");
            if (input && !input.disabled) input.focus();
        }, 60);
    }

    startSkin(stage, canvas, player.name);

    await done;

    openPlayerName = null;

    if (skinViewer) {
        skinViewer.dispose();
        skinViewer = null;
    }
}


async function startSkin(stage, canvas, name) {

    const skinUrl = "https://mc-heads.net/skin/" + encodeURIComponent(name);

    const fallback = function() {
        stage.textContent = "";
        const img = document.createElement("img");
        img.className = "pl-skin-2d";
        img.alt = name;
        img.src = "https://mc-heads.net/body/" + encodeURIComponent(name) + "/220";
        stage.append(img);
    };

    try {
        await loadSkinLib();

        // El modal pudo cerrarse mientras cargaba la libreria
        if (!canvas.isConnected) return;

        skinViewer = new skinview3d.SkinViewer({
            canvas: canvas,
            width: 220,
            height: 300
        });

        skinViewer.background = null;
        skinViewer.zoom = 0.85;
        skinViewer.fov = 40;
        skinViewer.autoRotate = true;
        skinViewer.autoRotateSpeed = 0.6;
        skinViewer.controls.enableZoom = false;
        skinViewer.animation = new skinview3d.WalkingAnimation();
        skinViewer.animation.speed = 0.55;

        await skinViewer.loadSkin(skinUrl);

    } catch (error) {
        if (skinViewer) {
            skinViewer.dispose();
            skinViewer = null;
        }
        fallback();
    }
}


setInterval(function() {
    if (activeTab === "players" && authorized) loadPlayers();
}, 5000);


// ============================================================
// Chat del servidor
// ============================================================

let chatKey = "";
let chatTotal = null;
let chatUnread = 0;


function showPane(name) {

    consolePane = name;
    $("panes").dataset.pane = name;

    document.querySelectorAll(".tab-btn[data-pane]").forEach(function(btn) {
        btn.classList.toggle("active", btn.dataset.pane === name);
    });

    if (name === "chat") {
        chatUnread = 0;
        renderChatBadge();
    }

    const box = $(name);
    box.scrollTop = box.scrollHeight;
}


function renderChatBadge() {
    const badge = $("chatBadge");
    badge.hidden = chatUnread <= 0;
    badge.textContent = chatUnread > 99 ? "99+" : String(chatUnread);
}


function chatTime(ts) {
    return new Date(ts * 1000).toLocaleTimeString(locale(), {
        hour: "2-digit",
        minute: "2-digit"
    });
}


function chatDay(ts) {

    const d = new Date(ts * 1000);
    const today = new Date();
    const yesterday = new Date(Date.now() - 86400000);

    if (d.toDateString() === today.toDateString()) return t("act.today");
    if (d.toDateString() === yesterday.toDateString()) return t("chat.yesterday");

    return d.toLocaleDateString(locale(), {
        weekday: "long",
        day: "numeric",
        month: "long"
    });
}


function chatAvatar(name) {

    const avatar = el("span", "avatar chat-avatar", name.charAt(0).toUpperCase());
    const img = document.createElement("img");
    img.alt = "";
    img.src = "https://mc-heads.net/avatar/" + encodeURIComponent(name) + "/32";
    img.onerror = function() { img.remove(); };
    avatar.append(img);

    return avatar;
}


function chatRow(message) {

    const time = el("span", "chat-time", chatTime(message.ts));
    time.title = new Date(message.ts * 1000).toLocaleString(locale());

    if (message.type === "chat" || message.type === "say") {

        const row = el("div", "chat-msg" + (message.type === "say" ? " chat-say" : ""));
        const body = el("div", "chat-body");

        const name = el("span", "chat-name",
            message.type === "say" ? t("chat.server") : message.name);

        body.append(name, el("span", "chat-text", message.text));

        const avatar = message.type === "say"
            ? el("span", "avatar chat-avatar server", "S")
            : chatAvatar(message.name);

        row.append(time, avatar, body);
        return row;
    }

    const row = el("div", "chat-msg chat-sys chat-" + message.type);
    let text;

    if (message.type === "join") text = t("chat.joined", { name: message.name });
    else if (message.type === "leave") text = t("chat.left", { name: message.name });
    else text = t("chat.advancement", { name: message.name, a: message.text });

    row.append(time, el("span", "chat-dot"), el("span", "chat-text", text));
    return row;
}


async function loadChat() {

    try {

        const response = await fetch("/chat?t=" + Date.now());
        const data = await response.json();
        const messages = data.messages || [];
        const last = messages.length ? messages[messages.length - 1] : null;
        const key = lang + "|" + data.total + "|" + (last ? last.ts : 0);

        // Mensajes nuevos mientras la pestana del chat no esta a la vista
        if (chatTotal !== null && data.total > chatTotal &&
            ((isNarrow() && consolePane !== "chat") || $("tab-panel").hidden)) {
            chatUnread += messages.slice(-(data.total - chatTotal)).filter(function(m) {
                return m.type === "chat" || m.type === "say";
            }).length;
            renderChatBadge();
        }

        chatTotal = data.total;

        if (key === chatKey) return;
        chatKey = key;

        const box = $("chat");
        const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;

        box.textContent = "";

        $("chatSince").textContent = messages.length
            ? t("chat.since", {
                d: new Date(messages[0].ts * 1000).toLocaleDateString(locale(), {
                    day: "numeric", month: "long", year: "numeric"
                })
            })
            : "";

        if (!messages.length) {
            box.append(el("div", "chat-empty", t("chat.empty")));
            return;
        }

        const frag = document.createDocumentFragment();
        let lastDay = "";

        messages.forEach(function(message) {

            const day = new Date(message.ts * 1000).toDateString();

            if (day !== lastDay) {
                frag.append(el("div", "chat-day", chatDay(message.ts)));
                lastDay = day;
            }

            frag.append(chatRow(message));
        });

        box.append(frag);

        if (atBottom || box.dataset.scrolled !== "1") {
            box.scrollTop = box.scrollHeight;
        }

    } catch (error) {
    }
}


$("chat").addEventListener("scroll", function() {
    // Si el usuario sube a leer, no se le mueve al llegar mensajes
    this.dataset.scrolled =
        this.scrollHeight - this.scrollTop - this.clientHeight > 60 ? "1" : "0";
});


async function sendChat() {

    const input = $("chatInput");
    const text = input.value.trim();

    if (!text) return;

    try {

        const response = await fetch("/chat/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: text })
        });

        const data = await response.json();

        if (data.ok) {
            input.value = "";
            $("chat").dataset.scrolled = "0";
            setTimeout(loadChat, 700);
        } else {
            showToast(serverText(data.message), "red");
        }

    } catch (error) {
        showToast(t("console.sendError"), "red");
    }
}


setInterval(loadChat, 4000);
loadChat();


applyI18n();
renderThemeButton();

if (location.hash === "#archivos") {
    showTab("files");
} else if (location.hash === "#ajustes") {
    showTab("settings");
} else if (location.hash === "#jugadores") {
    showTab("players");
}

setInterval(updateStats, 2000);
setInterval(loadBackups, 4000);
updateStats();
checkConsoleSession();


update();
updateConsole();

setInterval(update, 2000);
setInterval(updateConsole, 1500);
setInterval(renderCountdown, 250);

</script>

</body>
</html>
"""



class Handler(BaseHTTPRequestHandler):

    def send_body(self, output, content_type, code=200, headers=None):

        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(output)))

        for key, value in (headers or {}).items():
            self.send_header(key, value)

        self.end_headers()
        self.wfile.write(output)


    def send_json(self, data, code=200, headers=None):

        output = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_body(
            output,
            "application/json; charset=utf-8",
            code,
            headers
        )


    def send_file(self, full, download_name):

        size = os.path.getsize(full)
        quoted = urllib.parse.quote(download_name)

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header(
            "Content-Disposition",
            "attachment; filename*=UTF-8''" + quoted
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        with open(full, "rb") as f:
            shutil.copyfileobj(f, self.wfile, 1024 * 1024)


    def route(self):
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        def param(name, default=""):
            return query.get(name, [default])[0]

        return parsed.path, param


    def session_token(self):
        cookie = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None


    def authorized(self):
        return valid_session(self.session_token())


    def read_body(self, limit=MAX_EDIT_BYTES + 1024):
        length = int(self.headers.get("Content-Length", "0") or 0)

        if length > limit:
            raise FileError("Contenido demasiado grande", 413)

        return self.rfile.read(length)


    def do_GET(self):

        path, param = self.route()

        if path == "/api":
            self.send_json(server_data())
            return

        if path == "/stats":
            self.send_json(system_stats())
            return

        if path == "/chat":
            self.send_json(chat_history())
            return

        if path == "/console":
            self.send_body(
                console().encode("utf-8"),
                "text/plain; charset=utf-8"
            )
            return

        if (path.startswith("/files/") or path.startswith("/backups")
                or path in ("/settings", "/players")):
            self.protected_get(path, param)
            return

        self.send_body(
            PAGE,
            "text/html; charset=utf-8"
        )


    def protected_get(self, path, param):

        if path == "/files/session":
            self.send_json({"authorized": self.authorized()})
            return

        if not self.authorized():
            self.send_json({"ok": False, "message": "Sesión no válida"}, 401)
            return

        try:
            if path == "/files/list":
                self.send_json(list_files(param("path")))

            elif path == "/files/read":
                self.send_json(read_text_file(param("path")))

            elif path == "/files/download":
                full = safe_path(param("path"))

                if not os.path.isfile(full):
                    raise FileError("Solo se pueden descargar archivos")

                self.send_file(full, os.path.basename(full))

            elif path == "/files/zip":
                paths = json.loads(param("paths", "[]"))

                if not isinstance(paths, list):
                    raise FileError("Petición no válida")

                tmp, name = build_zip([str(p) for p in paths])

                try:
                    self.send_file(tmp, name)
                finally:
                    os.remove(tmp)

            elif path == "/settings":
                self.send_json(get_settings())

            elif path == "/players":
                self.send_json(list_players())

            elif path == "/backups":
                self.send_json(list_backups())

            elif path == "/backups/download":
                full = backup_path(param("name"))
                self.send_file(full, os.path.basename(full))

            else:
                self.send_json({"ok": False, "message": "No encontrado"}, 404)

        except FileError as error:
            self.send_json({"ok": False, "message": str(error)}, error.code)

        except (BrokenPipeError, ConnectionResetError):
            pass

        except Exception as error:
            self.send_json({"ok": False, "message": "Error: " + str(error)}, 500)


    def do_POST(self):

        path, param = self.route()

        if path.startswith("/action/"):
            self.send_json(docker_action(path.split("/")[-1]))
            return

        if path == "/command":
            if not self.authorized():
                self.send_json({"ok": False, "message": "Sesión no válida"}, 401)
                return

            try:
                body = self.read_body().decode("utf-8", errors="replace")
                params = urllib.parse.parse_qs(body)
                command_text = params.get("command", [""])[0]
                self.send_json(send_command(command_text))
            except Exception as error:
                self.send_json({
                    "ok": False,
                    "message": "Error procesando comando",
                    "output": str(error)
                })
            return

        if path == "/chat/send":
            # Sin contrasena a proposito; solo se limita la frecuencia
            if chat_rate_limited(self.client_address[0]):
                self.send_json({
                    "ok": False,
                    "message": "Estás enviando mensajes muy rápido. Espera un momento."
                }, 429)
                return

            try:
                data = json.loads(self.read_body(4096) or b"{}")
                self.send_json(send_chat(str(data.get("text", ""))))
            except Exception as error:
                self.send_json({"ok": False, "message": "Error: " + str(error)})
            return

        if path == "/files/login":
            self.login()
            return

        if path == "/files/logout":
            end_session(self.session_token())
            self.send_json(
                {"ok": True},
                headers={
                    "Set-Cookie": SESSION_COOKIE
                    + "=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
                }
            )
            return

        if (path.startswith("/files/") or path.startswith("/backups")
                or path in ("/settings", "/players/action", "/system/uninstall")):
            self.protected_post(path, param)
            return

        self.send_json({"ok": False, "message": "No encontrado"}, 404)


    def login(self):

        ip = self.client_address[0]

        if login_blocked(ip):
            self.send_json({
                "ok": False,
                "message": "Demasiados intentos. Espera 5 minutos."
            }, 429)
            return

        try:
            data = json.loads(self.read_body(4096) or b"{}")
            password = str(data.get("password", ""))
        except Exception:
            password = ""

        ok = bool(password) and check_password(password)
        register_login(ip, ok)

        if not ok:
            time.sleep(1)
            self.send_json({"ok": False, "message": "Contraseña incorrecta"}, 401)
            return

        token = create_session()

        self.send_json(
            {"ok": True},
            headers={
                "Set-Cookie": SESSION_COOKIE + "=" + token
                + "; Path=/; Max-Age=" + str(SESSION_SECONDS)
                + "; HttpOnly; SameSite=Strict"
            }
        )


    def protected_post(self, path, param):

        if not self.authorized():
            self.send_json({"ok": False, "message": "Sesión no válida"}, 401)
            return

        try:
            if path == "/files/upload":
                length = int(self.headers.get("Content-Length", "0") or 0)
                self.send_json(
                    receive_upload(self, param("path"), param("name"), length)
                )

            elif path == "/files/write":
                content = self.read_body().decode("utf-8")
                self.send_json(write_text_file(param("path"), content))

            elif path == "/files/mkdir":
                self.send_json(make_folder(param("path"), param("name")))

            elif path == "/files/rename":
                self.send_json(rename_item(param("path"), param("name")))

            elif path == "/files/delete":
                self.send_json(delete_item(param("path")))

            elif path in ("/files/move", "/files/delete-many"):
                data = json.loads(self.read_body() or b"{}")
                paths = data.get("paths")

                if not isinstance(paths, list):
                    raise FileError("Petición no válida")

                paths = [str(p) for p in paths]

                if path == "/files/move":
                    self.send_json(move_items(paths, str(data.get("dest", ""))))
                else:
                    self.send_json(delete_items(paths))

            elif path == "/settings":
                data = json.loads(self.read_body() or b"{}")
                self.send_json(save_settings(data.get("values")))

            elif path == "/system/uninstall":
                data = json.loads(self.read_body(4096) or b"{}")
                self.send_json(start_uninstall(data if isinstance(data, dict) else {}))

            elif path == "/players/action":
                data = json.loads(self.read_body() or b"{}")

                if not isinstance(data, dict):
                    raise FileError("Petición no válida")

                self.send_json(player_action(data))

            elif path == "/backups/create":
                self.send_json(start_backup())

            elif path == "/backups/delete":
                self.send_json(delete_backup(param("name")))

            else:
                self.send_json({"ok": False, "message": "No encontrado"}, 404)

        except FileError as error:
            self.send_json({"ok": False, "message": str(error)}, error.code)

        except Exception as error:
            self.send_json({"ok": False, "message": "Error: " + str(error)}, 500)


    def log_message(self, format, *args):
        pass


# Valores de la instalacion insertados en la pagina una sola vez
PAGE = (
    HTML
    .replace("__SERVER_NAME__", html.escape(SERVER_NAME))
    .replace("__PUBLIC_ADDRESS__", html.escape(PUBLIC_ADDRESS))
    .replace("__DEFAULT_LANG__", "es" if DEFAULT_LANG == "es" else "en")
).encode("utf-8")

threading.Thread(target=stats_loop, daemon=True).start()
threading.Thread(target=slow_stats_loop, daemon=True).start()
threading.Thread(target=timeout_loop, daemon=True).start()

server = ThreadingHTTPServer(
    (BIND, PORT),
    Handler
)

print(
    "Minecraft web panel escuchando en puerto "
    + str(PORT)
)

server.serve_forever()
