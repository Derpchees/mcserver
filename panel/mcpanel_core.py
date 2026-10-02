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
import sqlite3
import subprocess
import sys
import threading
import time


# ============================================================
# Configuracion del sistema
# ============================================================

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


SYSTEM_NAME = cfg("SYSTEM_NAME", "MCServer")
DEFAULT_LANG = cfg("LANG_DEFAULT", "en")
INSTALL_DIR = cfg("INSTALL_DIR", "/opt/mcpanel")
DATA_ROOT = cfg("DATA_ROOT", "/srv/minecraft/servers")
BACKUP_ROOT = cfg("BACKUP_ROOT", "/srv/minecraft/backups")
BACKUP_MOUNT = cfg("BACKUP_MOUNT", "")
LOG_ROOT = cfg("LOG_DIR", "/var/log/mcpanel")
STATE_ROOT = cfg("STATE_DIR", "/var/lib/mcpanel")
RUN_ROOT = cfg("RUN_DIR", "/run/mcpanel")
LISTEN_IP = cfg("LISTEN_IP", "0.0.0.0")
PUBLIC_HOST = cfg("PUBLIC_HOST", "")
PANEL_PORT = int(cfg("PANEL_PORT", "8090"))
PANEL_BIND = cfg("PANEL_BIND", "0.0.0.0")
GAME_PORT_START = int(cfg("GAME_PORT_START", "25565"))
INTERNAL_PORT_START = int(cfg("INTERNAL_PORT_START", "35565"))
MC_UID = int(cfg("MC_UID", "1000"))
MC_GID = int(cfg("MC_GID", "1000"))
IMAGE = cfg("IMAGE", "itzg/minecraft-server")
DOCKER_NETWORK = cfg("DOCKER_NETWORK", "mcpanel-net")

DB_PATH = os.path.join(STATE_ROOT, "mcpanel.db")

SERVER_TYPES = ("FORGE", "FABRIC", "PAPER", "VANILLA")


def system_ram_gb():
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
    state TEXT NOT NULL DEFAULT 'ready',
    state_detail TEXT NOT NULL DEFAULT '',
    data_dir TEXT NOT NULL DEFAULT '',
    backup_dir TEXT NOT NULL DEFAULT '',
    container TEXT NOT NULL DEFAULT '',
    extra_env TEXT NOT NULL DEFAULT '',
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
        "max_servers_per_user": "1"
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
              "backup_time", "backup_keep", "state", "state_detail", "created")

    def __init__(self, row):
        for field in self.FIELDS:
            setattr(self, field, row[field])

        # Rutas y contenedor pueden venir fijados (servidores importados)
        self.data_dir = row["data_dir"] or os.path.join(DATA_ROOT, self.slug)
        self.backup_dir = row["backup_dir"] or os.path.join(BACKUP_ROOT, self.slug)
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

        if self.game_port == 25565:
            return host

        return "%s:%d" % (host, self.game_port)

    def ensure_dirs(self):
        for path in (self.log_dir, self.state_dir, os.path.dirname(self.run_file)):
            os.makedirs(path, exist_ok=True)

        for path in (self.data_dir, self.backup_dir):
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
            "BACKUP_MOUNT": BACKUP_MOUNT if self.backup_dir.startswith(BACKUP_ROOT) else "",
            "BACKUP_KEEP_AUTO": str(self.backup_keep),
            "LOG_DIR": self.log_dir,
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
            "state": self.state,
            "state_detail": self.state_detail
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


def port_in_use(port):
    result = subprocess.run(["ss", "-ltnH", "( sport = :%d )" % port],
                            capture_output=True, text=True)
    return bool(result.stdout.strip())


def allocate_ports():
    used_game = {r["game_port"] for r in query("SELECT game_port FROM servers")}
    used_internal = {r["internal_port"] for r in query("SELECT internal_port FROM servers")}

    game = GAME_PORT_START
    while game in used_game or port_in_use(game):
        game += 1

    internal = INTERNAL_PORT_START
    while internal in used_internal or port_in_use(internal):
        internal += 1

    return game, internal


def create_server_row(name, owner_id, type_, version, max_gb, cpu, **extra):
    game_port, internal_port = allocate_ports()
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

def java_tag(version):
    # Version de Java que necesita cada version de Minecraft
    m = re.match(r"^1\.(\d+)(?:\.(\d+))?", version or "")

    if not m:
        return "latest"

    minor = int(m.group(1))
    patch = int(m.group(2) or 0)

    if minor < 17:
        return "java8"
    if minor == 17:
        return "java16"
    if minor < 20 or (minor == 20 and patch < 5):
        return "java17"

    return "latest"


def docker(*args, check=False):
    result = subprocess.run(["docker"] + list(args), capture_output=True, text=True)

    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "docker " + " ".join(args))

    return result


def container_state(srv):
    result = docker("inspect", "-f",
                    "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}",
                    srv.container)

    if result.returncode != 0:
        return "missing", "missing"

    status, _, health = result.stdout.strip().partition("|")
    return status, health


def build_container(srv, start=False):
    # (Re)crea el contenedor con los recursos del servidor. El mundo vive
    # en la carpeta del servidor, asi que recrearlo no borra nada.
    srv.ensure_dirs()
    srv.write_env()

    image = "%s:%s" % (IMAGE, java_tag(srv.version))

    if docker("image", "inspect", image).returncode != 0:
        docker("pull", "-q", image, check=True)

    if docker("network", "inspect", DOCKER_NETWORK).returncode != 0:
        docker("network", "create", DOCKER_NETWORK)

    docker("rm", "-f", srv.container)

    tz = subprocess.run(["timedatectl", "show", "-p", "Timezone", "--value"],
                        capture_output=True, text=True).stdout.strip() or "UTC"

    init_gb = max(1, srv.max_gb // 2)

    args = [
        "create",
        "--name", srv.container,
        "--network", DOCKER_NETWORK,
        "--label", "mcpanel.server=" + srv.slug,
        "-p", "127.0.0.1:%d:25565" % srv.internal_port,
        "-v", "%s:/data" % srv.data_dir,
        "-e", "EULA=TRUE",
        "-e", "TYPE=" + srv.type,
        "-e", "VERSION=" + srv.version,
        "-e", "INIT_MEMORY=%dG" % init_gb,
        "-e", "MAX_MEMORY=%dG" % srv.max_gb,
        "-e", "UID=%d" % MC_UID,
        "-e", "GID=%d" % MC_GID,
        "-e", "TZ=" + tz,
        "-e", "MOTD=" + srv.name,
        "--stop-timeout", "60",
        "--restart", "no" if srv.autostop else "unless-stopped"
    ]

    if srv.type == "PAPER":
        args += ["-e", "USE_AIKAR_FLAGS=true"]

    for key, value in sorted(srv.extra_env.items()):
        args += ["-e", "%s=%s" % (key, value)]

    if srv.cpu and srv.cpu > 0:
        args += ["--cpus", str(srv.cpu)]

    docker(*(args + [image]), check=True)

    if start:
        docker("start", srv.container, check=True)


def remove_container(srv):
    docker("rm", "-f", srv.container)


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
