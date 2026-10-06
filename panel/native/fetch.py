#
# MCServer by Derpchees - descargas (Java, servidores, mods)
#

import hashlib
import json
import os
import time
import urllib.request

# minecraft.net no contesta a nombres con una direccion web adentro
USER_AGENT = "MCServer-panel"


def open_url(url, timeout=60, headers=None, data=None):
    request = urllib.request.Request(url, data=data, headers=dict({"User-Agent": USER_AGENT}, **(headers or {})))
    return urllib.request.urlopen(request, timeout=timeout)


def get_json(url, headers=None, data=None, timeout=30):
    if data is not None:
        data = json.dumps(data).encode("utf-8")
        headers = dict(headers or {}, **{"Content-Type": "application/json"})

    with open_url(url, timeout, headers, data) as response:
        return json.loads(response.read())


def get_text(url, timeout=30):
    with open_url(url, timeout) as response:
        return response.read().decode("utf-8", "replace")


def download(url, dest, hashes=None, headers=None, attempts=3):
    # Baja a un archivo temporal y lo mueve al final: nunca deja uno a medias.
    # hashes: {"sha1": "...", "sha256": "...", "sha512": "..."} para comprobarlo
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    hashes = {k: v.lower() for k, v in (hashes or {}).items() if v}
    error = None

    for attempt in range(attempts):
        try:
            digests = {name: hashlib.new(name) for name in hashes}

            with open_url(url, 120, headers) as response, open(tmp, "wb") as f:
                while True:
                    chunk = response.read(1024 * 256)

                    if not chunk:
                        break

                    f.write(chunk)

                    for digest in digests.values():
                        digest.update(chunk)

            for name, digest in digests.items():
                if digest.hexdigest() != hashes[name]:
                    raise ValueError("el archivo descargado no coincide (%s)" % name)

            os.replace(tmp, dest)
            return dest
        except (OSError, ValueError) as err:
            error = err

            try:
                os.remove(tmp)
            except OSError:
                pass

            time.sleep(2 * (attempt + 1))

    raise RuntimeError("No se pudo descargar %s: %s" % (url.rsplit("/", 1)[-1][:80], error))
