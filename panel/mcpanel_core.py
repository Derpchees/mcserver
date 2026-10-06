#!/usr/bin/env python3
#
# MCServer by Derpchees - nucleo compartido
# https://github.com/Derpchees/mcserver
#
# Configuracion, base de datos (usuarios, servidores, ajustes, eventos),
# rutas de cada servidor y manejo de sus contenedores. Lo usan el panel
# web (mcpanel.py) y el agente (mcpanel-agent.py).
#
# Uso como comando (desde scripts de bash):
#   mcpanel_core.py event <slug> <tipo> <nivel> [mensaje]
#   mcpanel_core.py server-env <slug>
#

import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time


# ============================================================
# Configuracion del sistema
# ============================================================

# Windows: sin Docker ni rutas de Linux. Todo vive en una carpeta
# (C:/MCServer): el codigo en app/ y config.env junto a ella
WINDOWS = os.name == "nt"
HOME_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows no tiene duenos de archivo al estilo Linux: chown no hace nada
if not hasattr(os, "chown"):
    os.chown = lambda *args, **kwargs: None

CONFIG_ENV = os.environ.get("MCPANEL_CONFIG",
                            os.path.join(HOME_DIR, "config.env") if WINDOWS else "/etc/mcpanel/config.env")

# Los scripts que se lanzan con systemd-run no heredan el entorno: asi
# usan la misma configuracion (importa si hay mas de una instalacion)
CONFIG_SETENV = "--setenv=MCPANEL_CONFIG=" + CONFIG_ENV


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


def default_path(linux, windows):
    # En Windows las rutas por defecto son carpetas dentro de la instalacion
    return os.path.join(HOME_DIR, windows).replace("\\", "/") if WINDOWS else linux


SYSTEM_NAME = cfg("SYSTEM_NAME", "MCServer")
DEFAULT_LANG = cfg("LANG_DEFAULT", "en")
INSTALL_DIR = cfg("INSTALL_DIR", default_path("/opt/mcpanel", "app"))
DATA_ROOT = cfg("DATA_ROOT", default_path("/srv/minecraft/servers", "servers"))
BACKUP_ROOT = cfg("BACKUP_ROOT", default_path("/srv/minecraft/backups", "backups"))
BACKUP_MOUNT = cfg("BACKUP_MOUNT", "")
LOG_ROOT = cfg("LOG_DIR", default_path("/var/log/mcpanel", "logs"))
STATE_ROOT = cfg("STATE_DIR", default_path("/var/lib/mcpanel", "state"))
RUN_ROOT = cfg("RUN_DIR", default_path("/run/mcpanel", "run"))

# Como corren los servidores: "docker" (Linux) o "native" (procesos normales,
# siempre en Windows: el panel descarga Java y el servidor; ver runtime/)
NATIVE = cfg("RUNTIME", "native" if WINDOWS else "docker") == "native"
LISTEN_IP = cfg("LISTEN_IP", "0.0.0.0")
PUBLIC_HOST = cfg("PUBLIC_HOST", "")
PANEL_PORT = int(cfg("PANEL_PORT", "8090"))
PANEL_BIND = cfg("PANEL_BIND", "0.0.0.0")
GAME_PORT_START = int(cfg("GAME_PORT_START", "25565"))
# Bedrock usa otro rango de puertos (19132 es el que los clientes usan por defecto):
# TCP para conectarse y, desde ahi, UDP para el juego (bedrock/signaling.py)
BEDROCK_PORT_START = int(cfg("BEDROCK_PORT_START", "19132"))
INTERNAL_PORT_START = int(cfg("INTERNAL_PORT_START", "35565"))
MC_UID = int(cfg("MC_UID", "1000"))
MC_GID = int(cfg("MC_GID", "1000"))
IMAGE = cfg("IMAGE", "itzg/minecraft-server")
BEDROCK_IMAGE = cfg("BEDROCK_IMAGE", "itzg/minecraft-bedrock-server")
DOCKER_NETWORK = cfg("DOCKER_NETWORK", "mcpanel-net")

