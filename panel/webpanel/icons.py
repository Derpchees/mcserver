#
# MCServer by Derpchees - Icono de cada servidor
#

import json
import os

from .common import give_to_server


# Bloques reales de Minecraft en el estilo del logo: bandas horizontales
# (filas de una cuadricula de 12) divididas en franjas verticales. El
# bloque de pasto normal no esta: es el icono del sistema.
ICON_GRID = 12
ICON_BLOCKS = json.loads(r'''[{"name":"Mycelium","bands":[[3,["#7b6e83","#6a5f75","#85788c","#71667a"]],[9,["#8a5a3b","#7a4e33","#936240"]]]},{"name":"Podzol","bands":[[3,["#7a5a2b","#6b4e24","#866331","#71532a"]],[9,["#8a5a3b","#7a4e33","#936240"]]]},{"name":"Snowy Grass Block","bands":[[3,["#f2f6f6","#e3eaea","#ffffff","#e9efef"]],[9,["#8a5a3b","#7a4e33","#936240"]]]},{"name":"Dirt Path","bands":[[3,["#9c8148","#8b733f","#a88b4f","#937944"]],[9,["#8a5a3b","#7a4e33","#936240"]]]},{"name":"Crimson Nylium","bands":[[3,["#a31f1f","#8e1a1a","#b32525","#961c1c"]],[9,["#6f2b2b","#5e2424","#7a3131"]]]},{"name":"Warped Nylium","bands":[[3,["#2b7f78","#236b65","#33908a","#28746e"]],[9,["#6f2b2b","#5e2424","#7a3131"]]]},{"name":"TNT","bands":[[4,["#c93a2b","#b53325","#d2422f","#bc3628"]],[4,["#e8e2d6","#d8d2c6","#f0ebe0"]],[4,["#c93a2b","#b53325","#d2422f","#bc3628"]]]},{"name":"Bookshelf","bands":[[2,["#a2834f","#8f7343","#ae8e57"]],[8,["#8b2e2e","#2e4a8b","#c9a33c","#6b3f8f"]],[2,["#a2834f","#8f7343","#ae8e57"]]]},{"name":"Oak Log","bands":[[12,["#6b5232","#5a4429","#745a37","#614a2d"]]]},{"name":"Birch Log","bands":[[12,["#d9d6c9","#e9e6da","#3e3a33","#dcd9cc"]]]},{"name":"Stone","bands":[[12,["#7f7f7f","#727272","#8a8a8a"]]]},{"name":"Cobblestone","bands":[[12,["#7a7a7a","#5f5f5f","#8c8c8c","#6a6a6a"]]]},{"name":"Deepslate","bands":[[12,["#4a4a50","#3e3e44","#55555b"]]]},{"name":"Sand","bands":[[12,["#dbcf9f","#d0c493","#e3d8aa"]]]},{"name":"Netherrack","bands":[[12,["#6f2b2b","#5e2424","#7a3131"]]]},{"name":"End Stone","bands":[[12,["#e8edb0","#dce2a3","#f0f4be"]]]},{"name":"Obsidian","bands":[[12,["#1c1426","#140e1c","#251b33"]]]},{"name":"Glowstone","bands":[[12,["#f2c76a","#d9a94f","#fbe39a"]]]},{"name":"Ice","bands":[[12,["#9ec2f7","#8db4ee","#b0cefa"]]]},{"name":"Pumpkin","bands":[[12,["#d9832b","#c27327","#e0912f","#ca7a28"]]]},{"name":"Block of Gold","bands":[[12,["#f9d849","#e8c238","#fce36a"]]]},{"name":"Block of Diamond","bands":[[12,["#5de1d9","#4ccbc3","#7aebe4"]]]},{"name":"Block of Copper","bands":[[12,["#c0694a","#ae5d41","#cb7655"]]]},{"name":"Block of Amethyst","bands":[[12,["#8b5fc4","#7a51b0","#9c70d3"]]]},{"name":"Honey Block","bands":[[12,["#f6b23c","#e8a132","#fbc257"]]]}]''')


def _icon_hash(text):
    h = 2166136261

    for ch in text:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF

    return h


def server_icon_block(slug):
    return ICON_BLOCKS[_icon_hash(slug or "server") % len(ICON_BLOCKS)]


def server_icon_pixels(slug):
    pixels = []

    for rows, colors in server_icon_block(slug)["bands"]:
        rgb = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in colors]

        for _ in range(rows):
            for x in range(ICON_GRID):
                pixels.append(rgb[x * len(rgb) // ICON_GRID])

    return pixels


def server_icon_png(slug, size=64):
    import struct
    import zlib

    pixels = server_icon_pixels(slug)
    rows = []

    for y in range(size):
        row = bytearray([0])

        for x in range(size):
            row.extend(pixels[(y * ICON_GRID // size) * ICON_GRID + (x * ICON_GRID // size)])

        rows.append(bytes(row))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + chunk(b"IEND", b""))


def write_server_icon(srv, overwrite=False):
    # Solo si no tiene uno: no se pisa un icono que el dueno haya subido
    path = os.path.join(srv.data_dir, "server-icon.png")

    if os.path.exists(path) and not overwrite:
        return False

    srv.ensure_dirs()

    with open(path + ".tmp", "wb") as f:
        f.write(server_icon_png(srv.slug))

    os.chmod(path + ".tmp", 0o664)
    give_to_server(path + ".tmp")
    os.replace(path + ".tmp", path)
    return True
