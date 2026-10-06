#
# MCServer by Derpchees - Skins y caras de los jugadores
#
# Si el servidor usa un mod de skins propias (Quick Skin guarda las suyas
# en <mundo>/quickskin) se usa esa: es la que se ve dentro del juego. Si
# no, la oficial de Mojang, que el panel baja y guarda unas horas.
# mc-heads.net queda solo de respaldo: su cache a veces da a Steve.
#
# Bedrock no publica las skins: se usa la que GeyserMC tenga guardada de
# ese jugador (si alguna vez entro a un servidor con Geyser) y, si no, el
# personaje clasico (Steve o Alex, siempre el mismo para cada jugador).
# La cara se recorta aqui (capa de la cara + capa del casco), sin
# librerias de imagen.
#

import base64
import json
import os
import re
import struct
import threading
import time
import zlib

import mcpanel_core as core

from .common import fetch_url, read_json_file, read_lines


PLAYER_NAME = re.compile(r"^\w{1,16}$")
MOJANG_HEAD = "https://mc-heads.net/avatar/%s/%d"
MOJANG_SKIN = "https://mc-heads.net/skin/%s"


def level_dir(srv):
    name = "world"

    for line in read_lines(os.path.join(srv.data_dir, "server.properties")):
        if line.startswith("level-name="):
            name = line.split("=", 1)[1].strip() or "world"

    return os.path.join(srv.data_dir, name.replace("/", "_"))


def custom_skin(srv, name):
    # Ruta del PNG de la skin propia del jugador, o None
    if not PLAYER_NAME.match(name or ""):
        return None

    base = os.path.join(level_dir(srv), "quickskin")

    if not os.path.isdir(base):
        return None

    # El mismo nombre puede tener varios UUID (modo online y offline)
    for item in read_json_file(os.path.join(srv.data_dir, "usercache.json"), []):
        if str(item.get("name", "")).lower() != name.lower():
            continue

        uuid = str(item.get("uuid", ""))

        if not re.match(r"^[0-9a-f-]{32,36}$", uuid):
            continue

        appearance = read_json_file(os.path.join(base, "appearances", uuid + ".json"), {})
        skin = str(appearance.get("skinId", ""))

        if skin.startswith("local_skin:") and re.match(r"^[0-9a-f]{8,64}$", skin[11:]):
            path = os.path.join(base, "textures", skin[11:] + ".png")

            if os.path.isfile(path) and os.path.getsize(path) < 1024 * 1024:
                return path

    return None


# ------------------------------------------------------------
# Skin oficial de Mojang (guardada 6 horas; sin skin propia = Steve/Alex)

SKIN_TTL = 6 * 3600
_mojang_lock = threading.Lock()


def mojang_uuid(srv, name):
    # Del cache de jugadores del servidor (cuenta oficial: UUID version 4)
    for item in read_json_file(os.path.join(srv.data_dir, "usercache.json"), []):
        uuid = str(item.get("uuid", "")).replace("-", "")

        if str(item.get("name", "")).lower() == name.lower() and len(uuid) == 32 and uuid[12] == "4":
            return uuid

    data = json.loads(fetch_url("https://api.mojang.com/users/profiles/minecraft/" + name, timeout=8))
    return str(data.get("id", "")) or None


def mojang_skin(srv, name):
    folder = os.path.join(core.STATE_ROOT, "skins")
    path = os.path.join(folder, name.lower() + ".png")
    missing = path + ".none"

    with _mojang_lock:
        for candidate, ok in ((path, True), (missing, False)):
            try:
                if time.time() - os.path.getmtime(candidate) < SKIN_TTL:
                    return candidate if ok else None
            except OSError:
                pass

        try:
            uuid = mojang_uuid(srv, name)
            profile = json.loads(fetch_url("https://sessionserver.mojang.com/session/minecraft/profile/" + uuid, timeout=8))
            value = next(p["value"] for p in profile.get("properties", []) if p.get("name") == "textures")
            url = json.loads(base64.b64decode(value))["textures"]["SKIN"]["url"]

            if not re.match(r"^https?://textures\.minecraft\.net/texture/[0-9a-f]+$", url):
                raise ValueError("url")

            data = fetch_url(url.replace("http://", "https://"), timeout=8)
        except Exception:
            # Sin cuenta, sin skin propia o sin internet: se vuelve a probar luego
            os.makedirs(folder, exist_ok=True)
            open(missing, "w").close()
            return None

        os.makedirs(folder, exist_ok=True)

        with open(path + ".tmp", "wb") as f:
            f.write(data[:1024 * 1024])

        os.replace(path + ".tmp", path)
        return path


# ------------------------------------------------------------
# Bedrock: skin guardada por GeyserMC (por XUID) o el personaje clasico

