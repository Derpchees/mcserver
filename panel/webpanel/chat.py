#
# MCServer by Derpchees - Chat del servidor
#

import json
import os
import re
import time
import calendar
import threading
import glob
import gzip

import mcpanel_core as core
import runtime
from bedrock import console as bedrock_console

from .common import container_info, DEFAULT_LANG, S


CHAT_LIMIT = 3000

# Forge: [29Sep2026 00:40:42.324] [Server thread/INFO] [...]: mensaje
CHAT_LINE_FULL = re.compile(
    r"^\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2})\.\d+\] \[Server thread/INFO\] \[[^\]]*\]: (.*)$"
)

# Vanilla: [00:40:42] [Server thread/INFO]: mensaje (fecha sale del archivo)
CHAT_LINE_SHORT = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2})\] \[Server thread/INFO\](?: \[[^\]]*\])?: (.*)$"
)

CHAT_PATTERNS = [
    ("chat", re.compile(r"^(?:\[Not Secure\] )?<([^>]{1,32})> (.*)$")),
    ("say", re.compile(r"^(?:\[Not Secure\] )?\[(Server|Rcon)\] (.*)$")),
    ("join", re.compile(r"^(\w{1,16}) joined the game$")),
    ("leave", re.compile(r"^(\w{1,16}) left the game$")),
    ("advancement", re.compile(
        r"^(\w{1,16}) has (?:made the advancement|completed the challenge|reached the goal) \[(.+)\]$"
    ))
]

_chat_cache = {}
_chat_lock = threading.Lock()


def parse_chat_message(text):
    for kind, pattern in CHAT_PATTERNS:
        m = pattern.match(text)

        if m:
            groups = m.groups()
            return {
                "type": kind,
                "name": groups[0],
                "text": groups[1] if len(groups) > 1 else ""
            }

    return None


def parse_chat_file(path):
    # Los logs guardan la hora del contenedor, que esta en UTC
    name = os.path.basename(path)
    date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", name)

    if date_match:
        file_date = date_match.group(1)
    else:
        file_date = time.strftime("%Y-%m-%d", time.gmtime(os.path.getmtime(path)))

    opener = gzip.open if path.endswith(".gz") else open
    messages = []

    try:
        with opener(path, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")

                m = CHAT_LINE_FULL.match(line)

                if m:
                    try:
                        ts = calendar.timegm(time.strptime(m.group(1), "%d%b%Y %H:%M:%S"))
                    except ValueError:
                        continue
                else:
                    m = CHAT_LINE_SHORT.match(line)

                    if not m:
                        continue

                    try:
                        ts = calendar.timegm(
                            time.strptime(file_date + " " + m.group(1), "%Y-%m-%d %H:%M:%S")
                        )
                    except ValueError:
                        continue

                message = parse_chat_message(m.group(2))

                if message:
                    message["ts"] = ts
                    messages.append(message)
    except Exception:
        pass

    return messages


CHAT_MAX_CHARS = 240


def panel_chat_messages():
    # Mensajes enviados desde el panel: tellraw no queda en los logs
    # de Minecraft, asi que se guardan aqui para el historial
    messages = []

    try:
        with open(os.path.join(S().state_dir, "chat.jsonl"), "r", encoding="utf-8") as f:
            for line in f:
                try:
                    messages.append(json.loads(line))
                except ValueError:
                    continue
    except FileNotFoundError:
        pass

    return messages


_chat_senders = {}


def chat_rate_limited(ip):
    # Maximo 1 mensaje por segundo y 20 por minuto por IP
    now = time.time()

    with _chat_lock:
        recent = [x for x in _chat_senders.get(ip, []) if now - x < 60]

        if (recent and now - recent[-1] < 1) or len(recent) >= 20:
            _chat_senders[ip] = recent
            return True

        recent.append(now)
        _chat_senders[ip] = recent

        return False


CHAT_ROLES = {
    # Etiqueta y color en el juego segun quien escribe desde el panel
    "server": ("Server", "green"),
    "user": (None, "aqua"),
    "guest": (None, "gray")
}


def send_chat(text, role="server", username=None):
    # Quita saltos de linea y caracteres de control
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text or "").strip()[:CHAT_MAX_CHARS]

    if not text:
        return {"ok": False, "message": "Mensaje vacío"}

    running, _, _ = container_info()

    if running != "true":
        return {"ok": False, "message": "El servidor está apagado"}

    label, color = CHAT_ROLES.get(role, CHAT_ROLES["guest"])

    if role == "user":
        label = username or "?"
    elif role == "guest":
        label = "Invitado" if DEFAULT_LANG == "es" else "Guest"

    payload = json.dumps(
        ["", {"text": "[%s] " % label, "color": color}, {"text": text}],
        ensure_ascii=False
    )

    if core.is_bedrock(S()):
        sent, output = bedrock_console.tellraw(S(), "@a", text, label, color), ""
    else:
        sent, output = runtime.rcon(S(), ["tellraw", "@a", payload])

    if not sent:
        return {
            "ok": False,
            "message": "No se pudo enviar el mensaje",
            "output": output
        }

    os.makedirs(os.path.dirname(os.path.join(S().state_dir, "chat.jsonl")), exist_ok=True)

    with _chat_lock:
        with open(os.path.join(S().state_dir, "chat.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": int(time.time()),
                "type": "say",
                "name": label,
                "role": role,
                "text": text
            }, ensure_ascii=False) + "\n")

    return {"ok": True, "message": "Mensaje enviado"}


def chat_history():
    files = glob.glob(os.path.join(os.path.join(S().data_dir, "logs"), "*.log.gz"))
    latest = os.path.join(os.path.join(S().data_dir, "logs"), "latest.log")

    if os.path.exists(latest):
        files.append(latest)

    messages = []
    seen = set()

    with _chat_lock:
        for path in files:
            try:
                st = os.stat(path)
            except OSError:
                continue

            key = (st.st_mtime, st.st_size)
            cached = _chat_cache.get(path)

            if not cached or cached[0] != key:
                cached = (key, parse_chat_file(path))
                _chat_cache[path] = cached

            messages.extend(cached[1])

        for path in list(_chat_cache):
            if path not in files:
                del _chat_cache[path]

        messages.extend(panel_chat_messages())

    unique = []

    # latest.log puede repetirse en el .gz del mismo dia al rotar
    for message in sorted(messages, key=lambda x: x["ts"]):
        ident = (message["ts"], message["type"], message["name"], message["text"])

        if ident in seen:
            continue

        seen.add(ident)
        unique.append(message)

    return {
        "messages": unique[-CHAT_LIMIT:],
        "total": len(unique)
    }