# HTTPS: certificado y clave (los pone el panel al activar el acceso seguro)
TLS_CERT = cfg("TLS_CERT", "")
TLS_KEY = cfg("TLS_KEY", "")
PANEL_DOMAIN = cfg("PANEL_DOMAIN", "")


def tls_enabled():
    return bool(TLS_CERT and TLS_KEY and os.path.isfile(TLS_CERT) and os.path.isfile(TLS_KEY))

DB_PATH = os.path.join(STATE_ROOT, "mcpanel.db")

# Respaldos automaticos que se conservan por servidor (como maximo)
BACKUP_KEEP_MAX = 3


# ============================================================
# Ubicacion de servidores y respaldos
# ============================================================
#
# El panel puede cambiarlas sin reinstalar: se guardan en config.env
# (tambien lo lee uninstall.sh) y se releen cuando el archivo cambia.

_live = {"mtime": None, "values": CFG}
_live_lock = threading.Lock()


def live_cfg(key, default=""):
    try:
        mtime = os.path.getmtime(CONFIG_ENV)
    except OSError:
        mtime = None

    with _live_lock:
        if mtime != _live["mtime"]:
            _live["values"] = load_env(CONFIG_ENV)
            _live["mtime"] = mtime

        return _live["values"].get(key, default) or default


def data_root():
    return live_cfg("DATA_ROOT", DATA_ROOT)


def backup_root():
    return live_cfg("BACKUP_ROOT", BACKUP_ROOT)


CONFIG_VALUE = re.compile(r"^[A-Za-z0-9 ._/:+-]*$")


