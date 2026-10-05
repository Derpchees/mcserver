#
# MCServer by Derpchees - Rutas de las notificaciones push
#
#   GET  /push/key          llave publica VAPID (para PushManager.subscribe)
#   POST /push/subscribe    guarda el dispositivo y devuelve su token
#   POST /push/unsubscribe  lo quita
#   POST /push/events       el service worker recoge los eventos con su token
#   POST /me/notify         temas de avisos que la cuenta silencia
#

import mcpanel_core as core
from push import kinds, store, vapid

from .common import FileError


def push_key():
    return {"key": vapid.b64url(vapid.public_key(vapid.private_key(create=True)))}


def push_subscribe(user, data):
    token = store.subscribe(user, str(data.get("endpoint", "")))

    if not token:
        raise FileError("Este navegador usa un servicio de notificaciones desconocido")

    return {"ok": True, "token": token}


def push_unsubscribe(data):
    store.unsubscribe(str(data.get("endpoint", "")))
    return {"ok": True}


def set_notify_mute(user, data):
    value = kinds.clean(data.get("mute"))
    core.execute("UPDATE users SET notify_mute = ? WHERE id = ?", (value, user["id"]))
    return {"ok": True, "message": "Avisos guardados"}


def push_events(data):
    events = store.take_events(str(data.get("token", "")))

    if events is None:
        raise FileError("Dispositivo no registrado", 404)

    return {"events": events}
