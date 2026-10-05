#
# MCServer by Derpchees - Administracion
#

import subprocess
import os
import re
import time

import mcpanel_core as core
from push import kinds

from .common import FileError, INSTALL_DIR
from .accounts import check_new_password
from .sessions import end_user_sessions
from .servers import check_double_confirm, delete_server
from .access import is_owner


def admin_users():
    servers = {}

    for srv in core.list_servers():
        servers.setdefault(srv.owner_id, []).append({"id": srv.id, "name": srv.name})

    owner = core.owner_id()

    return [{
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "owner": row["id"] == owner,
        "created": row["created"],
        "servers": servers.get(row["id"], [])
    } for row in core.query("SELECT * FROM users ORDER BY id")]


def admin_update_user(admin, data):
    target = core.get_user(int(data.get("id", 0)))

    if not target:
        raise FileError("No existe el usuario", 404)

    if is_owner(target) and target["id"] != admin["id"]:
        raise FileError("Nadie puede cambiar la cuenta del dueño del sistema")

    if "role" in data:
        if not is_owner(admin):
            raise FileError("Solo el dueño del sistema puede cambiar roles")

        role = data["role"]

        if role not in ("admin", "user"):
            raise FileError("Rol no válido")

        if target["id"] == admin["id"] and role != "admin":
            raise FileError("No puedes quitarte el rol de administrador a ti mismo")

        core.execute("UPDATE users SET role = ? WHERE id = ?", (role, target["id"]))

    if data.get("password"):
        check_new_password(data["password"])
        core.execute("UPDATE users SET password = ? WHERE id = ?",
                     (core.hash_password(data["password"]), target["id"]))
        end_user_sessions(target["id"])

    return {"ok": True, "message": "Usuario actualizado"}


def admin_delete_user(admin, data):
    target = core.get_user(int(data.get("id", 0)))

    if not target:
        raise FileError("No existe el usuario", 404)

    if target["id"] == admin["id"]:
        raise FileError("Para borrar tu propia cuenta usa la página de tu cuenta")

    if is_owner(target):
        raise FileError("Nadie puede borrar la cuenta del dueño del sistema")

    check_double_confirm(data, target["username"])

    for srv in core.servers_of(target["id"]):
        delete_server(srv, bool(data.get("purge_data")), bool(data.get("purge_backups")), admin)

    end_user_sessions(target["id"])
    core.execute("DELETE FROM users WHERE id = ?", (target["id"],))

    return {"ok": True, "message": "Usuario eliminado"}


def admin_get_settings():
    values = core.all_settings()

    # La clave no se devuelve; solo si existe
    values["cf_api_key_set"] = bool(values.pop("cf_api_key", ""))
    values["limits"] = {"system_ram_gb": core.system_ram_gb(), "cores": os.cpu_count() or 1}
    return values


def admin_save_settings(data):
    if "signup" in data:
        core.set_setting("signup", "yes" if data["signup"] in (True, "yes", "true", 1) else "no")

    for key, low, high in (("max_ram_gb", 1, core.system_ram_gb()),
                           ("max_cpu", 0, os.cpu_count() or 1),
                           ("max_servers_per_user", 1, 50)):
        if key in data:
            try:
                value = int(data[key])
            except (TypeError, ValueError):
                raise FileError("Valor no válido: " + key)

            if not low <= value <= high:
                raise FileError("%s debe estar entre %d y %d" % (key, low, high))

            core.set_setting(key, value)

    if "public_access" in data:
        core.set_setting("public_access", "yes" if data["public_access"] in (True, "yes", "true", 1) else "no")

    if "cf_api_key" in data:
        key = str(data["cf_api_key"] or "").strip()

        if key and not re.match(r"^[\x21-\x7e]{10,200}$", key):
            raise FileError("La clave de CurseForge no parece válida")

        core.set_setting("cf_api_key", key)

    if "default_server" in data:
        value = str(data["default_server"] or "").strip()

        if value and not (value.isdigit() and core.get_server(int(value))):
            raise FileError("Ese servidor no existe")

        core.set_setting("default_server", value)

    if "public_host" in data:
        host = str(data["public_host"]).strip()

        if host and not re.match(r"^[A-Za-z0-9.:\[\]-]{1,100}$", host):
            raise FileError("Dirección pública no válida")

        core.set_setting("public_host", host)

    return {"ok": True, "message": "Ajustes guardados"}


def start_uninstall(data):
    check_double_confirm(data, core.SYSTEM_NAME)

    script = os.path.join(INSTALL_DIR, "uninstall.sh")

    if not os.path.isfile(script):
        raise FileError("No se encontró uninstall.sh", 404)

    args = [script, "--yes"]

    if data.get("purge_data"):
        args.append("--purge-data")

    if data.get("purge_backups"):
        args.append("--purge-backups")

    # Corre fuera de este servicio, que se va a detener y borrar
    result = subprocess.run(
        ["systemd-run", "--unit", "mcpanel-uninstall-%d" % int(time.time()),
         "--collect", "--quiet", core.CONFIG_SETENV] + args,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise FileError("No se pudo iniciar la desinstalación: " + result.stderr.strip(), 500)

    return {"ok": True, "message": "Desinstalando"}


def user_events(user, since):
    if since < 0:
        return {"last": core.last_event_id(), "events": []}

    if user["role"] == "admin":
        ids = [s.id for s in core.list_servers()]
    else:
        ids = [s.id for s in core.servers_of(user["id"])]

    events = core.events_since(since, ids, user["role"] == "admin")
    servers = {s.id: s for s in core.list_servers()}
    # El cursor avanza aunque se omitan los temas silenciados
    last = events[-1]["id"] if events else since
    events = kinds.wanted(events, kinds.muted_of(user))

    for event in events:
        srv = servers.get(event["server_id"])
        event["server"] = srv.name if srv else None
        # La pagina dibuja el icono del servidor con su slug
        event["server_slug"] = srv.slug if srv else None

    return {"last": last, "events": events}
