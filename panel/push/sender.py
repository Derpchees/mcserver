#
# MCServer by Derpchees - Envio de los avisos push (corre en el agente)
#
# Cada pocos segundos revisa si hay eventos nuevos para cada dispositivo
# suscrito y le manda un aviso vacio; el service worker del navegador
# pide los eventos y muestra la notificacion (ver web/sw.js).
#

import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import mcpanel_core as core

from . import kinds, store, vapid


INTERVAL = 5


def send(key, endpoint):
    # Devuelve False si el dispositivo ya no existe (se borra)
    parts = urllib.parse.urlsplit(endpoint)
    request = urllib.request.Request(endpoint, data=b"", method="POST", headers={
        "Authorization": vapid.auth_header(key, "%s://%s" % (parts.scheme, parts.netloc)),
        "TTL": "86400",
        "Urgency": "high"
    })

    try:
        urllib.request.urlopen(request, timeout=10).close()
    except urllib.error.HTTPError as error:
        if error.code in (404, 410):
            return False
        print("push: %s %s" % (error.code, parts.netloc), file=sys.stderr, flush=True)
    except OSError as error:
        print("push: %s %s" % (parts.netloc, error), file=sys.stderr, flush=True)

    return True


def check(sent):
    # sent: ultimo evento avisado a cada dispositivo (para no repetir el aviso
    # si el dispositivo todavia no paso a recogerlo)
    last = core.last_event_id()

    if last <= sent.get("_last", 0):
        return

    key = vapid.private_key()

    if key is None:
        sent["_last"] = last
        return

    for sub in store.all_subs():
        # Solo se avisa si hay algo de los temas que la cuenta quiere; si todo
        # lo nuevo esta silenciado se da por entregado (no se acumula)
        pending = store.pending(sub)
        events = kinds.wanted(pending, kinds.muted_of(sub))

        if pending and not events:
            store.advance(sub, pending[-1]["id"])
            continue

        if not events or events[-1]["id"] <= sent.get(sub["id"], 0):
            continue

        sent[sub["id"]] = events[-1]["id"]

        if not send(key, sub["endpoint"]):
            store.unsubscribe(sub["endpoint"])

    sent["_last"] = last


def loop():
    sent = {"_last": core.last_event_id()}

    while True:
        time.sleep(INTERVAL)

        try:
            check(sent)
        except Exception as error:
            print("push:", error, file=sys.stderr, flush=True)
