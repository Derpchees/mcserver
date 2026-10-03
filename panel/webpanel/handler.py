#
# MCServer by Derpchees - Rutas HTTP del panel
#

from http.server import BaseHTTPRequestHandler
import json
import os
import re
import time
import shutil
import urllib.parse
import http.cookies

import mcpanel_core as core

from .common import FileError, log_server_action, set_stop_hint, use_server
from .status import console, docker_action, send_command, server_data
from .stats import system_stats
from .chat import chat_history, chat_rate_limited, send_chat
from .files import (
    build_zip, delete_item, delete_items, list_files, make_folder, MAX_EDIT_BYTES, move_items,
    read_text_file, receive_upload, rename_item, safe_path, write_text_file,
)
from .players import list_players, player_action
from .properties import get_settings, save_settings
from .backups import backup_path, delete_backup, list_backups, start_backup
from .accounts import (
    auth_state, can_manage, change_password, create_server_for, create_session, end_session,
    login_blocked, register_login, SESSION_COOKIE, SESSION_SECONDS, session_user, setup_admin,
    signup,
)
from .servers import (
    check_double_confirm, delete_account, delete_server, list_public_servers,
    update_server_config,
)
from .admin import (
    admin_delete_user, admin_get_settings, admin_save_settings, admin_update_user, admin_users,
    start_uninstall, user_events,
)
from .versions import available_versions
from .access import is_owner, public_ok, set_personal_default
from .motd import set_motd
from .containers import apply_pending
from .mods import (
    add_mods, cf_search, clear_modpack, MOD_KIND, modrinth_search, mods_state, remove_mods,
    set_modpack,
)
from .mod_versions import modpack_versions, project_versions, set_modpack_version, set_project_version
from .storage_admin import data_disk_ready, storage_action, storage_get, storage_options_for
from .webassets import web


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

        output = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_body(output, "application/json; charset=utf-8", code, headers)


    def send_file(self, full, download_name):

        size = os.path.getsize(full)
        quoted = urllib.parse.quote(download_name)

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quoted)
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


    def read_body(self, limit=MAX_EDIT_BYTES + 1024):
        length = int(self.headers.get("Content-Length", "0") or 0)

        if length > limit:
            raise FileError("Contenido demasiado grande", 413)

        return self.rfile.read(length)


    def json_body(self, limit=65536):
        data = json.loads(self.read_body(limit) or b"{}")

        if not isinstance(data, dict):
            raise FileError("Petición no válida")

        return data


    def login_cookie(self, user):
        token = create_session(user["id"])
        return {
            "Set-Cookie": SESSION_COOKIE + "=" + token + "; Path=/; Max-Age="
            + str(SESSION_SECONDS) + "; HttpOnly; SameSite=Strict"
        }


    def deny(self, user):
        if user:
            self.send_json({"ok": False, "message": "No tienes permiso para esto"}, 403)
        else:
            self.send_json({"ok": False, "message": "Sesión no válida"}, 401)


    def guarded(self, work):
        try:
            work()
        except FileError as error:
            self.send_json({"ok": False, "message": str(error)}, error.code)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except json.JSONDecodeError:
            self.send_json({"ok": False, "message": "Petición no válida"}, 400)
        except Exception as error:
            self.send_json({"ok": False, "message": "Error: " + str(error)}, 500)


    # ========================================================
    # GET
    # ========================================================

    def do_GET(self):

        path, param = self.route()
        user = session_user(self.session_token())
        use_server(None)

        scoped = re.match(r"^/s/(\d+)(/.*)$", path)

        if scoped:
            self.guarded(lambda: self.server_get(int(scoped.group(1)), scoped.group(2), param, user))
            return

        if path == "/auth/state":
            self.send_json(auth_state(user))

        elif path == "/servers":
            if not public_ok(user):
                return self.deny(user)

            self.send_json({"servers": list_public_servers()})

        elif path == "/cf/modpacks":
            # El formulario de registro tambien busca modpacks
            if not user and core.get_setting("signup") != "yes" and core.user_count() > 0:
                return self.deny(user)

            self.guarded(lambda: self.send_json(cf_search("modpacks", param("q"))))

        elif path == "/modpacks":
            if not user and core.get_setting("signup") != "yes" and core.user_count() > 0:
                return self.deny(user)

            self.guarded(lambda: self.send_json(modrinth_search("modpacks", param("q"))))

        elif path == "/versions":
            self.guarded(lambda: self.send_json(available_versions(param("type"), param("mc"))))

        elif path == "/stats":
            if not user:
                return self.deny(user)
            self.send_json(system_stats())

        elif path == "/events":
            if not user:
                return self.deny(user)

            try:
                since = int(param("since", "-1"))
            except ValueError:
                since = -1

            self.send_json(user_events(user, since))

        elif path in ("/admin/users", "/admin/settings"):
            if not user or user["role"] != "admin":
                return self.deny(user)

            self.send_json({"users": admin_users()} if path == "/admin/users" else admin_get_settings())

        elif path in ("/admin/storage", "/admin/storage/options"):
            if not user or user["role"] != "admin":
                return self.deny(user)

            if path == "/admin/storage":
                self.send_json(storage_get())
            else:
                self.guarded(lambda: self.send_json(storage_options_for(param("role"))))

        elif path == "/app.js":
            self.send_body(web("js"), "text/javascript; charset=utf-8")

        elif path == "/app.css":
            self.send_body(web("css"), "text/css; charset=utf-8")

        else:
            self.send_body(web("page"), "text/html; charset=utf-8")


    def server_get(self, server_id, path, param, user):

        srv = core.get_server(server_id)

        if not srv:
            raise FileError("No existe el servidor", 404)

        use_server(srv)
        manage = can_manage(user, srv)

        # Publico: estado, recursos, consola y chat (si el admin lo permite)
        if path in ("/api", "/stats", "/console", "/chat") and not public_ok(user):
            return self.deny(user)

        if path == "/console":
            self.send_body(console().encode("utf-8"), "text/plain; charset=utf-8")
            return

        if path == "/chat":
            self.send_json(chat_history())
            return

        if path == "/api":
            data = server_data()
            owner = core.get_user(srv.owner_id) if srv.owner_id else None
            data["server"] = srv.public(owner["username"] if owner else None)
            data["can_manage"] = manage
            self.send_json(data)
            return

        if path == "/stats":
            self.send_json(system_stats())
            return

        if not manage:
            return self.deny(user)

        if path == "/chat":
            self.send_json(chat_history())

        elif path == "/console":
            self.send_body(console().encode("utf-8"), "text/plain; charset=utf-8")

        elif path == "/mods":
            self.send_json(mods_state())

        elif path == "/mods/search":
            kind = MOD_KIND.get(srv.type)

            if not kind:
                raise FileError("Este tipo de servidor no admite mods ni plugins")

            self.send_json(modrinth_search(kind, param("q"), srv.version, srv.type))

        elif path == "/mods/versions":
            self.send_json(project_versions(param("slug")))

        elif path == "/server/modpack/versions":
            self.send_json(modpack_versions(param("slug")))

        elif path == "/files/list":
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


    # ========================================================
    # POST
    # ========================================================

    def do_POST(self):

        path, param = self.route()
        user = session_user(self.session_token())
        use_server(None)

        scoped = re.match(r"^/s/(\d+)(/.*)$", path)

        if scoped:
            self.guarded(lambda: self.server_post(int(scoped.group(1)), scoped.group(2), param, user))
            return

        self.guarded(lambda: self.global_post(path, user))


    def global_post(self, path, user):

        ip = self.client_address[0]

        if path == "/auth/login":
            if login_blocked(ip):
                self.send_json({"ok": False, "message": "Demasiados intentos. Espera 5 minutos."}, 429)
                return

            data = self.json_body(4096)
            found = core.find_user(str(data.get("username", "")).strip())
            ok = bool(found) and core.verify_password(str(data.get("password", "")), found["password"])
            register_login(ip, ok)

            if not ok:
                time.sleep(1)
                self.send_json({"ok": False, "message": "Usuario o contraseña incorrectos"}, 401)
                return

            self.send_json({"ok": True}, headers=self.login_cookie(found))

        elif path == "/auth/logout":
            end_session(self.session_token())
            self.send_json({"ok": True}, headers={
                "Set-Cookie": SESSION_COOKIE + "=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
            })

        elif path == "/auth/setup":
            new_user = setup_admin(self.json_body())
            self.send_json({"ok": True}, headers=self.login_cookie(new_user))

        elif path == "/auth/signup":
            if login_blocked(ip):
                self.send_json({"ok": False, "message": "Demasiados intentos. Espera 5 minutos."}, 429)
                return

            new_user = signup(self.json_body())
            self.send_json({"ok": True}, headers=self.login_cookie(new_user))

        elif not user:
            self.deny(user)

        elif path == "/me/password":
            self.send_json(change_password(user, self.json_body(4096)))

        elif path == "/me/default":
            self.send_json(set_personal_default(user, self.json_body(4096)))

        elif path == "/me/delete":
            result = delete_account(user, self.json_body(4096))
            self.send_json(result, headers={
                "Set-Cookie": SESSION_COOKIE + "=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
            })

        elif path == "/servers/create":
            srv = create_server_for(user, self.json_body())
            self.send_json({"ok": True, "id": srv.id, "message": "Servidor creado"})

        elif user["role"] != "admin":
            self.deny(user)

        elif path == "/admin/users/update":
            self.send_json(admin_update_user(user, self.json_body(4096)))

        elif path == "/admin/users/delete":
            self.send_json(admin_delete_user(user, self.json_body(4096)))

        elif path == "/admin/settings":
            self.send_json(admin_save_settings(self.json_body(4096)))

        elif path.startswith("/admin/storage/"):
            self.send_json(storage_action(user, path, self.json_body(4096)))

        elif path == "/admin/uninstall":
            if not is_owner(user):
                raise FileError("Solo el dueño del sistema puede desinstalar", 403)

            self.send_json(start_uninstall(self.json_body(4096)))

        else:
            self.send_json({"ok": False, "message": "No encontrado"}, 404)


    def server_post(self, server_id, path, param, user):

        srv = core.get_server(server_id)

        if not srv:
            raise FileError("No existe el servidor", 404)

        use_server(srv)
        manage = can_manage(user, srv)

        if path.startswith("/action/"):
            action = path.split("/")[-1]

            if srv.state != "ready":
                raise FileError("El servidor todavía se está preparando")

            if action in ("start", "restart") and data_disk_ready():
                raise FileError(data_disk_ready())

            # Cualquiera puede encender (si el admin lo permite); apagar y
            # reiniciar solo el dueno o el admin
            if action != "start" and not manage:
                return self.deny(user)

            if not manage and not public_ok(user):
                return self.deny(user)

            if action in ("stop", "restart"):
                set_stop_hint(srv, "manual" if action == "stop" else "restart")
                log_server_action(srv, "%s por %s" % (action, user["username"]))

            self.send_json(docker_action(action))
            return

        # El chat esta abierto: cada quien aparece con su etiqueta
        if path == "/chat/send":
            if not manage and not public_ok(user):
                return self.deny(user)

            if chat_rate_limited(self.client_address[0]):
                self.send_json({"ok": False, "message": "Estás enviando mensajes muy rápido. Espera un momento."}, 429)
                return

            role = "server" if manage else ("user" if user else "guest")
            text = str(self.json_body(4096).get("text", ""))
            self.send_json(send_chat(text, role, user["username"] if user else None))
            return

        if not manage:
            return self.deny(user)

        if path == "/command":
            body = self.read_body().decode("utf-8", errors="replace")
            command_text = urllib.parse.parse_qs(body).get("command", [""])[0]
            self.send_json(send_command(command_text))

        elif path == "/chat/send":
            if chat_rate_limited(self.client_address[0]):
                self.send_json({"ok": False, "message": "Estás enviando mensajes muy rápido. Espera un momento."}, 429)
                return

            self.send_json(send_chat(str(self.json_body(4096).get("text", ""))))

        elif path == "/server/update":
            self.send_json(update_server_config(srv, self.json_body(4096), user))

        elif path == "/server/motd":
            self.send_json(set_motd(srv, self.json_body(4096).get("motd", ""), user))

        elif path == "/mods/add":
            self.send_json(add_mods(self.json_body(), user))

        elif path == "/mods/remove":
            self.send_json(remove_mods(self.json_body(), user))

        elif path == "/server/modpack/set":
            self.send_json(set_modpack(self.json_body(4096), user))

        elif path == "/server/modpack/clear":
            self.send_json(clear_modpack(user))

        elif path == "/mods/version":
            self.send_json(set_project_version(self.json_body(4096), user))

        elif path == "/server/modpack/version":
            self.send_json(set_modpack_version(self.json_body(4096), user))

        elif path == "/mods/apply":
            self.send_json(apply_pending(srv, user))

        elif path == "/server/delete":
            data = self.json_body(4096)
            check_double_confirm(data, srv.name)
            delete_server(srv, bool(data.get("purge_data")), bool(data.get("purge_backups")), user)
            self.send_json({"ok": True, "message": "Servidor eliminado"})

        elif path == "/files/upload":
            length = int(self.headers.get("Content-Length", "0") or 0)
            self.send_json(receive_upload(self, param("path"), param("name"), length))

        elif path == "/files/write":
            self.send_json(write_text_file(param("path"), self.read_body().decode("utf-8")))

        elif path == "/files/mkdir":
            self.send_json(make_folder(param("path"), param("name")))

        elif path == "/files/rename":
            self.send_json(rename_item(param("path"), param("name")))

        elif path == "/files/delete":
            self.send_json(delete_item(param("path")))

        elif path in ("/files/move", "/files/delete-many"):
            data = self.json_body(MAX_EDIT_BYTES)
            paths = data.get("paths")

            if not isinstance(paths, list):
                raise FileError("Petición no válida")

            paths = [str(p) for p in paths]

            if path == "/files/move":
                self.send_json(move_items(paths, str(data.get("dest", ""))))
            else:
                self.send_json(delete_items(paths))

        elif path == "/settings":
            self.send_json(save_settings(self.json_body().get("values")))

        elif path == "/players/action":
            self.send_json(player_action(self.json_body()))

        elif path == "/backups/create":
            self.send_json(start_backup())

        elif path == "/backups/delete":
            self.send_json(delete_backup(param("name")))

        else:
            self.send_json({"ok": False, "message": "No encontrado"}, 404)


    def log_message(self, format, *args):
        pass
