#
# MCServer by Derpchees - paquetes de Bedrock (.mcaddon, .mcpack, .zip)
#
# Un add-on son uno o varios paquetes: de comportamiento (behavior_packs)
# y de recursos (resource_packs). Cada paquete es una carpeta con su
# manifest.json (uuid, version, nombre y modulos). Un .mcaddon es un zip
# con varios .mcpack (otros zips) o con las carpetas directamente.
#

import io
import json
import os
import re
import shutil
import zipfile


MAX_TOTAL = 1024 ** 3          # 1 GB descomprimido por archivo subido
MAX_NESTED = 300 * 1024 ** 2   # cada .mcpack dentro de un .mcaddon
MAX_FILES = 30000
NESTED = (".mcpack", ".mcaddon", ".zip")

# Carpetas de Mojang: la imagen de Bedrock las reemplaza al actualizar
MOJANG_PREFIXES = ("vanilla", "chemistry", "experimental", "editor")

KIND_FOLDER = {"behavior": "behavior_packs", "resource": "resource_packs"}


class PackError(Exception):
    pass


def strip_comments(text):
    # Algunos manifest traen comentarios // o /* */ (fuera de las cadenas)
    out = []
    i = 0
    in_string = False

    while i < len(text):
        ch = text[i]

        if in_string:
            out.append(ch)

            if ch == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 1
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            out.append(ch)
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        else:
            out.append(ch)

        i += 1

    # Comas sobrantes antes de } o ]
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def parse_json(data):
    text = data.decode("utf-8-sig", "replace")

    try:
        return json.loads(text)
    except ValueError:
        return json.loads(strip_comments(text))


def lang_text(files, key, read):
    # "pack.name" -> texto de texts/en_US.lang (o el primero que haya)
    names = [n for n in files if n.lower().endswith(".lang") and "/texts/" in "/" + n.lower()]
    names.sort(key=lambda n: (not n.lower().endswith("en_us.lang"), not n.lower().endswith("es_mx.lang"), n))

    for name in names[:3]:
        try:
            for line in read(name).decode("utf-8-sig", "replace").splitlines():
                k, _, v = line.partition("=")

                if k.strip() == key:
                    return v.split("\t#")[0].strip()
        except (KeyError, OSError):
            continue

    return key


def pack_kind(manifest):
    types = {str((m or {}).get("type", "")).lower() for m in manifest.get("modules") or []}

    if types & {"data", "script", "javascript", "client_data"}:
        return "behavior"

    if "resources" in types:
        return "resource"

    if "skin_pack" in types:
        return "skin"

    if "world_template" in types:
        return "world"

    return None


def needs_beta(manifest):
    # Usa las API de scripts en beta: el mundo necesita "Beta APIs" activado
    for dep in manifest.get("dependencies") or []:
        if str((dep or {}).get("module_name", "")).startswith("@minecraft/") \
                and "beta" in str(dep.get("version", "")).lower():
            return True

    return False


def version_text(version):
    if isinstance(version, list):
        return ".".join(str(v) for v in version)

    return str(version or "")


class Pack:
    # Un paquete encontrado dentro de un archivo

    def __init__(self, manifest, prefix, files, read):
        header = manifest.get("header") or {}
        self.manifest = manifest
        self.prefix = prefix
        self.files = files
        self.read = read
        self.uuid = str(header.get("uuid", "")).lower()
        self.version = header.get("version") or [1, 0, 0]
        self.kind = pack_kind(manifest)
        self.beta = needs_beta(manifest)

        name = str(header.get("name") or "")
        description = str(header.get("description") or "")

        if "." in name and " " not in name:
            name = lang_text(files, name, read)

        if "." in description and " " not in description:
            description = lang_text(files, description, read)

        self.name = clean_text(name)[:80] or self.uuid[:8]
        self.description = clean_text(description)[:300]

    def info(self):
        return {"uuid": self.uuid, "version": self.version, "version_text": version_text(self.version),
                "kind": self.kind, "name": self.name, "description": self.description, "beta": self.beta}


def clean_text(text):
    # Quita los codigos de color de Minecraft (seccion + caracter)
    return re.sub(r"§.", "", re.sub(r"[\x00-\x1f\x7f]", " ", text)).strip()