def set_config(values):
    # Cambia o agrega claves de config.env sin tocar las demas
    for key, value in values.items():
        if not CONFIG_VALUE.match(str(value)):
            raise ValueError("Valor no permitido para " + key)

    try:
        with open(CONFIG_ENV, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []

    pending = dict(values)

    for i, line in enumerate(lines):
        key = line.partition("=")[0].strip()

        if key in pending:
            lines[i] = '%s="%s"' % (key, pending.pop(key))

    lines += ['%s="%s"' % (key, value) for key, value in pending.items()]

    tmp = CONFIG_ENV + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        os.chmod(tmp, os.stat(CONFIG_ENV).st_mode & 0o7777)
    except OSError:
        pass

    os.replace(tmp, CONFIG_ENV)


# Discos que deben estar montados. Un disco aparte se monta con "nofail":
# si falta, el equipo arranca igual y su punto de montaje queda como una
# carpeta vacia del disco del sistema. Ahi no se debe escribir nada.

def read_fstab():
    mounts = []

    if WINDOWS:
        return mounts

    try:
        with open("/etc/fstab", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split()

                if len(parts) >= 3 and not parts[0].startswith("#") and parts[2] != "swap":
                    mounts.append(parts[1].replace("\\040", " "))
    except OSError:
        pass

    return mounts


def is_mount(path):
    return os.path.ismount(path)


def expected_mount(path):
    # Punto de montaje del que depende una ruta (None si vive en el disco del sistema)
    path = os.path.normpath(path)
    candidates = read_fstab() + [live_cfg("BACKUP_MOUNT", BACKUP_MOUNT)]
    best = None

    for mount in candidates:
        if not mount or mount in ("/", "none"):
            continue

        mount = os.path.normpath(mount)

        if (path == mount or path.startswith(mount.rstrip(os.sep) + os.sep)) \
                and (best is None or len(mount) > len(best)):
            best = mount

    return best


def path_available(path):
    mount = expected_mount(path)
    return mount is None or is_mount(mount)

SERVER_TYPES = ("FORGE", "NEOFORGE", "FABRIC", "PAPER", "VANILLA", "AUTO_CURSEFORGE", "MODRINTH", "BEDROCK")


def is_bedrock(type_or_srv):
    # Bedrock (moviles, consolas, Windows) usa otra imagen, UDP y add-ons en lugar de mods
    type_ = getattr(type_or_srv, "type", type_or_srv)
    return type_ == "BEDROCK"

# Variable del contenedor que fija la version del cargador de cada tipo
LOADER_ENV = {
    "FORGE": "FORGE_VERSION",
    "NEOFORGE": "NEOFORGE_VERSION",
    "FABRIC": "FABRIC_LOADER_VERSION",
    "PAPER": "PAPER_BUILD"
}


def system_ram_gb():
    if WINDOWS:
        from native import winsys
        return max(1, round(winsys.memory()[0] / 1024 ** 3))

    with open("/proc/meminfo", "r") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // (1024 * 1024)
    return 4


# ============================================================
# Base de datos
# ============================================================

_db_lock = threading.Lock()
_db_ready = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    default_server INTEGER,
    notify_mute TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    version TEXT NOT NULL,
    max_gb INTEGER NOT NULL,
    cpu INTEGER NOT NULL DEFAULT 0,
    game_port INTEGER NOT NULL UNIQUE,
    internal_port INTEGER NOT NULL UNIQUE,
    autostop INTEGER NOT NULL DEFAULT 1,
    idle_minutes INTEGER NOT NULL DEFAULT 10,
    backups INTEGER NOT NULL DEFAULT 1,
    backup_time TEXT NOT NULL DEFAULT '04:00',
    backup_keep INTEGER NOT NULL DEFAULT 3,
    backup_every_hours INTEGER NOT NULL DEFAULT 24,
    backup_every_hours_off INTEGER NOT NULL DEFAULT 24,
    icon TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'ready',
    state_detail TEXT NOT NULL DEFAULT '',
    data_dir TEXT NOT NULL DEFAULT '',
    backup_dir TEXT NOT NULL DEFAULT '',
    container TEXT NOT NULL DEFAULT '',
    extra_env TEXT NOT NULL DEFAULT '',
    java TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,
    server_id INTEGER,
    kind TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS events_server ON events(server_id, id);

-- Sesiones del panel: id = SHA-256 del token de la cookie (nunca el token)
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created INTEGER NOT NULL,
    expires INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    remember INTEGER NOT NULL DEFAULT 0,
    ip TEXT NOT NULL DEFAULT '',
    agent TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);

-- Dispositivos con notificaciones push (push/store.py). token = SHA-256 del
-- token que guarda el service worker; last_event = ultimo evento entregado
CREATE TABLE IF NOT EXISTS push_subs (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL UNIQUE,
    token TEXT NOT NULL,
    last_event INTEGER NOT NULL DEFAULT 0,
    created INTEGER NOT NULL
);
"""


def db():
    global _db_ready

    os.makedirs(STATE_ROOT, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    if not _db_ready:
        with _db_lock:
            if not _db_ready:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript(SCHEMA)

                # Columnas agregadas en versiones posteriores
                columns = {row[1] for row in conn.execute("PRAGMA table_info(servers)")}

                if "extra_env" not in columns:
                    conn.execute("ALTER TABLE servers ADD COLUMN extra_env TEXT NOT NULL DEFAULT ''")

                if "java" not in columns:
                    conn.execute("ALTER TABLE servers ADD COLUMN java TEXT NOT NULL DEFAULT ''")

                # Cada cuantas horas se respalda encendido y apagado (0 = no se respalda apagado)
                if "backup_every_hours" not in columns:
                    conn.execute("ALTER TABLE servers ADD COLUMN backup_every_hours INTEGER NOT NULL DEFAULT 24")

                if "backup_every_hours_off" not in columns:
                    conn.execute("ALTER TABLE servers ADD COLUMN backup_every_hours_off INTEGER NOT NULL DEFAULT 24")

                # Bloque elegido para el icono ('' = el que toca por el nombre)
                if "icon" not in columns:
                    conn.execute("ALTER TABLE servers ADD COLUMN icon TEXT NOT NULL DEFAULT ''")

                user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}

                if "default_server" not in user_columns:
                    conn.execute("ALTER TABLE users ADD COLUMN default_server INTEGER")

                # Temas de avisos silenciados (push/kinds.py); '' = todos activos
                if "notify_mute" not in user_columns:
                    conn.execute("ALTER TABLE users ADD COLUMN notify_mute TEXT NOT NULL DEFAULT ''")

                _db_ready = True

    return conn


def query(sql, args=(), one=False):
    conn = db()

    try:
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()

    if one:
        return rows[0] if rows else None

    return rows


def execute(sql, args=()):
    conn = db()

    try:
        cur = conn.execute(sql, args)
        return cur.lastrowid
    finally:
        conn.close()


# ============================================================
# Ajustes del sistema (editables por el admin)
# ============================================================

def default_settings():
    ram = system_ram_gb()

    return {
        "signup": "yes",
        "max_ram_gb": str(max(1, min(8, ram - 2))),
        "max_cpu": "0",
        "public_host": PUBLIC_HOST,
        "max_servers_per_user": "1",
        "default_server": "",
        "public_access": "yes",
        "cf_api_key": "",
        "owner_id": "",
        # Respaldos desactivados por el administrador mientras falta su disco
        "backups_paused": "",
        # Hay una tarea de almacenamiento moviendo los servidores
        "storage_busy": ""
    }


def get_setting(key):
    row = query("SELECT value FROM settings WHERE key = ?", (key,), one=True)

    if row is None:
        return default_settings().get(key, "")

    return row["value"]


def all_settings():
    values = default_settings()

    for row in query("SELECT key, value FROM settings"):
        values[row["key"]] = row["value"]

    return values


def set_setting(key, value):
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value))
    )


# ============================================================
# Usuarios
# ============================================================

USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,24}$")


def hash_password(password):
    salt = secrets.token_bytes(16)
    iterations = 310000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()
    return "pbkdf2_sha256$%d$%s$%s" % (iterations, salt.hex(), digest)


def verify_password(password, stored):
    try:
        algorithm, iterations, salt, expected = stored.split("$")
    except (ValueError, AttributeError):
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
    ).hex()

    return hmac.compare_digest(digest, expected)


def owner_id():
    # Dueno del sistema: el primer usuario (el que hizo la configuracion inicial)
    value = get_setting("owner_id")

    if value.isdigit() and get_user(int(value)):
        return int(value)

    row = query("SELECT MIN(id) AS n FROM users WHERE role = 'admin'", one=True)
    return row["n"] if row else None


def user_count():
    return query("SELECT COUNT(*) AS n FROM users", one=True)["n"]


def get_user(user_id):
    return query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)


def find_user(username):
    return query("SELECT * FROM users WHERE username = ?", (username,), one=True)


def create_user(username, password, role="user"):
    return execute(
        "INSERT INTO users (username, password, role, created) VALUES (?, ?, ?, ?)",
        (username, hash_password(password), role, int(time.time()))
    )


# ============================================================
# Servidores
# ============================================================

class Server:
    # Un servidor de Minecraft: fila de la base de datos + rutas derivadas

    FIELDS = ("id", "slug", "name", "owner_id", "type", "version", "max_gb", "cpu",
              "game_port", "internal_port", "autostop", "idle_minutes", "backups",
              "backup_time", "backup_keep", "backup_every_hours", "backup_every_hours_off", "icon", "state", "state_detail", "java", "created")

    def __init__(self, row):
        for field in self.FIELDS:
            setattr(self, field, row[field])

        # Rutas y contenedor pueden venir fijados (servidores importados)
        self.data_dir = row["data_dir"] or os.path.join(data_root(), self.slug)
        self.backup_dir = row["backup_dir"] or os.path.join(backup_root(), self.slug)
        self.container = row["container"] or ("mcs-" + self.slug)

        # Variables extra del contenedor (ej. FORGE_VERSION de un servidor importado)
        try:
            self.extra_env = json.loads(row["extra_env"] or "{}")
        except ValueError:
            self.extra_env = {}
        self.log_dir = os.path.join(LOG_ROOT, "servers", self.slug)
        self.state_dir = os.path.join(STATE_ROOT, "servers", self.slug)
        self.run_file = os.path.join(RUN_ROOT, "servers", self.slug + ".json")

    @property
    def address(self):
        host = get_setting("public_host") or PUBLIC_HOST or "localhost"

        if self.game_port == (19132 if is_bedrock(self) else 25565):
            return host

        return "%s:%d" % (host, self.game_port)

    def ensure_dirs(self):
        for path in (self.log_dir, self.state_dir, os.path.dirname(self.run_file)):
            os.makedirs(path, exist_ok=True)

        for path in (self.data_dir, self.backup_dir):
            # Nunca en la carpeta vacia de un disco que no esta montado
            if not path_available(path):
                continue

            os.makedirs(path, exist_ok=True)

            try:
                os.chown(path, MC_UID, MC_GID)
            except OSError:
                pass

    def write_env(self):
        # Archivo que leen los scripts de bash (respaldos)
        self.ensure_dirs()

        values = {
            "SLUG": self.slug,
            "CONTAINER": self.container,
            "DATA_DIR": self.data_dir,
            "BACKUP_DIR": self.backup_dir,
            "BACKUP_MOUNT": expected_mount(self.backup_dir) or "",
            "BACKUP_KEEP_AUTO": str(min(self.backup_keep, BACKUP_KEEP_MAX)),
            "LOG_DIR": self.log_dir,
            "EDITION": "bedrock" if is_bedrock(self) else "java",
            "RUN_DIR": os.path.dirname(self.run_file),
            "MC_UID": str(MC_UID),
            "MC_GID": str(MC_GID)
        }

        path = os.path.join(self.state_dir, "server.env")

        with open(path + ".tmp", "w", encoding="utf-8") as f:
            for key, value in values.items():
                f.write('%s="%s"\n' % (key, value.replace("\\", "\\\\").replace('"', '\\"')))

        os.replace(path + ".tmp", path)

    def public(self, owner_name=None):
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "owner": owner_name,
            "owner_id": self.owner_id,
            "type": self.type,
            "edition": "bedrock" if is_bedrock(self) else "java",
            "version": self.version,
            "max_gb": self.max_gb,
            "cpu": self.cpu,
            "game_port": self.game_port,
            "address": self.address,
            "autostop": bool(self.autostop),
            "idle_minutes": self.idle_minutes,
            "backups": bool(self.backups),
            "backup_time": self.backup_time,
            "backup_keep": self.backup_keep,
            "backup_every_hours": self.backup_every_hours,
            "backup_every_hours_off": self.backup_every_hours_off,
            "icon": self.icon,
            "state": self.state,
            "state_detail": self.state_detail,
            "loader": self.extra_env.get(LOADER_ENV.get(self.type, ""), ""),
            "java": self.java,
            "modpack": self.extra_env.get("MODRINTH_MODPACK") or self.extra_env.get("CF_SLUG", "")
        }


def list_servers():
    return [Server(row) for row in query("SELECT * FROM servers ORDER BY id")]


def get_server(server_id):
    row = query("SELECT * FROM servers WHERE id = ?", (server_id,), one=True)
    return Server(row) if row else None


def get_server_by_slug(slug):
    row = query("SELECT * FROM servers WHERE slug = ?", (slug,), one=True)
    return Server(row) if row else None


def servers_of(user_id):
    return [Server(row) for row in query(
        "SELECT * FROM servers WHERE owner_id = ? ORDER BY id", (user_id,)
    )]


def update_server(server_id, **fields):
    if not fields:
        return

    columns = ", ".join("%s = ?" % key for key in fields)
    execute("UPDATE servers SET %s WHERE id = ?" % columns, tuple(fields.values()) + (server_id,))


def make_slug(base):
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:20] or "server"
    candidate = slug
    n = 2

    while query("SELECT 1 FROM servers WHERE slug = ?", (candidate,), one=True):
        candidate = "%s-%d" % (slug, n)
        n += 1

    return candidate


def port_in_use(port, udp=False):
    if WINDOWS:
        # Sin ss: se intenta ocupar el puerto un momento
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)

        try:
            sock.bind(("0.0.0.0", port))
            return False
        except OSError:
            return True
        finally:
            sock.close()

    result = subprocess.run(["ss", "-lunH" if udp else "-ltnH", "( sport = :%d )" % port],
                            capture_output=True, text=True)
    return bool(result.stdout.strip())


def allocate_ports(bedrock=False):
    used_game = {r["game_port"] for r in query("SELECT game_port FROM servers")}
    used_internal = {r["internal_port"] for r in query("SELECT internal_port FROM servers")}

    game = BEDROCK_PORT_START if bedrock else GAME_PORT_START
    while game in used_game or port_in_use(game):
        game += 1

    internal = INTERNAL_PORT_START
    while internal in used_internal or port_in_use(internal):
        internal += 1

    return game, internal


def create_server_row(name, owner_id, type_, version, max_gb, cpu, **extra):
    game_port, internal_port = allocate_ports(is_bedrock(type_))
    slug = extra.pop("slug", None) or make_slug(name)

    values = {
        "slug": slug,
        "name": name,
        "owner_id": owner_id,
        "type": type_,
        "version": version,
        "max_gb": max_gb,
        "cpu": cpu,
        "game_port": extra.pop("game_port", None) or game_port,
        "internal_port": extra.pop("internal_port", None) or internal_port,
        "state": "creating",
        "created": int(time.time())
    }

    values.update(extra)

    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    server_id = execute("INSERT INTO servers (%s) VALUES (%s)" % (columns, marks), tuple(values.values()))

    return get_server(server_id)


# ============================================================
# Contenedores
# ============================================================

def runtime():
    # Docker o procesos normales (se carga aqui: runtime importa este modulo)
    import runtime as backend
    return backend


def docker(*args, check=False):
    result = subprocess.run(["docker"] + list(args), capture_output=True, text=True)

    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "docker " + " ".join(args))

    return result


def container_state(srv):
    # (estado, salud): running/exited/missing y healthy/starting/no-health
    return runtime().state(srv)[:2]


def build_container(srv, start=False):
    # (Re)crea el contenedor (o prepara los archivos del servidor en Windows).
    # El mundo vive en la carpeta del servidor: rehacerlo no borra nada.
    if not path_available(srv.data_dir):
        raise RuntimeError("El disco de los servidores no está conectado")

    srv.ensure_dirs()
    srv.write_env()
    runtime().build(srv, start)


def container_matches(srv):
    # True si lo que corre ya tiene la configuracion actual (nada pendiente)
    return runtime().matches(srv)


def remove_container(srv):
    runtime().remove(srv)


# ============================================================
# Eventos (notificaciones)
# ============================================================

def add_event(server_id, kind, level="info", message=""):
    execute(
        "INSERT INTO events (ts, server_id, kind, level, message) VALUES (?, ?, ?, ?, ?)",
        (int(time.time()), server_id, kind, level, message[:300])
    )

    # Se guardan solo los ultimos 7 dias
    execute("DELETE FROM events WHERE ts < ?", (int(time.time()) - 7 * 86400,))


def events_since(last_id, server_ids, include_system):
    marks = ",".join("?" for _ in server_ids) or "NULL"
    sql = "SELECT * FROM events WHERE id > ? AND (server_id IN (%s)" % marks

    if include_system:
        sql += " OR server_id IS NULL"

    sql += ") ORDER BY id LIMIT 100"

    return [dict(row) for row in query(sql, (last_id,) + tuple(server_ids))]


def last_event_id():
    row = query("SELECT MAX(id) AS n FROM events", one=True)
    return row["n"] or 0


# ============================================================
# Uso como comando
# ============================================================

# Variables que fijan la version del cargador de mods o del modpack
IMPORT_ENV_KEYS = (
    "FORGE_VERSION", "NEOFORGE_VERSION", "FABRIC_LOADER_VERSION", "FABRIC_LAUNCHER_VERSION",
    "QUILT_LOADER_VERSION", "PAPER_BUILD", "PAPER_CHANNEL", "MODPACK", "PACKWIZ_URL",
    "CF_SERVER_MOD", "CF_SLUG", "CF_FILE_ID", "MODRINTH_PROJECT", "MODRINTH_VERSION"
)


def import_server(argv):
    # Registra un mundo que ya existe (no lo mueve ni lo copia)
    import argparse

    parser = argparse.ArgumentParser(prog="mcpanel_core.py import-server")
    parser.add_argument("--name", required=True)
    parser.add_argument("--owner", required=True, help="usuario del panel que sera el dueno")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--backup-dir", default="")
    parser.add_argument("--type", default="VANILLA", choices=SERVER_TYPES)
    parser.add_argument("--version", default="LATEST")
    parser.add_argument("--ram", type=int, default=4)
    parser.add_argument("--cpu", type=int, default=0)
    parser.add_argument("--game-port", type=int, default=0)
    parser.add_argument("--container", default="", help="contenedor existente a reemplazar")
    parser.add_argument("--idle-minutes", type=int, default=10)
    parser.add_argument("--backup-time", default="04:00")
    parser.add_argument("--backup-keep", type=int, default=3)
    parser.add_argument("--backup-every-hours", type=int, default=24)
    parser.add_argument("--backup-every-hours-off", type=int, default=24)
    parser.add_argument("--env", action="append", default=[], help="variable extra KEY=VALUE (repetible)")
    parser.add_argument("--from-container", default="",
                        help="copia del contenedor existente las variables de version (FORGE_VERSION, etc.)")
    args = parser.parse_args(argv)

    extra = {}

    if args.from_container:
        result = docker("inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", args.from_container)

        for line in result.stdout.splitlines():
            key, _, value = line.partition("=")

            if key in IMPORT_ENV_KEYS:
                extra[key] = value

    for item in args.env:
        key, _, value = item.partition("=")

        if key:
            extra[key] = value

    owner = find_user(args.owner)

    if not owner:
        sys.exit("No existe el usuario " + args.owner)

    if not os.path.isdir(args.data_dir):
        sys.exit("No existe la carpeta " + args.data_dir)

    srv = create_server_row(
        args.name, owner["id"], args.type, args.version, args.ram, args.cpu,
        game_port=args.game_port or None,
        data_dir=os.path.realpath(args.data_dir),
        backup_dir=os.path.realpath(args.backup_dir) if args.backup_dir else "",
        container=args.container,
        idle_minutes=args.idle_minutes,
        backup_time=args.backup_time,
        backup_keep=args.backup_keep,
        backup_every_hours=args.backup_every_hours,
        backup_every_hours_off=args.backup_every_hours_off,
        extra_env=json.dumps(extra) if extra else ""
    )

    try:
        build_container(srv, start=False)
        update_server(srv.id, state="ready", state_detail="")
    except Exception as error:
        update_server(srv.id, state="error", state_detail=str(error)[:300])
        sys.exit("Error creando el contenedor: %s" % error)

    print("Servidor importado: id=%d slug=%s puerto=%d contenedor=%s variables=%s" % (
        srv.id, srv.slug, srv.game_port, srv.container, extra or "-"))


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "init":
        db().close()
        print(DB_PATH)
    elif len(sys.argv) == 3 and sys.argv[1] == "create-admin":
        # La contrasena llega por stdin para no dejarla en el historial
        password = sys.stdin.readline().rstrip("\n")

        if not USERNAME.match(sys.argv[2]) or len(password) < 6:
            sys.exit("Usuario no válido o contraseña de menos de 6 caracteres")

        if find_user(sys.argv[2]):
            sys.exit("Ese usuario ya existe")

        create_user(sys.argv[2], password, role="admin")
        print("Administrador creado: " + sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "import-server":
        import_server(sys.argv[2:])
    elif len(sys.argv) >= 5 and sys.argv[1] == "event":
        srv = get_server_by_slug(sys.argv[2])
        add_event(srv.id if srv else None, sys.argv[3], sys.argv[4],
                  sys.argv[5] if len(sys.argv) > 5 else "")
    elif len(sys.argv) == 3 and sys.argv[1] == "server-env":
        srv = get_server_by_slug(sys.argv[2])

        if not srv:
            sys.exit(1)

        srv.write_env()
        print(os.path.join(srv.state_dir, "server.env"))
    else:
        print(__doc__ or "usage: mcpanel_core.py event|server-env ...", file=sys.stderr)
        sys.exit(2)
