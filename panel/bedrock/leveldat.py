#
# MCServer by Derpchees - level.dat de Bedrock (NBT little-endian)
#
# Formato: 4 bytes de version + 4 bytes de largo + un compuesto NBT sin
# nombre. Se lee y se vuelve a escribir igual (tipos y orden), sin
# librerias. Cada etiqueta es (tipo, valor); un compuesto es una lista de
# (nombre, etiqueta) para conservar el orden.
#

import os
import struct

END, BYTE, SHORT, INT, LONG, FLOAT, DOUBLE, BYTES, STRING, LIST, COMPOUND, INTS, LONGS = range(13)

SCALAR = {BYTE: "<b", SHORT: "<h", INT: "<i", LONG: "<q", FLOAT: "<f", DOUBLE: "<d"}


class Reader:

    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos

    def take(self, size):
        chunk = self.data[self.pos:self.pos + size]

        if len(chunk) != size:
            raise ValueError("level.dat incompleto")

        self.pos += size
        return chunk

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def string(self):
        return self.take(self.unpack("<H")).decode("utf-8", "replace")

    def payload(self, kind):
        if kind in SCALAR:
            return self.unpack(SCALAR[kind])
        if kind == STRING:
            return self.string()
        if kind == BYTES:
            return self.take(self.unpack("<i"))
        if kind == INTS:
            return [self.unpack("<i") for _ in range(self.unpack("<i"))]
        if kind == LONGS:
            return [self.unpack("<q") for _ in range(self.unpack("<i"))]
        if kind == LIST:
            inner = self.unpack("<b")
            return inner, [self.payload(inner) for _ in range(self.unpack("<i"))]
        if kind == COMPOUND:
            items = []

            while True:
                tag = self.unpack("<b")

                if tag == END:
                    return items

                name = self.string()
                items.append((name, (tag, self.payload(tag))))

        raise ValueError("Etiqueta NBT desconocida: %d" % kind)


def pack_string(text):
    data = text.encode("utf-8")
    return struct.pack("<H", len(data)) + data


def pack(kind, value):
    if kind in SCALAR:
        return struct.pack(SCALAR[kind], value)
    if kind == STRING:
        return pack_string(value)
    if kind == BYTES:
        return struct.pack("<i", len(value)) + value
    if kind == INTS:
        return struct.pack("<i", len(value)) + b"".join(struct.pack("<i", v) for v in value)
    if kind == LONGS:
        return struct.pack("<i", len(value)) + b"".join(struct.pack("<q", v) for v in value)
    if kind == LIST:
        inner, items = value
        return struct.pack("<bi", inner, len(items)) + b"".join(pack(inner, v) for v in items)
    if kind == COMPOUND:
        out = b""

        for name, (tag, item) in value:
            out += struct.pack("<b", tag) + pack_string(name) + pack(tag, item)

        return out + struct.pack("<b", END)

    raise ValueError("Etiqueta NBT desconocida: %d" % kind)


def read(path):
    # (version, compuesto raiz)
    with open(path, "rb") as f:
        data = f.read()

    version, _ = struct.unpack("<ii", data[:8])
    reader = Reader(data, 8)

    if reader.unpack("<b") != COMPOUND:
        raise ValueError("level.dat no válido")

    reader.string()
    return version, reader.payload(COMPOUND)


def write(path, version, root):
    body = struct.pack("<b", COMPOUND) + pack_string("") + pack(COMPOUND, root)
    tmp = path + ".tmp-panel"

    with open(tmp, "wb") as f:
        f.write(struct.pack("<ii", version, len(body)) + body)

    os.replace(tmp, path)


def get(compound, name, default=None):
    for key, tag in compound:
        if key == name:
            return tag

    return default


def put(compound, name, tag):
    for i, (key, _) in enumerate(compound):
        if key == name:
            compound[i] = (name, tag)
            return

    compound.append((name, tag))
