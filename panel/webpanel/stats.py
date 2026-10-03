#
# MCServer by Derpchees - Monitor de recursos: CPU, memoria, discos y temperaturas
#

import os
import re
import time
import threading
import shlex
import glob

import mcpanel_core as core

from .common import command, current_server


HISTORY_POINTS = 90
STATS_INTERVAL = 2

_stats = {
    "cpu": 0.0,
    "cpu_history": [],
    "mem_history": [],
    "containers": {},
    "sizes": {},
    "docker_size": None
}

_stats_lock = threading.Lock()


def read_cpu_times():
    with open("/proc/stat", "r") as f:
        values = [int(x) for x in f.readline().split()[1:]]

    idle = values[3] + values[4]
    return sum(values), idle


def read_memory():
    info = {}

    with open("/proc/meminfo", "r") as f:
        for line in f:
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0]) * 1024

    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", 0)

    return total, total - available


def dir_size(path):
    output = command("du -sb " + shlex.quote(path) + " 2>/dev/null")

    try:
        return int(output.split()[0])
    except Exception:
        return None


def parse_docker_size(text):
    m = re.match(r"([\d.]+)\s*([KMGT]?i?B)", text.strip())

    if not m:
        return 0

    units = {
        "B": 1,
        "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12,
        "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4
    }

    return int(float(m.group(1)) * units.get(m.group(2), 1))


def stats_loop():
    prev_total, prev_idle = read_cpu_times()

    while True:
        time.sleep(STATS_INTERVAL)

        try:
            total, idle = read_cpu_times()
            dt = total - prev_total
            cpu = 0.0 if dt <= 0 else (1 - (idle - prev_idle) / dt) * 100
            prev_total, prev_idle = total, idle

            mem_total, mem_used = read_memory()
            now = int(time.time())

            with _stats_lock:
                _stats["cpu"] = round(cpu, 1)
                _stats["cpu_history"].append([now, round(cpu, 1)])
                _stats["mem_history"].append([now, mem_used])
                del _stats["cpu_history"][:-HISTORY_POINTS]
                del _stats["mem_history"][:-HISTORY_POINTS]
        except Exception:
            pass


def slow_stats_loop():
    # docker stats y du son lentos; van en su propio hilo
    last_du = 0

    while True:
        try:
            output = command(
                "docker stats --no-stream --format "
                "'{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}' 2>/dev/null"
            )

            containers = {}

            for line in output.splitlines():
                parts = line.split("|")

                if len(parts) != 3:
                    continue

                used, _, limit = parts[2].partition("/")
                containers[parts[0]] = {
                    "cpu": float(parts[1].strip().rstrip("%") or 0),
                    "mem_used": parse_docker_size(used),
                    "mem_limit": parse_docker_size(limit)
                }

            with _stats_lock:
                _stats["containers"] = containers

            if time.time() - last_du > 300 or _stats.pop("refresh_du", False):
                sizes = {}

                for srv in core.list_servers():
                    sizes[srv.slug] = {
                        "data": dir_size(srv.data_dir),
                        "backups": dir_size(srv.backup_dir)
                    }

                docker_size = dir_size("/var/lib/docker")

                with _stats_lock:
                    _stats["sizes"] = sizes
                    _stats["docker_size"] = docker_size

                last_du = time.time()
        except Exception:
            pass

        time.sleep(5)


def mount_point(path):
    path = os.path.realpath(path)

    while not os.path.ismount(path):
        parent = os.path.dirname(path)

        if parent == path:
            break

        path = parent

    return path


def disk_model(names):
    # Nombre comercial del disco (ej. "Samsung SSD 870") si el kernel lo expone
    for name in sorted(names):
        try:
            with open("/sys/block/%s/device/model" % name, "r") as f:
                model = f.read().strip()

            if model:
                return model
        except Exception:
            continue

    return ", ".join(sorted(names))


def configured_disks():
    # Un disco por sistema de archivos: el del servidor, el de los respaldos
    # (si es otro) y el del sistema (si es otro, para ver Docker y swap)
    found = []
    seen = {}

    srv = current_server()
    data_path = srv.data_dir if srv else core.data_root()
    backup_path_ = srv.backup_dir if srv else core.backup_root()

    for role, path in (("data", data_path), ("backups", backup_path_), ("system", "/")):
        if not os.path.exists(path):
            continue

        mount = mount_point(path)
        dev = os.stat(mount).st_dev

        if dev in seen:
            seen[dev]["roles"].append(role)
            continue

        entry = {"mount": mount, "roles": [role]}
        seen[dev] = entry
        found.append(entry)

    return found


def swap_file_size(mount):
    # Archivos de swap que viven en el disco indicado
    total = 0

    try:
        with open("/proc/swaps", "r") as f:
            for line in f.readlines()[1:]:
                name, kind, size = line.split()[:3]

                if kind == "file" and os.stat(name).st_dev == os.stat(mount).st_dev:
                    total += os.path.getsize(name)
    except Exception:
        pass

    return total


def physical_disks(sys_path):
    # Baja por LVM/particiones hasta los discos fisicos (sda, sdb...)
    slaves = glob.glob(sys_path + "/slaves/*")

    if slaves:
        found = set()
        for slave in slaves:
            found |= physical_disks(os.path.realpath(slave))
        return found

    if os.path.exists(sys_path + "/partition"):
        sys_path = os.path.dirname(sys_path)

    return {os.path.basename(sys_path)}


def disks_for_mount(path):
    try:
        st = os.stat(path)
        dev = "%d:%d" % (os.major(st.st_dev), os.minor(st.st_dev))
        return physical_disks(os.path.realpath("/sys/dev/block/" + dev))
    except Exception:
        return set()


