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

server = ThreadingHTTPServer((BIND, PORT), Handler)

# Con certificado el panel habla HTTPS (los navegadores lo exigen, por
# ejemplo, para las notificaciones). El saludo TLS se hace en el hilo de
# cada conexion, no en el que acepta, para que un cliente lento no frene a
# los demas.
if core.tls_enabled():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(core.TLS_CERT, core.TLS_KEY)
    server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)

print("MCServer panel escuchando en %s://%s:%d" % ("https" if core.tls_enabled() else "http", BIND, PORT), flush=True)
server.serve_forever()
