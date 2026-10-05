#
# MCServer by Derpchees - Sesiones
#
# Cada inicio de sesion es un token al azar que va en una cookie HttpOnly.
# En la base solo se guarda su hash (SHA-256): quien lea la base no puede
# usar las sesiones. Sobreviven a los reinicios del panel.
#
#   - "Mantener la sesion iniciada": 30 dias, que se renuevan con el uso
#   - sin marcarla: la cookie dura hasta cerrar el navegador (maximo 12 h)
#

import hashlib
import re
import secrets
import threading
import time

import mcpanel_core as core

SESSION_COOKIE = "mcpanel"
SHORT_SECONDS = 12 * 3600
REMEMBER_SECONDS = 30 * 86400

# Cada cuanto se anota el ultimo uso (y se renueva una sesion recordada)
TOUCH_SECONDS = 300

_lock = threading.Lock()


def token_id(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id, remember=False, ip="", agent=""):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    life = REMEMBER_SECONDS if remember else SHORT_SECONDS

    with _lock:
        core.execute("DELETE FROM sessions WHERE expires < ?", (now,))
        core.execute(
            "INSERT INTO sessions (id, user_id, created, expires, last_seen, remember, ip, agent) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (token_id(token), user_id, now, now + life, now, 1 if remember else 0,
             str(ip)[:64], str(agent)[:300])
        )

    return token


def cookie_header(token, remember):
    # Sin Max-Age la cookie se borra al cerrar el navegador
    age = "; Max-Age=%d" % REMEMBER_SECONDS if remember else ""
    # Con HTTPS la cookie nunca viaja sin cifrar
    secure = "; Secure" if core.tls_enabled() else ""
    return {"Set-Cookie": "%s=%s; Path=/%s; HttpOnly; SameSite=Strict%s" % (SESSION_COOKIE, token, age, secure)}


def clear_cookie_header():
    return {"Set-Cookie": SESSION_COOKIE + "=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"}


def session_user(token, ip=""):
    if not token:
        return None

    sid = token_id(token)
    row = core.query("SELECT * FROM sessions WHERE id = ?", (sid,), one=True)
    now = int(time.time())

    if not row or row["expires"] < now:
        if row:
            core.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        return None

    user = core.get_user(row["user_id"])

    if not user:
        core.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        return None

    if now - row["last_seen"] > TOUCH_SECONDS:
        expires = now + REMEMBER_SECONDS if row["remember"] else row["expires"]
        core.execute("UPDATE sessions SET last_seen = ?, expires = ?, ip = ? WHERE id = ?",
                     (now, expires, str(ip)[:64] or row["ip"], sid))

    return user


def end_session(token):
    if token:
        core.execute("DELETE FROM sessions WHERE id = ?", (token_id(token),))


def end_user_sessions(user_id, keep_token=None):
    # Cierra todas las sesiones de un usuario (menos la actual, si se indica)
    if keep_token:
        core.execute("DELETE FROM sessions WHERE user_id = ? AND id != ?", (user_id, token_id(keep_token)))
    else:
        core.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def device_name(agent):
    # Un nombre corto y reconocible a partir del User-Agent
    agent = agent or ""
    browser = next((name for pattern, name in (
        (r"Edg/", "Edge"), (r"OPR/|Opera", "Opera"), (r"Firefox/", "Firefox"),
        (r"Chrome/", "Chrome"), (r"Safari/", "Safari")) if re.search(pattern, agent)), "")
    system = next((name for pattern, name in (
        (r"Android", "Android"), (r"iPhone|iPad", "iOS"), (r"Windows", "Windows"),
        (r"Mac OS X|Macintosh", "macOS"), (r"Linux", "Linux")) if re.search(pattern, agent)), "")

    return " · ".join(x for x in (browser, system) if x) or (agent[:40] if agent else "")


def list_sessions(user_id, current_token):
    current = token_id(current_token) if current_token else ""
    rows = core.query("SELECT * FROM sessions WHERE user_id = ? AND expires >= ? ORDER BY last_seen DESC",
                      (user_id, int(time.time())))

    return [{
        "id": row["id"][:16],
        "current": row["id"] == current,
        "device": device_name(row["agent"]),
        "ip": row["ip"],
        "created": row["created"],
        "last_seen": row["last_seen"],
        "expires": row["expires"],
        "remember": bool(row["remember"])
    } for row in rows]


def end_session_by_id(user_id, short_id):
    # El panel solo conoce los primeros caracteres del hash, no el token
    if not re.match(r"^[0-9a-f]{16}$", short_id or ""):
        return False

    for row in core.query("SELECT id FROM sessions WHERE user_id = ?", (user_id,)):
        if row["id"].startswith(short_id):
            core.execute("DELETE FROM sessions WHERE id = ?", (row["id"],))
            return True

    return False
