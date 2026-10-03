#
# MCServer by Derpchees - Acceso publico, dueno del sistema y favorito personal
#


import mcpanel_core as core

from .common import FileError


def public_ok(user):
    # Sin sesion solo se puede ver y encender si el admin lo permite
    return bool(user) or core.get_setting("public_access") != "no"


def is_owner(user):
    return bool(user) and user["id"] == core.owner_id()


def personal_default(user):
    if user and user["default_server"] and core.get_server(user["default_server"]):
        return user["default_server"]

    return None


def set_personal_default(user, data):
    value = str(data.get("server") or "").strip()

    if value and not (value.isdigit() and core.get_server(int(value))):
        raise FileError("Ese servidor no existe")

    core.execute("UPDATE users SET default_server = ? WHERE id = ?",
                 (int(value) if value else None, user["id"]))

    return {"ok": True}
