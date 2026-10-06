#
# MCServer by Derpchees - Cuentas y sesiones
#

import json
import os
import re
import time
import threading

import backup_schedule
import server_setup
import mcpanel_core as core
from push import kinds

from .common import BOOT_ID, FileError, log_server_action
from .versions import JAVA_CHOICES, LOADER_ENV, LOADER_TEXT
from .access import personal_default
from .motd import set_motd
from .containers import build_in_background
from .mods import CF_SLUG
from .icons import write_server_icon
from .storage_admin import data_disk_ready, storage_alert


VERSION_TEXT = re.compile(r"^(LATEST|SNAPSHOT|PREVIEW|[0-9][0-9A-Za-z._-]{0,19})$")

_failed_logins = {}
_auth_lock = threading.Lock()


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


def can_manage(user, srv):
    return bool(user) and (user["role"] == "admin" or srv.owner_id == user["id"])


def user_info(user):
    if not user:
        return None

    return {"id": user["id"], "username": user["username"], "role": user["role"],
            "owner": user["id"] == core.owner_id(),
            # Temas de avisos silenciados (push/kinds.py)
            "notify_mute": sorted(kinds.muted_of(user))}


def limits_for(user, as_admin=False):
    settings = core.all_settings()
    ram = core.system_ram_gb()
    cores = os.cpu_count() or 1
    admin = as_admin or (bool(user) and user["role"] == "admin")

    max_ram = ram if admin else min(ram, int(settings["max_ram_gb"] or 1))
    max_cpu = int(settings["max_cpu"] or 0)

    return {
        "system_ram_gb": ram,
        "cores": cores,
        "max_ram_gb": max(1, max_ram),
        "max_cpu": cores if admin or max_cpu <= 0 else min(cores, max_cpu),
        "max_servers": 1000 if admin else int(settings["max_servers_per_user"] or 1)
    }


def auth_state(user):
    settings = core.all_settings()
    setup = core.user_count() == 0

    return {
        "setup": setup,
        "user": user_info(user),
        "signup": settings["signup"] == "yes",
        # En la configuracion inicial quien llena el formulario sera el admin
        "limits": limits_for(user, as_admin=setup),
        "system_name": core.SYSTEM_NAME,
        "types": list(core.SERVER_TYPES),
        "bedrock_port_start": core.BEDROCK_PORT_START,
        # En Windows no hay discos ni HTTPS en Administracion
        "platform": "windows" if core.WINDOWS else "linux",
        "my_servers": [s.id for s in core.servers_of(user["id"])] if user else [],
        # Para el menu de la cuenta: nombre e icono de cada uno
        "my_server_list": [{"id": s.id, "name": s.name, "slug": s.slug, "icon": s.icon}
                           for s in core.servers_of(user["id"])] if user else [],
        "default_server": default_server_id(),
        "my_default": personal_default(user),
        "public_access": settings["public_access"] != "no",
        "cf_enabled": bool(settings["cf_api_key"]),
        # Disco desconectado o datos moviendose (solo lo ven los administradores)
        "storage_alert": storage_alert() if user and user["role"] == "admin" else None,
        "boot": BOOT_ID
    }


def default_server_id():
    value = core.get_setting("default_server")

    if value.isdigit() and core.get_server(int(value)):
        return int(value)

    return None


def check_new_password(password):
    if len(password or "") < 6:
        raise FileError("La contraseña debe tener al menos 6 caracteres")


def check_username(username):
    if not core.USERNAME.match(username or ""):
        raise FileError("Usuario no válido: 3 a 24 letras, números, punto, guion o guion bajo")

    if core.find_user(username):
        raise FileError("Ese usuario ya existe")


