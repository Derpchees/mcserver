#
# MCServer by Derpchees - server.properties sin Docker
#
# En Docker la imagen escribe los ajustes de red; en Windows los pone el
# panel antes de cada arranque. Solo cambia las claves pedidas y conserva
# lo demas (comentarios incluidos).
#

import os


def update(path, values):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []

    pending = {key: str(value) for key, value in values.items()}

    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") or "=" not in line:
            continue

        key = line.split("=", 1)[0].strip()

        if key in pending:
            lines[i] = "%s=%s" % (key, pending.pop(key))

    lines += ["%s=%s" % (key, value) for key, value in pending.items()]
    tmp = path + ".tmp-panel"

    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    os.replace(tmp, path)


def read(path):
    values = {}

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.lstrip().startswith("#") or "=" not in line:
                    continue

                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    except FileNotFoundError:
        pass

    return values
