#
# MCServer by Derpchees - add-ons instalados en un servidor Bedrock
#
# Los paquetes viven en behavior_packs/ y resource_packs/ del servidor. El
# mundo los usa si estan en worlds/<mundo>/world_behavior_packs.json o
# world_resource_packs.json: activar o desactivar es agregarlos o quitarlos
# de ahi (la carpeta se queda). De donde vino cada uno (CurseForge o
# subido) se guarda en mcpanel-addons.json, dentro del servidor para que
# viaje con los respaldos. Los cambios se aplican al reiniciar el servidor.
#

import json
import os
import shutil
import time

from . import packs


REGISTRY = "mcpanel-addons.json"
WORLD_FILE = {"behavior": "world_behavior_packs.json", "resource": "world_resource_packs.json"}


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data, uid, gid):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-panel"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    try:
        os.chown(tmp, uid, gid)
    except OSError:
        pass

    os.replace(tmp, path)


class Addons:

    def __init__(self, data_dir, uid, gid, level_name=None):
        self.data_dir = data_dir
        self.uid = uid
        self.gid = gid
        self.level = level_name or self.read_level_name()

    # --------------------------------------------------------
    # Rutas

    def read_level_name(self):
        try:
            with open(os.path.join(self.data_dir, "server.properties"), "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("level-name="):
                        return line.split("=", 1)[1].strip() or "Bedrock level"
        except OSError:
            pass

        return "Bedrock level"

    def world_dir(self):
        name = self.level.replace("/", "_").replace("\\", "_").strip(".") or "Bedrock level"
        return os.path.join(self.data_dir, "worlds", name)

    def world_file(self, kind):
        return os.path.join(self.world_dir(), WORLD_FILE[kind])

    def registry_path(self):
        return os.path.join(self.data_dir, REGISTRY)

    # --------------------------------------------------------
    # Lectura

    def registry(self):
        data = read_json(self.registry_path(), {})
        return data if isinstance(data, dict) else {}

    def enabled(self, kind):
        data = read_json(self.world_file(kind), [])
        return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []

    def installed(self):
        # Los instalados desde el panel y los que el mundo usa. Bedrock trae
        # paquetes propios (librerias de scripts) que no se muestran
        registry = self.registry()
        active = {kind: {str(e.get("pack_id", "")).lower() for e in self.enabled(kind)} for kind in WORLD_FILE}
        found = []

        for kind, folder_name in packs.KIND_FOLDER.items():
            root = os.path.join(self.data_dir, folder_name)

            if not os.path.isdir(root):
                continue

            for folder in sorted(os.listdir(root)):
                path = os.path.join(root, folder)

                if packs.is_mojang(folder) or folder.endswith(".tmp-panel") or not os.path.isdir(path):
                    continue

                pack = packs.read_manifest(path)

                if not pack:
                    continue

                meta = registry.get(pack.uuid) or {}

                if not meta and pack.uuid not in active[kind]:
                    continue
                item = pack.info()
                item.update({
                    "kind": kind,
                    "folder": folder,
                    "enabled": pack.uuid in active[kind],
                    "icon": os.path.isfile(os.path.join(path, "pack_icon.png")),
                    "source": meta.get("source") or {},
                    "group": meta.get("group", ""),
                    "installed": meta.get("installed") or int(os.path.getmtime(path))
                })
                found.append(item)

        found.sort(key=lambda p: (p.get("group") or p["name"].lower(), p["kind"]))
        return found

    def find(self, uuid):
        for item in self.installed():
            if item["uuid"] == uuid:
                return item

        return None

    def icon_path(self, uuid):
        item = self.find(uuid)

        if not item or not item["icon"]:
            return None

        return os.path.join(self.data_dir, packs.KIND_FOLDER[item["kind"]], item["folder"], "pack_icon.png")

    # --------------------------------------------------------
    # Cambios

    def set_enabled(self, uuid, on):
        item = self.find(uuid)

        if not item:
            raise packs.PackError("Ese add-on no está instalado")

        entries = [e for e in self.enabled(item["kind"]) if str(e.get("pack_id", "")).lower() != uuid]

        # El primero de la lista tiene prioridad: el nuevo va arriba
        if on:
            entries.insert(0, {"pack_id": uuid, "version": item["version"]})

        write_json(self.world_file(item["kind"]), entries, self.uid, self.gid)
        return item

    def remove(self, uuid):
        item = self.find(uuid)

        if not item:
            raise packs.PackError("Ese add-on no está instalado")

        self.set_enabled(uuid, False)
        shutil.rmtree(os.path.join(self.data_dir, packs.KIND_FOLDER[item["kind"]], item["folder"]),
                      ignore_errors=True)

        registry = self.registry()

        if registry.pop(uuid, None) is not None:
            write_json(self.registry_path(), registry, self.uid, self.gid)

        return item

    def install(self, source_path, source=None, group=""):
        # Instala y activa todos los paquetes de un archivo. Devuelve sus datos.
        found = [p for p in packs.find_packs(source_path) if p.uuid]
        usable = [p for p in found if p.kind in packs.KIND_FOLDER]

        if not usable:
            if any(p.kind == "skin" for p in found):
                raise packs.PackError("Es un paquete de skins: se usa en el juego, no en el servidor")
            if any(p.kind == "world" for p in found):
                raise packs.PackError("Es una plantilla de mundo, no un add-on")
            raise packs.PackError("No se encontró ningún paquete (manifest.json) en el archivo")

        # Un mismo uuid repetido (por ejemplo dentro de dos .mcpack): el ultimo gana
        unique = {}

        for pack in usable:
            unique[pack.uuid] = pack

        registry = self.registry()
        current = {item["uuid"]: item for item in self.installed()}
        installed = []

        for pack in unique.values():
            # Una version anterior del mismo paquete en otra carpeta se reemplaza
            old = current.get(pack.uuid)

            if old:
                self.set_enabled(pack.uuid, False)
                shutil.rmtree(os.path.join(self.data_dir, packs.KIND_FOLDER[old["kind"]], old["folder"]),
                              ignore_errors=True)

            packs.extract(pack, self.data_dir, self.uid, self.gid)
            registry[pack.uuid] = {"name": pack.name, "source": source or {"provider": "upload"},
                                   "group": group or (found[0].name if len(unique) > 1 else ""),
                                   "installed": int(time.time())}
            installed.append(pack.info())

        write_json(self.registry_path(), registry, self.uid, self.gid)

        for item in installed:
            self.set_enabled(item["uuid"], True)

        return installed

    def has_resource_packs(self):
        return any(item["kind"] == "resource" and item["enabled"] for item in self.installed())
