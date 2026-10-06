#
# MCServer by Derpchees - como corren los servidores
#
# Una sola forma de encender, apagar, mandar comandos y leer la consola,
# corra el servidor en Docker (Linux, runtime/docker.py) o como proceso
# normal (Windows, runtime/native.py). El resto del panel usa solo esto.
#

import mcpanel_core as core

if core.NATIVE:
    from . import native as backend
else:
    from . import docker as backend


def state(srv):
    # (estado, salud, codigo de salida)
    return backend.state(srv)


def running(srv):
    return backend.state(srv)[0] == "running"


def prepare(srv):
    # Lo que solo se puede cambiar con el servidor apagado (experimentos de Bedrock)
    if core.is_bedrock(srv):
        from bedrock import experiments

        try:
            experiments.apply_pending(srv)
        except (OSError, ValueError):
            pass


def start(srv):
    # (ok, error)
    if not running(srv):
        prepare(srv)

    return backend.start(srv)


def stop(srv):
    return backend.stop(srv)


def restart(srv):
    # Apagar y encender (no "docker restart"): asi pasa por prepare
    stop(srv)
    return start(srv)


def rcon(srv, args, timeout=20):
    # Comando de Java con su respuesta: (ok, texto)
    return backend.rcon(srv, args, timeout)


def console_send(srv, text):
    # Linea en la consola (Bedrock no tiene RCON): (ok, texto)
    return backend.console_send(srv, text)


def logs(srv, since=None, tail=None, timestamps=False):
    # Salida de la consola; since en segundos desde 1970
    return backend.logs(srv, since, tail, timestamps)


def started_at(srv):
    return backend.started_at(srv)


def stats():
    # {contenedor: {cpu, mem_used, mem_limit}} de los que estan encendidos
    return backend.stats()


def build(srv, start=False):
    return backend.build(srv, start)


def matches(srv):
    return backend.matches(srv)


def remove(srv):
    return backend.remove(srv)


def current_env(srv):
    return backend.current_env(srv)