def clean_server_fields(data, user, partial=False):
    # Valida nombre, tipo, version y recursos dentro de los limites del usuario
    limits = limits_for(user)
    out = {}

    if not partial or "name" in data:
        name = re.sub(r"[\x00-\x1f\x7f]", " ", str(data.get("name", ""))).strip()[:40]

        if not name:
            raise FileError("Falta el nombre del servidor")

        out["name"] = name

    if not partial or "type" in data:
        type_ = str(data.get("type", "PAPER")).upper()

        if type_ not in core.SERVER_TYPES:
            raise FileError("Tipo de servidor no válido")

        out["type"] = type_

    if not partial or "version" in data:
        version = str(data.get("version", "LATEST")).strip() or "LATEST"

        if not VERSION_TEXT.match(version):
            raise FileError("Versión no válida")

        out["version"] = version

    if not partial or "max_gb" in data:
        try:
            max_gb = int(data.get("max_gb", 2))
        except (TypeError, ValueError):
            max_gb = 0

        if not 1 <= max_gb <= limits["max_ram_gb"]:
            raise FileError("La RAM debe estar entre 1 y %d GB" % limits["max_ram_gb"])

        out["max_gb"] = max_gb

    if not partial or "cpu" in data:
        try:
            cpu = int(data.get("cpu", 0))
        except (TypeError, ValueError):
            cpu = -1

        if not 0 <= cpu <= limits["max_cpu"]:
            raise FileError("Los núcleos deben estar entre 0 y %d" % limits["max_cpu"])

        # Con limite de CPU configurado por el admin, 0 (sin limite) no se permite
        if cpu == 0 and limits["max_cpu"] < limits["cores"]:
            cpu = limits["max_cpu"]

        out["cpu"] = cpu

    if "modpack" in data:
        modpack = str(data.get("modpack") or "").strip().lower()

        if modpack and not CF_SLUG.match(modpack):
            raise FileError("Modpack no válido")

        out["modpack"] = modpack

    if out.get("type") == "MODRINTH" and not partial and not out.get("modpack"):
        raise FileError("Elige un modpack")

    if out.get("type") == "AUTO_CURSEFORGE":
        if not core.get_setting("cf_api_key"):
            raise FileError("Falta la clave de API de CurseForge. El administrador la agrega en Administración.")

        if not partial and not out.get("modpack"):
            raise FileError("Elige un modpack de CurseForge")

    if "loader" in data:
        loader = str(data.get("loader") or "").strip()

        if loader and not LOADER_TEXT.match(loader):
            raise FileError("Versión del cargador no válida")

        out["loader"] = loader

    # Bedrock no usa Java ni cargador de mods
    if out.get("type") == "BEDROCK":
        data = {k: v for k, v in data.items() if k not in ("java", "loader", "modpack")}

    if "java" in data:
        java = str(data.get("java") or "")

        if java not in JAVA_CHOICES:
            raise FileError("Versión de Java no válida")

        out["java"] = java

    for key in ("autostop", "backups"):
        if key in data:
            out[key] = 1 if data[key] in (True, 1, "1", "true", "yes") else 0

    if "idle_minutes" in data:
        try:
            idle = int(data["idle_minutes"])
        except (TypeError, ValueError):
            idle = 0

        if not 1 <= idle <= 1440:
            raise FileError("Los minutos sin jugadores deben estar entre 1 y 1440")

        out["idle_minutes"] = idle

    if "backup_time" in data:
        value = str(data["backup_time"])

        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", value):
            raise FileError("Hora de respaldo no válida (HH:MM)")

        out["backup_time"] = value

    if "backup_keep" in data:
        try:
            keep = int(data["backup_keep"])
        except (TypeError, ValueError):
            keep = 0

        if not 1 <= keep <= core.BACKUP_KEEP_MAX:
            raise FileError("Respaldos a conservar: entre 1 y %d" % core.BACKUP_KEEP_MAX)

        out["backup_keep"] = keep

    # Cada cuantas horas se respalda encendido y apagado (apagado: 0 = nunca)
    for key, low in (("backup_every_hours", 1), ("backup_every_hours_off", 0)):
        if key in data:
            try:
                hours = int(data[key])
            except (TypeError, ValueError):
                hours = -1

            if not low <= hours <= 720:
                raise FileError("El intervalo de respaldos debe ser de 1 hora a 30 días")

            out[key] = hours

    return out


def create_server_for(user, data):
    fields = clean_server_fields(data, user)

    if len(core.servers_of(user["id"])) >= limits_for(user)["max_servers"]:
        raise FileError("Ya tienes el máximo de servidores permitidos")

    if data_disk_ready():
        raise FileError(data_disk_ready())

    type_ = fields.pop("type")
    loader = fields.pop("loader", "")
    modpack = fields.pop("modpack", "")

    if type_ == "BEDROCK":
        # Nombre en la lista de servidores (ver motd.set_bedrock_name)
        fields["extra_env"] = json.dumps({"SERVER_NAME": fields["name"]})
    elif type_ == "AUTO_CURSEFORGE":
        fields["extra_env"] = json.dumps({"CF_SLUG": modpack})
        fields["version"] = "LATEST"
    elif type_ == "MODRINTH":
        fields["extra_env"] = json.dumps({"MODRINTH_MODPACK": modpack})
        fields["version"] = "LATEST"
    elif loader and type_ in LOADER_ENV:
        fields["extra_env"] = json.dumps({LOADER_ENV[type_]: loader})

    srv = core.create_server_row(owner_id=user["id"], type_=type_, **fields)
    log_server_action(srv, "servidor creado por " + user["username"])

    # Mensaje inicial en la lista multijugador (el nombre) e icono propio
    try:
        if not core.is_bedrock(srv):
            set_motd(srv, srv.name, None)
            write_server_icon(srv)

        # Un servidor nuevo no tiene mundo que respaldar: el primer respaldo
        # automatico toca en el siguiente turno del horario
        backup_schedule.mark_done(srv)
    except OSError:
        pass
    # No se enciende hasta que su dueno lo configure y lo encienda
    server_setup.mark(srv)
    build_in_background(srv, start=False)

    return srv


def setup_admin(data):
    if core.user_count() > 0:
        raise FileError("El sistema ya está configurado", 403)

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    check_username(username)
    check_new_password(password)

    # El primer usuario es el dueno del sistema
    user_id = core.create_user(username, password, role="admin")
    user = core.get_user(user_id)
    core.set_setting("owner_id", user_id)
    core.set_setting("public_access", "no" if data.get("public_access") is False else "yes")

    if data.get("server"):
        create_server_for(user, data["server"])

    return user


def signup(data):
    if core.get_setting("signup") != "yes":
        raise FileError("El registro de cuentas está desactivado", 403)

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    check_username(username)
    check_new_password(password)

    # La cuenta se crea sola: el servidor se crea despues desde el panel
    user_id = core.create_user(username, password)
    return core.get_user(user_id)


def change_password(user, data):
    if not core.verify_password(str(data.get("current", "")), user["password"]):
        raise FileError("La contraseña actual no es correcta", 403)

    check_new_password(str(data.get("password", "")))
    core.execute("UPDATE users SET password = ? WHERE id = ?",
                 (core.hash_password(data["password"]), user["id"]))

    return {"ok": True, "message": "Contraseña actualizada"}
