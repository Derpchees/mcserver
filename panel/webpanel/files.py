#
# MCServer by Derpchees - Gestor de archivos
#

import os
import shutil
import tempfile
import zipfile

from .common import FileError, give_to_server, S


MAX_EDIT_BYTES = 2 * 1024 * 1024

TEXT_EXTENSIONS = {
    ".txt", ".properties", ".json", ".json5", ".toml", ".yml", ".yaml",
    ".cfg", ".conf", ".ini", ".log", ".md", ".sh", ".bat", ".ps1",
    ".mcmeta", ".js", ".snbt", ".csv", ".xml", ".env", ".list"
}


def safe_path(relative, must_exist=True):
    root = os.path.realpath(S().data_dir)
    relative = (relative or "").replace("\\", "/").lstrip("/")
    full = os.path.realpath(os.path.join(root, relative))

    # realpath resuelve enlaces simbolicos y "..", asi que esto
    # impide salir de la carpeta del servidor
    if full != root and not full.startswith(root + os.sep):
        raise FileError("Ruta fuera de la carpeta del servidor", 403)

    if must_exist and not os.path.lexists(full):
        raise FileError("No existe: " + relative, 404)

    return full


def relative_path(full):
    rel = os.path.relpath(full, os.path.realpath(S().data_dir))
    return "" if rel == "." else rel.replace(os.sep, "/")


def valid_name(name):
    name = (name or "").strip()

    if not name or name in (".", "..") or "/" in name or "\\" in name or "\0" in name:
        raise FileError("Nombre no válido")

    if len(name.encode("utf-8")) > 255:
        raise FileError("Nombre demasiado largo")

    return name


def list_files(relative):
    full = safe_path(relative)

    if not os.path.isdir(full):
        raise FileError("No es una carpeta")

    entries = []

    with os.scandir(full) as it:
        for entry in it:
            try:
                st = entry.stat(follow_symlinks=False)
                is_dir = entry.is_dir(follow_symlinks=True)
            except OSError:
                continue

            entries.append({
                "name": entry.name,
                "dir": is_dir,
                "size": 0 if is_dir else st.st_size,
                "mtime": int(st.st_mtime),
                "link": entry.is_symlink()
            })

    entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))

    return {
        "path": relative_path(full),
        "entries": entries
    }


def read_text_file(relative):
    full = safe_path(relative)

    if not os.path.isfile(full):
        raise FileError("No es un archivo")

    if os.path.getsize(full) > MAX_EDIT_BYTES:
        raise FileError("El archivo es demasiado grande para editarlo aquí (máx. 2 MB)")

    with open(full, "rb") as f:
        raw = f.read()

    if b"\0" in raw:
        raise FileError("Es un archivo binario; descárgalo para verlo")

    return {
        "path": relative_path(full),
        "content": raw.decode("utf-8", errors="replace")
    }


def write_text_file(relative, content):
    full = safe_path(relative, must_exist=False)

    if os.path.isdir(full):
        raise FileError("Es una carpeta")

    data = content.encode("utf-8")

    if len(data) > MAX_EDIT_BYTES:
        raise FileError("Contenido demasiado grande")

    mode = os.stat(full).st_mode & 0o7777 if os.path.exists(full) else 0o664
    tmp = full + ".tmp-panel"

    with open(tmp, "wb") as f:
        f.write(data)

    os.chmod(tmp, mode)
    give_to_server(tmp)
    os.replace(tmp, full)

    return {"ok": True, "message": "Archivo guardado"}


def make_folder(relative, name):
    parent = safe_path(relative)
    target = safe_path(os.path.join(relative_path(parent), valid_name(name)), must_exist=False)

    if os.path.exists(target):
        raise FileError("Ya existe un elemento con ese nombre")

    os.mkdir(target, 0o775)
    give_to_server(target)

    return {"ok": True, "message": "Carpeta creada"}


def rename_item(relative, name):
    source = safe_path(relative)

    if source == os.path.realpath(S().data_dir):
        raise FileError("No se puede renombrar la carpeta raíz")

    target = os.path.join(os.path.dirname(source), valid_name(name))
    safe_path(relative_path(os.path.dirname(source)) + "/" + os.path.basename(target), must_exist=False)

    if os.path.lexists(target):
        raise FileError("Ya existe un elemento con ese nombre")

    os.rename(source, target)

    return {"ok": True, "message": "Renombrado"}


