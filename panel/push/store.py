#
# MCServer by Derpchees - Dispositivos suscritos a las notificaciones push
#
# Cada navegador que activa los avisos guarda aqui su "endpoint" (la
# direccion del servicio de push) y un token propio. El aviso push va vacio:
# al recibirlo, el service worker pide los eventos con ese token, asi que
# ningun texto pasa por los servidores de Google, Mozilla o Apple.
#

import hashlib
import secrets
import time
import urllib.parse

import mcpanel_core as core

from . import kinds


# Solo se aceptan servicios de push conocidos: asi nadie puede hacer que el
# agente mande peticiones a otras direcciones
PUSH_HOSTS = (
    "fcm.googleapis.com", "android.googleapis.com", ".push.services.mozilla.com",
    ".push.apple.com", ".notify.windows.com"
)


def valid_endpoint(endpoint):
    parts = urllib.parse.urlsplit(endpoint)
    host = (parts.hostname or "").lower()

    return (parts.scheme == "https" and len(endpoint) <= 1024
            and any(host == h or (h.startswith(".") and host.endswith(h)) for h in PUSH_HOSTS))


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def subscribe(user, endpoint):
    # Devuelve el token que el service worker usa para pedir los eventos.
    # Si el dispositivo ya estaba (u otra cuenta lo uso), se reasigna.
    if not valid_endpoint(endpoint):
        return None

    token = secrets.token_urlsafe(32)
    core.execute(
        "INSERT INTO push_subs (user_id, endpoint, token, last_event, created) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(endpoint) DO UPDATE SET user_id = excluded.user_id, token = excluded.token, "
        "last_event = MAX(push_subs.last_event, excluded.last_event)",
        (user["id"], endpoint, token_hash(token), core.last_event_id(), int(time.time()))
    )
    return token


def unsubscribe(endpoint):
    core.execute("DELETE FROM push_subs WHERE endpoint = ?", (endpoint,))


def all_subs():
    return [dict(row) for row in core.query(
        "SELECT p.*, u.role, u.notify_mute FROM push_subs p JOIN users u ON u.id = p.user_id"
    )]


def visible_ids(sub):
    # Lo mismo que ve la campana: el admin todo, cada quien sus servidores
    if sub["role"] == "admin":
        return [s.id for s in core.list_servers()], True

    return [s.id for s in core.servers_of(sub["user_id"])], False


def pending(sub):
    # Todos los eventos nuevos que la cuenta puede ver (tambien los silenciados)
    ids, include_system = visible_ids(sub)
    return core.events_since(sub["last_event"], ids, include_system)


def advance(sub, last_id):
    core.execute("UPDATE push_subs SET last_event = ? WHERE id = ? AND last_event < ?",
                 (last_id, sub["id"], last_id))


def take_events(token):
    # Eventos nuevos del dispositivo con ese token (y se marcan como entregados)
    row = core.query("SELECT p.*, u.role, u.notify_mute FROM push_subs p JOIN users u ON u.id = p.user_id "
                     "WHERE p.token = ?", (token_hash(token or ""),), one=True)

    if not row:
        return None

    sub = dict(row)
    events = pending(sub)

    if events:
        advance(sub, events[-1]["id"])

    events = kinds.wanted(events, kinds.muted_of(sub))
    servers = {s.id: s for s in core.list_servers()}

    for event in events:
        srv = servers.get(event["server_id"])
        event["server"] = srv.name if srv else None
        event["server_slug"] = srv.slug if srv else None

    return events