def find_packs(source, depth=0, budget=None):
    # Paquetes dentro de un zip (ruta o bytes). Los .mcpack internos se abren tambien.
    budget = budget if budget is not None else {"bytes": 0, "files": 0}

    try:
        archive = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError):
        raise PackError("El archivo no es un add-on válido (.mcaddon, .mcpack o .zip)")

    infos = [i for i in archive.infolist() if not i.is_dir()]
    budget["files"] += len(infos)
    budget["bytes"] += sum(i.file_size for i in infos)

    if budget["files"] > MAX_FILES or budget["bytes"] > MAX_TOTAL:
        raise PackError("El add-on es demasiado grande")

    names = [i.filename.replace("\\", "/") for i in infos]
    real = {i.filename.replace("\\", "/"): i.filename for i in infos}

    def read(name):
        return archive.read(real[name])

    prefixes = sorted({n[:-len("manifest.json")] for n in names
                       if n.lower().endswith("manifest.json") and (n == "manifest.json" or n.lower().endswith("/manifest.json"))
                       and "/subpacks/" not in "/" + n.lower()}, key=len, reverse=True)
    packs = []
    taken = set()

    for prefix in prefixes:
        files = [n for n in names if n.startswith(prefix) and n not in taken]
        taken.update(files)

        try:
            manifest = parse_json(read(prefix + "manifest.json"))
        except (ValueError, KeyError):
            continue

        if not isinstance(manifest, dict) or not (manifest.get("header") or {}).get("uuid"):
            continue

        packs.append(Pack(manifest, prefix, files, read))

    # .mcpack dentro de un .mcaddon
    if depth < 2:
        for info in infos:
            name = info.filename.replace("\\", "/")

            if name in taken or not name.lower().endswith(NESTED):
                continue

            if info.file_size > MAX_NESTED:
                raise PackError("El add-on es demasiado grande")

            packs += find_packs(io.BytesIO(archive.read(info.filename)), depth + 1, budget)

    return packs


def safe_name(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:32] or "pack"


def is_mojang(folder):
    return folder.lower().startswith(MOJANG_PREFIXES)


def extract(pack, data_dir, uid, gid):
    # Copia el paquete a behavior_packs/ o resource_packs/ y devuelve la carpeta
    if pack.kind not in KIND_FOLDER:
        raise PackError("Este paquete no se puede usar en un servidor (skins o plantillas de mundo)")

    root = os.path.join(data_dir, KIND_FOLDER[pack.kind])
    folder = "mcp_%s_%s" % (safe_name(pack.name), re.sub(r"[^a-f0-9]", "", pack.uuid)[:8])
    target = os.path.join(root, folder)
    tmp = target + ".tmp-panel"

    os.makedirs(root, exist_ok=True)
    shutil.rmtree(tmp, ignore_errors=True)

    try:
        for name in pack.files:
            rel = name[len(pack.prefix):]
            parts = [p for p in rel.split("/") if p not in ("", ".")]

            if not parts or ".." in parts or os.path.isabs(rel):
                continue

            dest = os.path.join(tmp, *parts)
            os.makedirs(os.path.dirname(dest), exist_ok=True)

            with open(dest, "wb") as f:
                f.write(pack.read(name))

        for base, dirs, files in os.walk(tmp):
            for item in dirs + files:
                try:
                    os.chown(os.path.join(base, item), uid, gid)
                except OSError:
                    pass

        try:
            os.chown(tmp, uid, gid)
        except OSError:
            pass

        shutil.rmtree(target, ignore_errors=True)
        os.replace(tmp, target)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return folder


def read_manifest(folder):
    try:
        with open(os.path.join(folder, "manifest.json"), "rb") as f:
            manifest = parse_json(f.read())
    except (OSError, ValueError):
        return None

    if not isinstance(manifest, dict) or not (manifest.get("header") or {}).get("uuid"):
        return None

    files = []

    texts = os.path.join(folder, "texts")

    if os.path.isdir(texts):
        files = ["texts/" + n for n in os.listdir(texts)]

    def read(name):
        with open(os.path.join(folder, *name.split("/")), "rb") as f:
            return f.read()

    return Pack(manifest, "", files, read)
