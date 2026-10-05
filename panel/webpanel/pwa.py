#
# MCServer by Derpchees - Panel instalable como app (PC y celular)
#
# Manifiesto, iconos PNG del bloque de pasto (los mismos pixeles que el
# favicon) y el service worker. Los PNG se dibujan aqui con zlib, sin
# archivos binarios en el repositorio ni librerias de imagen.
#

import json
import os
import struct
import zlib

import mcpanel_core as core

from .webassets import WEB_DIR, WEB_DEV


# Bloque de pasto en 16x16, de abajo hacia arriba (cada capa tapa a la anterior)
DIRT = "#8a5a3b"
LAYERS = [
    ("#7a4e33", [(2, 8, 2, 2), (9, 9, 2, 2), (5, 12, 2, 2), (12, 12, 2, 2), (7, 7, 1, 1)]),
    ("#936240", [(11, 7, 2, 1), (3, 11, 1, 1), (9, 13, 2, 1)]),
    ("#5fbf3f", [(0, 0, 16, 6)]),
    ("#4ea634", [(0, 5, 3, 2), (6, 5, 2, 3), (11, 5, 3, 2), (4, 2, 2, 2), (10, 1, 2, 2)]),
    ("#62c444", [(8, 2, 2, 2), (1, 3, 2, 1), (13, 3, 2, 1)]),
]

# Fondo de la app al abrirse (el mismo del tema oscuro)
APP_BACKGROUND = "#0a0d0b"


def rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def block_grid():
    grid = [[rgb(DIRT)] * 16 for _ in range(16)]

    for color, rects in LAYERS:
        for x, y, w, h in rects:
            for row in range(y, y + h):
                for col in range(x, x + w):
                    grid[row][col] = rgb(color)

    return grid


def corner_alpha(px, py, size, radius):
    # Cobertura (0..255) de la esquina redondeada, con 4x4 muestras por pixel
    if radius <= 0:
        return 255

    inside = 0

    for sy in range(4):
        for sx in range(4):
            x = px + (sx + 0.5) / 4
            y = py + (sy + 0.5) / 4
            cx = min(max(x, radius), size - radius)
            cy = min(max(y, radius), size - radius)

            if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                inside += 1

    return inside * 255 // 16


def draw(size, rounded=True, badge=False):
    # badge: silueta blanca (Android solo usa la transparencia del icono pequeno)
    grid = block_grid()
    radius = size * 3 / 16 if rounded else 0
    rows = []

    for py in range(size):
        row = bytearray([0])
        gy = py * 16 // size

        for px in range(size):
            near = radius and (min(px, size - 1 - px) < radius and min(py, size - 1 - py) < radius)
            alpha = corner_alpha(px, py, size, radius) if near else 255

            if badge:
                # Una franja libre separa el pasto de la tierra
                if 6 * size // 16 <= py < 7 * size // 16:
                    alpha = 0
                row += bytes((255, 255, 255, alpha))
            else:
                row += bytes(grid[gy][px * 16 // size]) + bytes((alpha,))

        rows.append(bytes(row))

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + chunk(b"IEND", b""))


# Nombre publicado -> (tamano, esquinas redondas, silueta)
ICONS = {
    "icon-192.png": (192, True, False),
    "icon-512.png": (512, True, False),
    # "maskable": Android recorta su propia forma, asi que va completo
    "maskable-512.png": (512, False, False),
    # iOS redondea solo y pinta de negro lo transparente
    "apple-touch-icon.png": (180, False, False),
    "badge-96.png": (96, True, True),
}

_icons = {}


def icon(name):
    if name not in ICONS:
        return None

    if name not in _icons:
        _icons[name] = draw(*ICONS[name])

    return _icons[name]


def manifest():
    name = core.SYSTEM_NAME

    return json.dumps({
        "id": "/",
        "name": name,
        "short_name": name if len(name) <= 12 else "MCServer",
        "description": "Minecraft",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": APP_BACKGROUND,
        "theme_color": APP_BACKGROUND,
        "icons": [
            {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ]
    }, ensure_ascii=False).encode("utf-8")


_worker = None


def service_worker():
    global _worker

    if _worker is None or WEB_DEV:
        with open(os.path.join(WEB_DIR, "sw.js"), "rb") as f:
            _worker = f.read()

    return _worker
