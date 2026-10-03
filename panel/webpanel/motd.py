#
# MCServer by Derpchees - Mensaje del servidor (MOTD)
#

import os
import re

import mcpanel_core as core

from .common import FileError, give_to_server, log_server_action, read_lines, use_server
from .properties import escape_property, unescape_property
from .containers import request_rebuild


MOTD_MAX = 200


def read_motd(srv):
    for line in read_lines(os.path.join(srv.data_dir, "server.properties")):
        if line.startswith("motd="):
            return unescape_property(line[5:])

    return ""


def set_motd(srv, text, user):
    text = str(text or "").replace("\r", "")
    lines = [re.sub(r"[\x00-\x1f\x7f]", "", line) for line in text.split("\n")][:2]
    text = "\n".join(lines).rstrip("\n")

    if len(text) > MOTD_MAX:
        raise FileError("El mensaje es demasiado largo (máx. %d caracteres)" % MOTD_MAX)

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
    env = core.docker("inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", srv.container).stdout

    if any(line.startswith("MOTD=") for line in env.splitlines()):
        use_server(srv)
        request_rebuild(srv)

    if user:
        log_server_action(srv, "mensaje del servidor cambiado por " + user["username"])

    return {"ok": True, "message": "Mensaje guardado",
            "running": core.container_state(srv)[0] == "running"}
