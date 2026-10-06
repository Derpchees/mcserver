#
# MCServer by Derpchees - servidores nuevos sin configurar
#
# Un servidor recien creado no se enciende solo (ni al crearlo ni cuando
# alguien intenta entrar) hasta que quien lo creo lo enciende desde el
# panel: asi elige antes la semilla, las reglas, los add-ons, etc.
# La marca es un archivo en la carpeta de estado del servidor.
#

import os

MARK = "setup-pending"


def path(srv):
    return os.path.join(srv.state_dir, MARK)


def pending(srv):
    return os.path.exists(path(srv))


def mark(srv):
    os.makedirs(srv.state_dir, exist_ok=True)
    open(path(srv), "w").close()


def clear(srv):
    try:
        os.remove(path(srv))
    except OSError:
        pass
