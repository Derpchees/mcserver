#
# MCServer by Derpchees - primer arranque de un servidor Bedrock
#
# Bedrock trae la lista de permitidos activada y vacia: nadie podria entrar.
# La primera vez que el servidor queda listo se apaga (como en Java, donde
# viene desactivada). Despues el dueno la cambia en Ajustes cuando quiera.
# Lo llama el agente; una marca en el estado evita repetirlo.
#

import os

from . import console


MARKER = "bedrock-firstboot"


def run(srv, uid, gid):
    marker = os.path.join(srv.state_dir, MARKER)
    path = os.path.join(srv.data_dir, "server.properties")

    if os.path.exists(marker) or not os.path.isfile(path):
        return False

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    lines = ["allow-list=false" if line.startswith("allow-list=") else line for line in lines]
    tmp = path + ".tmp-panel"

    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        os.chown(tmp, uid, gid)
    except OSError:
        pass

    os.replace(tmp, path)

    # Tambien en el servidor encendido, sin reiniciar
    console.send(srv, "allowlist off")

    os.makedirs(srv.state_dir, exist_ok=True)
    open(marker, "w").close()
    return True
