#
# MCServer by Derpchees - Recreacion del contenedor (en segundo plano y pendiente)
#

import subprocess
import os
import threading

import mcpanel_core as core

from .common import log_server_action, set_stop_hint


def build_in_background(srv, start, restart_after=False):
    # Descargar la imagen puede tardar minutos: se hace en un hilo
    def work():
        try:
            if restart_after:
                set_stop_hint(srv, "restart")
                subprocess.run(["docker", "stop", srv.container], capture_output=True)

            core.build_container(srv, start=start or restart_after)
            core.update_server(srv.id, state="ready", state_detail="")

            clear_pending(srv)
        except Exception as error:
            core.update_server(srv.id, state="error", state_detail=str(error)[:300])
            core.add_event(srv.id, "server_error", "error", str(error)[:200])

    threading.Thread(target=work, daemon=True).start()


def pending_path(srv):
    return os.path.join(srv.state_dir, "pending_rebuild")


def clear_pending(srv):
    try:
        os.remove(pending_path(srv))
    except OSError:
        pass


def has_pending(srv):
    # Un cambio pendiente que se deshizo (ej. agregar y quitar el mismo mod)
    # ya no es pendiente: se compara con el contenedor que esta corriendo
    if not os.path.exists(pending_path(srv)):
        return False

    if core.container_matches(srv):
        clear_pending(srv)
        return False

    return True


def request_rebuild(srv):
    # Apagado: se recrea ya. Encendido: queda pendiente hasta que el
    # dueno lo aplique, para no sacar a los jugadores
    if core.container_state(srv)[0] == "running":
        if core.container_matches(srv):
            clear_pending(srv)
            return "none"

        os.makedirs(srv.state_dir, exist_ok=True)
        open(pending_path(srv), "w").close()
        return "pending"

    core.update_server(srv.id, state="creating", state_detail="rebuild")
    build_in_background(srv, start=False)
    return "applied"


def apply_pending(srv, user):
    running = core.container_state(srv)[0] == "running"
    core.update_server(srv.id, state="creating", state_detail="rebuild")
    build_in_background(srv, start=False, restart_after=running)
    log_server_action(srv, "cambios aplicados por " + user["username"])
    return {"ok": True, "message": "Aplicando cambios"}