def drive_temperatures():
    # Sensores del modulo drivetemp, por nombre de disco
    temps = {}

    for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            with open(hwmon + "/name", "r") as f:
                if f.read().strip() != "drivetemp":
                    continue

            block = os.listdir(hwmon + "/device/block")[0]
        except Exception:
            continue

        current = read_file_int(hwmon + "/temp1_input")

        if current is None:
            continue

        high = read_file_int(hwmon + "/temp1_max")

        temps[block] = {
            "current": current / 1000,
            "high": high / 1000 if high else None
        }

    return temps


def disk_list(sizes):
    disks = []
    temps = drive_temperatures()
    docker_dev = os.stat("/var/lib/docker").st_dev if os.path.exists("/var/lib/docker") else None

    for disk in configured_disks():
        path = disk["mount"]
        roles = disk["roles"]
        dev = os.stat(path).st_dev

        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = (st.f_blocks - st.f_bfree) * st.f_frsize

        # ext4 reserva ~5% para root; no es espacio usado de verdad
        reserved = (st.f_bfree - st.f_bavail) * st.f_frsize

        parts = []

        if "data" in roles:
            parts.append(["server", "Servidor", sizes.get("data")])

        if "backups" in roles:
            parts.append(["backups", "Respaldos", sizes.get("backups")])

        if docker_dev == dev:
            parts.append(["docker", "Docker", sizes.get("docker")])

        swap = swap_file_size(path)

        if swap:
            parts.append(["swap", "Swap", swap])

        rest_id = "system" if "system" in roles else "other"
        rest_label = "Sistema" if rest_id == "system" else "Otros"

        known = sum(p[2] or 0 for p in parts)
        rest = max(0, used - known)

        # ext4 siempre aparta unos MB para uso interno; por debajo
        # de 128 MB solo meteria ruido en la grafica
        tiny = 128 * 1024 ** 2

        parts.append([rest_id, rest_label, rest if rest >= tiny else 0])
        parts.append(["reserved", "Reservado", reserved if reserved >= tiny else 0])

        disk_temps = [
            temps[name] for name in sorted(disks_for_mount(path))
            if name in temps
        ]

        temp = None

        if disk_temps:
            temp = max(disk_temps, key=lambda t: t["current"])
            # Sin limite reportado: 70 C para SSD, 55 C para discos mecanicos
            if temp["high"] is None:
                rotational = read_file_int(
                    "/sys/block/%s/queue/rotational" % sorted(disks_for_mount(path))[0]
                )
                temp["high"] = 55 if rotational == 1 else 70

        disks.append({
            "id": "-".join(roles),
            "role": "data" if "data" in roles else roles[0],
            "label": disk_model(disks_for_mount(path)),
            "mount": path,
            "temp": temp,
            "total": total,
            "used": used + reserved,
            "free": free,
            "parts": [
                {"id": p[0], "label": p[1], "size": p[2]}
                for p in parts
            ]
        })

    return disks


def read_file_int(path):
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def cpu_temperature():
    # Temperatura general del procesador (sensor "Package" de coretemp)
    for hwmon in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        try:
            with open(hwmon + "/name", "r") as f:
                if f.read().strip() != "coretemp":
                    continue
        except Exception:
            continue

        for label_file in sorted(glob.glob(hwmon + "/temp*_label")):
            try:
                with open(label_file, "r") as f:
                    if not f.read().startswith("Package"):
                        continue
            except Exception:
                continue

            base = label_file[:-len("_label")]
            current = read_file_int(base + "_input")

            if current is None:
                continue

            high = read_file_int(base + "_max")
            crit = read_file_int(base + "_crit")

            return {
                "current": current / 1000,
                "high": high / 1000 if high else 80,
                "crit": crit / 1000 if crit else 95
            }

    for zone in glob.glob("/sys/class/thermal/thermal_zone*"):
        try:
            with open(zone + "/type", "r") as f:
                if f.read().strip() != "x86_pkg_temp":
                    continue
        except Exception:
            continue

        current = read_file_int(zone + "/temp")

        if current is not None:
            return {"current": current / 1000, "high": 80, "crit": 95}

    return None


def server_sizes():
    # Tamano del servidor actual, o de todos sumados (vista general)
    srv = current_server()
    sizes = _stats["sizes"]

    if srv:
        own = sizes.get(srv.slug, {})
        return {"data": own.get("data"), "backups": own.get("backups"), "docker": _stats["docker_size"]}

    known = [v for v in sizes.values()]
    return {
        "data": sum(v.get("data") or 0 for v in known) if known else None,
        "backups": sum(v.get("backups") or 0 for v in known) if known else None,
        "docker": _stats["docker_size"]
    }


def system_stats():
    mem_total, mem_used = read_memory()

    with _stats_lock:
        data = {
            "cpu": {
                "percent": _stats["cpu"],
                "cores": os.cpu_count(),
                "load": os.getloadavg(),
                "temp": cpu_temperature(),
                "history": list(_stats["cpu_history"])
            },
            "memory": {
                "total": mem_total,
                "used": mem_used,
                "history": list(_stats["mem_history"])
            },
            "disks": disk_list(server_sizes()),
            "container": None
        }

        srv = current_server()

        if srv:
            data["container"] = _stats["containers"].get(srv.container)

    try:
        with open("/proc/uptime", "r") as f:
            data["uptime"] = int(float(f.read().split()[0]))
    except Exception:
        data["uptime"] = None

    return data
