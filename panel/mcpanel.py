#!/usr/bin/env python3
#
# MCServer by Derpchees
# https://github.com/Derpchees/mcserver
#
# Panel web para administrar varios servidores de Minecraft en Docker
# (itzg/minecraft-server), con cuentas de usuario. La configuracion del
# sistema vive en /etc/mcpanel/config.env y los datos en SQLite
# (mcpanel_core.py).
#
# El codigo del panel esta en webpanel/ (un modulo por tema) y la pagina
# en web/ (index.html, css/ y js/).
#

from http.server import ThreadingHTTPServer
import os
import socket
import ssl
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mcpanel_core as core  # noqa: E402

from webpanel.handler import Handler  # noqa: E402
from webpanel.players import timeout_loop  # noqa: E402
from webpanel.stats import slow_stats_loop, stats_loop  # noqa: E402

PORT = core.PANEL_PORT
BIND = core.PANEL_BIND

threading.Thread(target=stats_loop, daemon=True).start()
threading.Thread(target=slow_stats_loop, daemon=True).start()
threading.Thread(target=timeout_loop, daemon=True).start()

class PanelServer(ThreadingHTTPServer):
    # Con HTTPS activo, el mismo puerto atiende las dos cosas: si la conexion
    # empieza con un saludo TLS se cifra; si es HTTP normal, el manejador la
    # redirige a https:// (asi siguen sirviendo los enlaces viejos). Todo se
    # hace en el hilo de cada conexion, para que un cliente lento no frene
    # a los demas.

    tls = None

    def finish_request(self, request, client_address):
        secure = None

        if self.tls:
            try:
                request.settimeout(15)
                first = request.recv(1, socket.MSG_PEEK)
            except OSError:
                return

            if first == b"\x16":  # saludo TLS (ClientHello)
                try:
                    secure = self.tls.wrap_socket(request, server_side=True)
                except (ssl.SSLError, OSError):
                    return

            (secure or request).settimeout(None)

        try:
            self.RequestHandlerClass(secure or request, client_address, self)
        finally:
            if secure:
                try:
                    secure.close()
                except OSError:
                    pass


server = PanelServer((BIND, PORT), Handler)

# Con certificado el panel habla HTTPS (los navegadores lo exigen, por
# ejemplo, para las notificaciones). Ver sysadmin/localca.py.
if core.tls_enabled():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(core.TLS_CERT, core.TLS_KEY)
    server.tls = context

print("MCServer panel escuchando en %s://%s:%d" % ("https" if core.tls_enabled() else "http", BIND, PORT), flush=True)
server.serve_forever()
