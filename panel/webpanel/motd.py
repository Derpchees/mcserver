#
# MCServer by Derpchees - Mensaje del servidor (MOTD)
#

import json
import os
import re

import mcpanel_core as core
import runtime

from .common import FileError, give_to_server, log_server_action, read_lines, use_server
from .properties import escape_property, unescape_property
from .containers import request_rebuild


MOTD_MAX = 200


def read_motd(srv):
    # Bedrock muestra en la lista el nombre del servidor (server-name)
    if core.is_bedrock(srv) and srv.extra_env.get("SERVER_NAME"):
        return srv.extra_env["SERVER_NAME"]

    key = "server-name=" if core.is_bedrock(srv) else "motd="

    for line in read_lines(os.path.join(srv.data_dir, "server.properties")):
        if line.startswith(key):
            return unescape_property(line[len(key):])

    return ""


def set_bedrock_name(srv, text, user):
    # La imagen de Bedrock nunca reemplaza un server.properties que ya existe
    # y lo ajusta con variables al arrancar: el nombre va en SERVER_NAME
    extra = dict(srv.extra_env)
    extra["SERVER_NAME"] = text or srv.name
    core.update_server(srv.id, extra_env=json.dumps(extra))
    fresh = core.get_server(srv.id)
    use_server(fresh)
    request_rebuild(fresh)

    if user:
        log_server_action(fresh, "mensaje del servidor cambiado por " + user["username"])

    return {"ok": True, "message": "Mensaje guardado",
            "running": core.container_state(fresh)[0] == "running"}


def set_motd(srv, text, user):
    text = str(text or "").replace("\r", "")
    lines = [re.sub(r"[\x00-\x1f\x7f]", "", line) for line in text.split("\n")]
    lines = lines[:1 if core.is_bedrock(srv) else 2]
    text = "\n".join(lines).rstrip("\n")

    if len(text) > MOTD_MAX:
        raise FileError("El mensaje es demasiado largo (máx. %d caracteres)" % MOTD_MAX)

    if core.is_bedrock(srv):
        return set_bedrock_name(srv, text, user)

    srv.ensure_dirs()
    path = os.path.join(srv.data_dir, "server.properties")
    entry = "motd=" + escape_property(text)
    out = []
    found = False

    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f.read().splitlines():
                if line.startswith("motd="):
                    out.append(entry)
                    found = True
                else:
                    out.append(line)

    if not found:
        out.append(entry)

    tmp = path + ".tmp-panel"

    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    os.chmod(tmp, 0o664)
    give_to_server(tmp)
    os.replace(tmp, path)

    # Contenedores creados con MOTD fijo lo reescribirian al arrancar
    if "MOTD" in runtime.current_env(srv):
        use_server(srv)
        request_rebuild(srv)

    if user:
        log_server_action(srv, "mensaje del servidor cambiado por " + user["username"])

    return {"ok": True, "message": "Mensaje guardado",
            "running": core.container_state(srv)[0] == "running"}
