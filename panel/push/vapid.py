#
# MCServer by Derpchees - Llave VAPID para Web Push
#
# Los servicios de push (Google, Mozilla, Apple, Microsoft) piden que cada
# aviso vaya firmado con ECDSA P-256 (ES256). Python no la trae y no se
# instalan librerias extra, asi que aqui va la curva hecha a mano: solo se
# firma un JWT corto de vez en cuando, la velocidad no importa.
#

import base64
import hashlib
import json
import secrets
import time

import mcpanel_core as core


# Curva P-256 (NIST, FIPS 186-4)
P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
A = P - 3
N = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
G = (0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296,
     0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5)

SETTING = "push_vapid_key"

# Quien manda los avisos (los servicios de push piden un contacto)
CONTACT = "https://github.com/Derpchees/mcserver"


def point_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1

    (x1, y1), (x2, y2) = p1, p2

    if x1 == x2 and (y1 + y2) % P == 0:
        return None

    if p1 == p2:
        slope = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        slope = (y2 - y1) * pow(x2 - x1, -1, P) % P

    x3 = (slope * slope - x1 - x2) % P
    return x3, (slope * (x1 - x3) - y1) % P


def point_mul(k, point=G):
    result = None

    while k:
        if k & 1:
            result = point_add(result, point)
        point = point_add(point, point)
        k >>= 1

    return result


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def private_key(create=False):
    # La llave se guarda en los ajustes; la crea el panel la primera vez
    value = core.get_setting(SETTING)

    if value:
        return int(value, 16)

    if not create:
        return None

    key = secrets.randbelow(N - 1) + 1
    core.set_setting(SETTING, "%064x" % key)
    return int(core.get_setting(SETTING), 16)


def public_key(key):
    # Punto sin comprimir (65 bytes), como lo pide PushManager.subscribe
    x, y = point_mul(key)
    return b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")


def sign(key, message):
    z = int.from_bytes(hashlib.sha256(message).digest(), "big")

    while True:
        k = secrets.randbelow(N - 1) + 1
        r = point_mul(k)[0] % N
        s = pow(k, -1, N) * (z + r * key) % N

        if r and s:
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def auth_header(key, audience):
    # Authorization: vapid t=<JWT>, k=<llave publica>
    header = b64url(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    claims = b64url(json.dumps({
        "aud": audience,
        "exp": int(time.time()) + 12 * 3600,
        "sub": CONTACT
    }).encode())

    unsigned = header + "." + claims
    token = unsigned + "." + b64url(sign(key, unsigned.encode("ascii")))

    return "vapid t=%s, k=%s" % (token, b64url(public_key(key)))
