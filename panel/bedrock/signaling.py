#
# MCServer by Derpchees - NetherNet: la conexion de Bedrock desde la 1.26
#
# El cliente habla primero por HTTP (TCP) con el puerto del servidor, casi
# siempre cifrado (TLS); en texto plano solo llega la consulta de estado:
#   GET /v1/join  -> estado para la lista de servidores (nombre, jugadores...)
#   lo demas      -> el ingreso (negocia la conexion UDP del juego)
# Lo cifrado no se puede leer: se trata como un ingreso y se reenvia tal cual.
# El juego viaja despues por UDP directo a un rango de puertos propio de
# cada servidor (server-udp-ports). El agente pasa el HTTP por su proxy
# TCP: asi contesta la lista con el servidor apagado y lo enciende al entrar.
#

import asyncio
import ipaddress
import json
import os
import socket
import urllib.request

import mcpanel_core as core


STATUS_PATH = "/v1/join"
HEAD_LIMIT = 16384

# Puertos UDP del juego por servidor (uno por conexion de jugador)
UDP_PORTS = 20

TEXT = {
    "off": {"es": "Apagado: entra para encenderlo", "en": "Sleeping: join to start it"},
    "nodisk": {"es": "No disponible", "en": "Unavailable"}
}


def text(key):
    return TEXT[key]["es" if core.DEFAULT_LANG == "es" else "en"]


def udp_range(srv):
    # Rango UDP fijo segun el puerto del servidor: 19132 -> 19132-19151,
    # 19133 -> 19152-19171... (los puertos UDP no chocan con los TCP)
    start = core.BEDROCK_PORT_START
    base = start + max(0, srv.game_port - start) * UDP_PORTS
    return base, base + UDP_PORTS - 1


def advertised_ip():
    # IP que el servidor anuncia para el UDP del juego: la de los jugadores.
    # Tiene que ser una IP (no un dominio); dentro de Docker no sabe la suya.
    host = core.get_setting("public_host") or core.PUBLIC_HOST

    for candidate in (host, core.LISTEN_IP):
        if not candidate or candidate == "0.0.0.0":
            continue

        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass

        try:
            return socket.gethostbyname(candidate)
        except OSError:
            pass

    # La IP con la que este equipo sale a la red (sin enviar nada)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("1.1.1.1", 53))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def status(port, timeout=2.0):
    # Estado del servidor real (puerto interno) o None si no responde
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, STATUS_PATH), timeout=timeout) as response:
            data = json.loads(response.read(65536))
    except (OSError, ValueError):
        return None

    return data if isinstance(data, dict) else None


def cache_path(srv):
    return os.path.join(srv.state_dir, "bedrock-status.json")


def remember(srv, data):
    try:
        os.makedirs(srv.state_dir, exist_ok=True)

        with open(cache_path(srv), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def cached(srv):
    try:
        with open(cache_path(srv), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}

    return data if isinstance(data, dict) else {}


def is_status_request(head):
    # Solo la consulta de la lista; cualquier otra peticion es un ingreso
    line = head.split(b"\r\n", 1)[0].decode("latin-1", "replace").split()
    headers = head.lower()

    return (len(line) >= 2 and line[0] == "GET" and line[1].split("?")[0] == STATUS_PATH
            and b"upgrade:" not in headers)


def offline_response(srv, state="off"):
    # Lo que ve el jugador en la lista con el servidor apagado
    data = cached(srv)
    name = data.get("name") or srv.extra_env.get("SERVER_NAME") or srv.name

    body = json.dumps({
        "name": "%s (%s)" % (name, text(state)),
        "protocol": data.get("protocol", 0),
        "version": data.get("version", ""),
        "level": data.get("level", "Bedrock level"),
        "players": 0,
        "maxPlayers": data.get("maxPlayers", 10),
        "gameType": data.get("gameType", 0)
    }, ensure_ascii=False).encode("utf-8")

    return (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n"
            b"Connection: close\r\n\r\n" % len(body)) + body


def is_tls(head):
    # Saludo TLS (ClientHello): el juego entrando por la conexion cifrada
    return head[:1] == b"\x16"


async def read_head(reader, timeout):
    # Lee hasta el final de los encabezados HTTP (lo leido se reenvia despues).
    # Con TLS se devuelve el primer pedazo: el cliente espera respuesta del
    # servidor y no mandaria nada mas.
    data = b""

    while b"\r\n\r\n" not in data and len(data) < HEAD_LIMIT:
        chunk = await asyncio.wait_for(reader.read(4096), timeout)

        if not chunk:
            break

        data += chunk

        if is_tls(data):
            break

    return data
