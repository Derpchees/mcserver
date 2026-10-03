#
# MCServer by Derpchees - Servidores: estado, cambios y borrado
#

import json
import os
import shutil

import mcpanel_core as core

from .common import FileError, log_server_action, read_json_file, set_stop_hint
from .accounts import clean_server_fields, end_user_sessions
from .versions import LOADER_ENV
from .access import is_owner
from .motd import read_motd
from .containers import build_in_background


def server_summary(srv, owners):
    state = read_json_file(srv.run_file, {})

    info = srv.public(owners.get(srv.owner_id))
    info.update({
        "motd": read_motd(srv),
        "running": bool(state.get("running")),
        "health": state.get("health", "offline"),
        "players": state.get("players", 0),
        "names": state.get("names", [])
    })

    return info


def list_public_servers():
    owners = {row["id"]: row["username"] for row in core.query("SELECT id, username FROM users")}
    return [server_summary(srv, owners) for srv in core.list_servers()]


def update_server_config(srv, data, user):
    fields = clean_server_fields(data, user, partial=True)
    loader = fields.pop("loader", None)
    modpack = fields.pop("modpack", None)
    new_type = fields.get("type", srv.type)

    # El cargador y el modpack viven en las variables extra del contenedor
    if loader is not None or modpack is not None or new_type != srv.type:
        extra = dict(srv.extra_env)

        for key in list(LOADER_ENV.values()) + ["CF_SLUG", "MODRINTH_MODPACK", "CF_FILE_ID", "MODRINTH_VERSION"]:
            extra.pop(key, None)

        value = loader if loader is not None else ""

        if value and new_type in LOADER_ENV:
            extra[LOADER_ENV[new_type]] = value

        if new_type == "AUTO_CURSEFORGE":
            slug = modpack if modpack else srv.extra_env.get("CF_SLUG", "")

            if not slug:
                raise FileError("Elige un modpack de CurseForge")

            extra["CF_SLUG"] = slug

            # La version elegida solo sigue si el modpack es el mismo
            if slug == srv.extra_env.get("CF_SLUG") and srv.extra_env.get("CF_FILE_ID"):
                extra["CF_FILE_ID"] = srv.extra_env["CF_FILE_ID"]

        if new_type == "MODRINTH":
            slug = modpack if modpack else srv.extra_env.get("MODRINTH_MODPACK", "")

            if not slug:
                raise FileError("Elige un modpack")

            extra["MODRINTH_MODPACK"] = slug

            if slug == srv.extra_env.get("MODRINTH_MODPACK") and srv.extra_env.get("MODRINTH_VERSION"):
                extra["MODRINTH_VERSION"] = srv.extra_env["MODRINTH_VERSION"]

        if extra != srv.extra_env:
            fields["extra_env"] = json.dumps(extra) if extra else ""

    def current(key):
        if key == "extra_env":
            return json.dumps(srv.extra_env) if srv.extra_env else ""
        return getattr(srv, key)

    changed = {k: v for k, v in fields.items() if current(k) != v}

    if not changed:
        return {"ok": True, "message": "Sin cambios", "rebuild": False}

    core.update_server(srv.id, **changed)
    fresh = core.get_server(srv.id)
    fresh.write_env()
    log_server_action(fresh, "configuración cambiada por %s: %s" % (user["username"], ", ".join(sorted(changed))))

    # Recursos, tipo o version: hay que recrear el contenedor
    rebuild = bool({"type", "version", "max_gb", "cpu", "autostop", "name", "extra_env", "java"} & set(changed))

    if rebuild:
        running = core.container_state(fresh)[0] == "running"
        core.update_server(srv.id, state="creating", state_detail="rebuild")
        build_in_background(fresh, start=False, restart_after=running)

    return {"ok": True, "message": "Servidor actualizado", "rebuild": rebuild}


def safe_delete_dir(path, root):
    # Solo se borran carpetas dentro de las raices de datos o respaldos
    real = os.path.realpath(path)
    allowed = [os.path.realpath(r) for r in (core.data_root(), core.backup_root(), root) if r]

    if real in allowed or not any(real.startswith(a + os.sep) for a in allowed):
        return False

    shutil.rmtree(real, ignore_errors=True)
    return True


def delete_server(srv, purge_data, purge_backups, user):
    set_stop_hint(srv, "manual")
    core.remove_container(srv)

    if purge_data:
        safe_delete_dir(srv.data_dir, os.path.dirname(srv.data_dir))

    if purge_backups:
        safe_delete_dir(srv.backup_dir, os.path.dirname(srv.backup_dir))

    shutil.rmtree(srv.state_dir, ignore_errors=True)

    for path in (srv.run_file, srv.run_file + ".hint"):
        try:
            os.remove(path)
        except OSError:
            pass

    core.execute("DELETE FROM servers WHERE id = ?", (srv.id,))
    core.execute("UPDATE users SET default_server = NULL WHERE default_server = ?", (srv.id,))

    if core.get_setting("default_server") == str(srv.id):
        core.set_setting("default_server", "")

    core.add_event(None, "server_deleted", "info", "%s (%s)" % (srv.name, user["username"]))


def check_double_confirm(data, expected):
    # Doble confirmacion: casilla "entiendo" + escribir el texto exacto
    if not data.get("understand"):
        raise FileError("Falta confirmar que entiendes que no se puede deshacer")

    if str(data.get("confirm", "")).strip() != expected:
        raise FileError("El texto de confirmación no coincide")


def delete_account(user, data):
    check_double_confirm(data, user["username"])

    if is_owner(user):
        raise FileError("El dueño del sistema no puede borrar su cuenta; para quitar todo usa Desinstalar")

    if user["role"] == "admin":
        admins = core.query("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'", one=True)["n"]

        if admins <= 1:
            raise FileError("Eres el único administrador; nombra a otro antes de borrar tu cuenta")

    for srv in core.servers_of(user["id"]):
        delete_server(srv, bool(data.get("purge_data")), bool(data.get("purge_backups")), user)

    end_user_sessions(user["id"])
    core.execute("DELETE FROM users WHERE id = ?", (user["id"],))

    return {"ok": True, "message": "Cuenta eliminada"}
