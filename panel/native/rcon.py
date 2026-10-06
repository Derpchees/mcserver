#
# MCServer by Derpchees - cliente RCON (lo que hace rcon-cli en Docker)
#
# Protocolo de Minecraft Java: paquetes <largo><id><tipo><texto>\0\0.
# Tipo 3 = iniciar sesion, 2 = comando, 0 = respuesta.
#

import socket
import struct


class RconError(Exception):
    pass


def packet(request_id, kind, text):
    body = struct.pack("<ii", request_id, kind) + text.encode("utf-8") + b"\x00\x00"
    return struct.pack("<i", len(body)) + body


def read_exact(sock, size):
    data = b""

    while len(data) < size:
        chunk = sock.recv(size - len(data))

        if not chunk:
            raise RconError("conexión cerrada")

        data += chunk

    return data


def read_packet(sock):
    size = struct.unpack("<i", read_exact(sock, 4))[0]
    body = read_exact(sock, size)
    request_id, kind = struct.unpack("<ii", body[:8])
    return request_id, kind, body[8:-2].decode("utf-8", "replace")


def command(port, password, text, timeout=20):
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
        sock.sendall(packet(1, 3, password))
        request_id, _, _ = read_packet(sock)

        if request_id == -1:
            raise RconError("contraseña de RCON incorrecta")

        sock.sendall(packet(2, 2, text))
        parts = [read_packet(sock)[2]]

        # Una respuesta larga llega en varios paquetes seguidos (Paper cierra
        # la conexion si se le manda un paquete vacio para marcar el final)
        sock.settimeout(0.2)

        try:
            while True:
                request_id, _, body = read_packet(sock)

                if request_id != 2:
                    break

                parts.append(body)
        except (OSError, RconError):
            pass

        return "".join(parts)