def delete_item(relative):
    full = safe_path(relative)

    if full == os.path.realpath(S().data_dir):
        raise FileError("No se puede borrar la carpeta raíz")

    if os.path.isdir(full) and not os.path.islink(full):
        shutil.rmtree(full)
    else:
        os.remove(full)

    return {"ok": True, "message": "Eliminado"}


def ensure_folder(relative):
    # Crea la carpeta (y las intermedias) si no existen; se usa al
    # soltar carpetas completas en el gestor
    folder = safe_path(relative, must_exist=False)
    root = os.path.realpath(S().data_dir)
    missing = []
    current = folder

    while current != root and not os.path.lexists(current):
        missing.append(current)
        current = os.path.dirname(current)

    for path in reversed(missing):
        valid_name(os.path.basename(path))
        os.mkdir(path, 0o775)
        give_to_server(path)

    return folder


def move_items(paths, dest):
    target_dir = safe_path(dest)
    root = os.path.realpath(S().data_dir)

    if not os.path.isdir(target_dir):
        raise FileError("El destino no es una carpeta")

    if not paths:
        raise FileError("No hay elementos seleccionados")

    sources = []

    # Se valida todo antes de mover nada
    for relative in paths:
        source = safe_path(relative)

        if source == root:
            raise FileError("No se puede mover la carpeta raíz")

        if target_dir == source or target_dir.startswith(source + os.sep):
            raise FileError("No se puede mover una carpeta dentro de sí misma")

        if os.path.dirname(source) == target_dir:
            raise FileError("El elemento ya está en esa carpeta")

        if os.path.lexists(os.path.join(target_dir, os.path.basename(source))):
            raise FileError("Ya existe un elemento con ese nombre")

        sources.append(source)

    for source in sources:
        shutil.move(source, os.path.join(target_dir, os.path.basename(source)))

    return {"ok": True, "message": "Movido", "count": len(sources)}


def delete_items(paths):
    root = os.path.realpath(S().data_dir)

    if not paths:
        raise FileError("No hay elementos seleccionados")

    targets = []

    for relative in paths:
        full = safe_path(relative)

        if full == root:
            raise FileError("No se puede borrar la carpeta raíz")

        targets.append(full)

    for full in targets:
        if os.path.isdir(full) and not os.path.islink(full):
            shutil.rmtree(full)
        elif os.path.lexists(full):
            os.remove(full)

    return {"ok": True, "message": "Eliminado", "count": len(targets)}


def build_zip(paths):
    # Empaqueta archivos y carpetas en un ZIP temporal. Sin compresion:
    # los mods y el mundo ya vienen comprimidos y asi es mucho mas rapido
    if not paths:
        raise FileError("No hay elementos seleccionados")

    root = os.path.realpath(S().data_dir)
    sources = [safe_path(p) for p in paths]

    if len(sources) == 1:
        name = (os.path.basename(sources[0]) or "minecraft-server") + ".zip"
    else:
        name = "minecraft-server-files.zip"

    tmp = tempfile.NamedTemporaryFile(prefix="mc-panel-", suffix=".zip", delete=False)

    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as archive:
            for source in sources:
                base = os.path.dirname(source) if source != root else root

                if os.path.isdir(source) and not os.path.islink(source):
                    for folder, dirs, files in os.walk(source):
                        if not dirs and not files:
                            archive.write(folder, os.path.relpath(folder, base))

                        for file_name in files:
                            full = os.path.join(folder, file_name)

                            if os.path.isfile(full) and not os.path.islink(full):
                                archive.write(full, os.path.relpath(full, base))
                elif os.path.isfile(source):
                    archive.write(source, os.path.relpath(source, base))

        tmp.close()
    except Exception:
        tmp.close()
        os.remove(tmp.name)
        raise

    return tmp.name, name


def receive_upload(handler, relative, name, length):
    folder = ensure_folder(relative)

    if not os.path.isdir(folder):
        raise FileError("El destino no es una carpeta")

    target = safe_path(
        relative_path(folder) + "/" + valid_name(name),
        must_exist=False
    )

    if os.path.isdir(target):
        raise FileError("Ya existe una carpeta con ese nombre")

    tmp = target + ".upload-panel"
    remaining = length

    try:
        with open(tmp, "wb") as f:
            while remaining > 0:
                chunk = handler.rfile.read(min(1024 * 1024, remaining))

                if not chunk:
                    raise FileError("La subida se interrumpió")

                f.write(chunk)
                remaining -= len(chunk)

        os.chmod(tmp, 0o664)
        give_to_server(tmp)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    return {"ok": True, "message": "Archivo subido"}