GEYSER_SKIN = "https://api.geysermc.org/v2/skin/%s"
DEFAULT_SKINS = {
    "steve": "https://textures.minecraft.net/texture/1a4af718455d4aab528e7a61f86fa25e6a369d1768dcb13f7df319a713eb810b",
    "alex": "https://textures.minecraft.net/texture/3b60a1f6d562f52aaebbf1434f1de147933a3affe0e764fa49ea057536623cd3"
}


def cached_download(path, producer):
    # Guarda lo descargado unas horas; si no hay, lo recuerda tambien
    missing = path + ".none"

    with _mojang_lock:
        for candidate, ok in ((path, True), (missing, False)):
            try:
                if time.time() - os.path.getmtime(candidate) < SKIN_TTL:
                    return candidate if ok else None
            except OSError:
                pass

        os.makedirs(os.path.dirname(path), exist_ok=True)

        try:
            data = producer()
        except Exception:
            data = None

        if not data:
            open(missing, "w").close()
            return None

        with open(path + ".tmp", "wb") as f:
            f.write(data[:1024 * 1024])

        os.replace(path + ".tmp", path)
        return path


def bedrock_xuid(srv, name):
    # Los nombres que el panel vio en el log (xuid -> nombre)
    names = read_json_file(os.path.join(srv.state_dir, "bedrock-players.json"), {})
    return next((xuid for xuid, known in names.items() if known.lower() == name.lower() and xuid.isdigit()), None)


def geyser_skin(xuid):
    def producer():
        data = json.loads(fetch_url(GEYSER_SKIN % xuid, timeout=8))
        texture = str(data.get("texture_id", ""))

        if not re.match(r"^[0-9a-f]{20,80}$", texture):
            return None

        return fetch_url("https://textures.minecraft.net/texture/" + texture, timeout=8)

    return cached_download(os.path.join(core.STATE_ROOT, "skins", "bedrock-%s.png" % xuid), producer)


def default_skin(name):
    # Como Minecraft con las cuentas sin skin: Steve o Alex segun el jugador
    kind = "alex" if sum(name.lower().encode("utf-8")) % 2 else "steve"
    return cached_download(os.path.join(core.STATE_ROOT, "skins", "default-%s.png" % kind),
                           lambda: fetch_url(DEFAULT_SKINS[kind], timeout=8))


def bedrock_skin(srv, name):
    xuid = bedrock_xuid(srv, name)
    return (geyser_skin(xuid) if xuid else None) or default_skin(name)


def skin_path(srv, name):
    if core.is_bedrock(srv):
        return bedrock_skin(srv, name)

    return custom_skin(srv, name) or mojang_skin(srv, name)


# ------------------------------------------------------------
# PNG minimo (8 bits, RGB o RGBA, sin entrelazado: lo que usan las skins)

def read_png(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("no es PNG")

    pos = 8
    idat = b""
    width = height = color = None

    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length

        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", chunk)

            if depth != 8 or color not in (2, 6) or interlace:
                raise ValueError("formato no soportado")
        elif kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break

    bpp = 4 if color == 6 else 3
    raw = zlib.decompress(idat)
    stride = width * bpp
    rows = []
    prev = bytearray(stride)
    i = 0

    for _ in range(height):
        kind = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride

        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0

            if kind == 1:
                line[x] = (line[x] + a) & 255
            elif kind == 2:
                line[x] = (line[x] + b) & 255
            elif kind == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255

        rows.append([tuple(line[x:x + bpp]) + ((255,) if bpp == 3 else ()) for x in range(0, stride, bpp)])
        prev = line

    return width, height, rows


def write_png(size, pixels):
    rows = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in pixels)

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9))
            + chunk(b"IEND", b""))


def head_png(path, size):
    # Cara (8,8) con el casco (40,8) encima, escalada sin suavizar
    with open(path, "rb") as f:
        width, _, rows = read_png(f.read())

    scale = width // 64 or 1
    face = []

    for y in range(8):
        line = []

        for x in range(8):
            px = rows[(8 + y) * scale][(8 + x) * scale]
            hat = rows[(8 + y) * scale][(40 + x) * scale]
            line.append(hat if hat[3] > 0 else px[:3] + (255,))

        face.append(line)

    return write_png(size, [[face[y * 8 // size][x * 8 // size] for x in range(size)] for y in range(size)])


def player_head(srv, name, size):
    # (png, None) con la cara propia, o (None, url de mc-heads.net)
    size = max(8, min(int(size), 256))
    path = skin_path(srv, name)

    if path:
        try:
            return head_png(path, size), None
        except (ValueError, OSError, zlib.error, struct.error, IndexError):
            pass

    return None, MOJANG_HEAD % (name, size)


def player_skin(srv, name):
    path = skin_path(srv, name)

    if path:
        with open(path, "rb") as f:
            return f.read(), None

    return None, MOJANG_SKIN % name
