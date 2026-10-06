#
# MCServer by Derpchees - servidores en contenedores Docker (Linux)
#
# Cada servidor es un contenedor de itzg/minecraft-server (o la imagen de
# Bedrock). La imagen descarga el servidor, los mods y Java; aqui solo se
# describe como debe quedar (container_spec) y se maneja con el comando docker.
#

import json
import re
import subprocess

import mcpanel_core as core


def docker(*args, check=False, timeout=None):
    result = subprocess.run(["docker"] + list(args), capture_output=True, text=True, timeout=timeout)

    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "docker " + " ".join(args))

    return result


def java_tag(version):
    # Version de Java que necesita cada version de Minecraft
    m = re.match(r"^1\.(\d+)(?:\.(\d+))?", version or "")

    if not m:
        return "latest"

    minor = int(m.group(1))
    patch = int(m.group(2) or 0)

    if minor < 17:
        return "java8"
    if minor == 17:
        return "java16"
    if minor < 20 or (minor == 20 and patch < 5):
        return "java17"

    return "latest"


def host_timezone():
    return subprocess.run(["timedatectl", "show", "-p", "Timezone", "--value"],
                          capture_output=True, text=True).stdout.strip() or "UTC"


# ============================================================
# Estado y acciones
# ============================================================

def state(srv):
    # (estado, salud, codigo de salida): running/exited/missing, healthy/starting/no-health
    result = docker("inspect", "-f",
                    "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}"
                    "|{{.State.ExitCode}}", srv.container)

    if result.returncode != 0:
        return "missing", "missing", 0

    status, health, exit_code = (result.stdout.strip().split("|") + ["", "", "0"])[:3]

    try:
        exit_code = int(exit_code)
    except ValueError:
        exit_code = 0

    return status, health, exit_code


def _action(*args):
    result = docker(*args)
    return result.returncode == 0, result.stderr.strip()


def start(srv):
    return _action("start", srv.container)


def stop(srv):
    return _action("stop", srv.container)


def restart(srv):
    return _action("restart", srv.container)


def rcon(srv, args, timeout=20):
    # Comando de Java con su respuesta (rcon-cli viene en la imagen)
    try:
        result = docker("exec", srv.container, "rcon-cli", *[str(a) for a in args], timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, ""

    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()

    # rcon-cli agrega codigos de color ANSI al final
    return True, re.sub(r"\x1b\[[0-9;]*m", "", result.stdout).strip()


def console_send(srv, text):
    # Linea en la consola de Bedrock: send-command busca el proceso en /proc,
    # sin --privileged Docker no lo deja
    try:
        result = docker("exec", "--privileged", srv.container, "send-command", *text.split(" "), timeout=20)
    except subprocess.TimeoutExpired:
        return False, ""

    return result.returncode == 0, (result.stdout + result.stderr).strip()


def logs(srv, since=None, tail=None, timestamps=False):
    # since: segundos desde 1970 (como float)
    args = ["docker", "logs"]

    if timestamps:
        args.append("--timestamps")

    if since is not None:
        args += ["--since", "%.3f" % since]

    if tail is not None:
        args += ["--tail", str(tail)]

    try:
        result = subprocess.run(args + [srv.container], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""

    return result.stdout


def started_at(srv):
    import calendar
    import time

    result = docker("inspect", "-f", "{{.State.StartedAt}}", srv.container)
    value = result.stdout.strip()

    if result.returncode != 0 or not value:
        return None

    try:
        return calendar.timegm(time.strptime(value[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None


def parse_size(text):
    m = re.match(r"([\d.]+)\s*([KMGT]?i?B)", text.strip())

    if not m:
        return 0

    units = {
        "B": 1,
        "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12,
        "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4
    }

    return int(float(m.group(1)) * units.get(m.group(2), 1))


def stats():
    # CPU y memoria de cada contenedor encendido, por nombre
    result = docker("stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}")
    found = {}

    for line in result.stdout.splitlines():
        parts = line.split("|")

        if len(parts) != 3:
            continue

        used, _, limit = parts[2].partition("/")
        found[parts[0]] = {
            "cpu": float(parts[1].strip().rstrip("%") or 0),
            "mem_used": parse_size(used),
            "mem_limit": parse_size(limit)
        }

    return found


# ============================================================
# Como debe quedar el contenedor
# ============================================================

def bedrock_spec(srv):
    # Bedrock no usa Java: la RAM es un limite del contenedor. Desde la 1.26
    # se conecta con NetherNet: HTTP por TCP (pasa por el proxy del agente) y
    # el juego por UDP directo a su rango de puertos, anunciado con la IP de
    # los jugadores (ver bedrock/signaling.py)
    from bedrock import signaling

    first, last = signaling.udp_range(srv)
    env = {
        "EULA": "TRUE",
        "VERSION": srv.version or "LATEST",
        "TRANSPORT": "nethernet",
        "SERVER_UDP_PORTS": "%s:%d-%d:%d-%d" % (signaling.advertised_ip(), first, last, first, last),
        "UID": str(core.MC_UID),
        "GID": str(core.MC_GID),
        "TZ": host_timezone()
    }

    for key, value in sorted(srv.extra_env.items()):
        env[key] = str(value)

    return {
        "image": core.BEDROCK_IMAGE + ":latest",
        "env": env,
        "cpus": srv.cpu if srv.cpu and srv.cpu > 0 else 0,
        "memory": srv.max_gb * 1024 ** 3,
        "restart": "no" if srv.autostop else "unless-stopped",
        "port": srv.internal_port,
        "udp": (first, last),
        "data": srv.data_dir
    }


def container_spec(srv):
    # Como debe quedar el contenedor del servidor. Lo usan build (para
    # crearlo) y matches (para saber si hay cambios pendientes).
    if core.is_bedrock(srv):
        return bedrock_spec(srv)

    image = "%s:%s" % (core.IMAGE, ("java" + srv.java) if srv.java else java_tag(srv.version))

    env = {
        "EULA": "TRUE",
        "TYPE": srv.type,
        "VERSION": srv.version,
        "INIT_MEMORY": "%dG" % max(1, srv.max_gb // 2),
        "MAX_MEMORY": "%dG" % srv.max_gb,
        "UID": str(core.MC_UID),
        "GID": str(core.MC_GID),
        "TZ": host_timezone()
    }

    if srv.type == "PAPER":
        env["USE_AIKAR_FLAGS"] = "true"

    for key, value in sorted(srv.extra_env.items()):
        env[key] = str(value)

    # Las dependencias obligatorias de los mods de Modrinth se instalan solas
    if "MODRINTH_PROJECTS" in srv.extra_env and "MODRINTH_DOWNLOAD_DEPENDENCIES" not in srv.extra_env:
        env["MODRINTH_DOWNLOAD_DEPENDENCIES"] = "required"

    # CurseForge necesita la clave de API para modpacks y mods
    if srv.type == "AUTO_CURSEFORGE" or "CURSEFORGE_FILES" in srv.extra_env:
        key = core.get_setting("cf_api_key")

        if key:
            env["CF_API_KEY"] = key

    return {
        "image": image,
        "env": env,
        "cpus": srv.cpu if srv.cpu and srv.cpu > 0 else 0,
        "restart": "no" if srv.autostop else "unless-stopped",
        "port": srv.internal_port,
        "data": srv.data_dir
    }


def build(srv, start=False):
    # (Re)crea el contenedor con los recursos del servidor. El mundo vive
    # en la carpeta del servidor, asi que recrearlo no borra nada.
    spec = container_spec(srv)

    if docker("image", "inspect", spec["image"]).returncode != 0:
        docker("pull", "-q", spec["image"], check=True)

    if docker("network", "inspect", core.DOCKER_NETWORK).returncode != 0:
        docker("network", "create", core.DOCKER_NETWORK)

    docker("rm", "-f", srv.container)

    args = [
        "create",
        "--name", srv.container,
        "--network", core.DOCKER_NETWORK,
        "--label", "mcpanel.server=" + srv.slug,
        "-v", "%s:/data" % spec["data"],
        "--stop-timeout", "60",
        "--restart", spec["restart"]
    ]

    if core.is_bedrock(srv):
        # HTTP por el proxy; el UDP del juego directo. La entrada abierta
        # deja mandar comandos con send-command
        first, last = spec["udp"]
        args += ["-p", "127.0.0.1:%d:19132/tcp" % spec["port"],
                 "-p", "%s:%d-%d:%d-%d/udp" % (core.LISTEN_IP, first, last, first, last), "-i"]
    else:
        args += ["-p", "127.0.0.1:%d:25565" % spec["port"]]

    if spec.get("memory"):
        args += ["--memory", str(spec["memory"])]

    for key, value in spec["env"].items():
        args += ["-e", "%s=%s" % (key, value)]

    if spec["cpus"]:
        args += ["--cpus", str(spec["cpus"])]

    docker(*(args + [spec["image"]]), check=True)

    if start:
        docker("start", srv.container, check=True)


def matches(srv):
    # True si el contenedor que existe ya tiene exactamente la configuracion
    # actual del servidor (entonces no hay nada pendiente de aplicar)
    result = docker("inspect", srv.container)

    if result.returncode != 0:
        return False

    try:
        info = json.loads(result.stdout)[0]
    except (ValueError, IndexError):
        return False

    spec = container_spec(srv)
    config = info.get("Config") or {}
    host = info.get("HostConfig") or {}

    if config.get("Image") != spec["image"]:
        return False

    if (host.get("RestartPolicy") or {}).get("Name", "no") != spec["restart"]:
        return False

    if int(host.get("NanoCpus") or 0) != int(spec["cpus"] * 1e9):
        return False

    if int(host.get("Memory") or 0) != int(spec.get("memory") or 0):
        return False

    # Variables propias: las del contenedor menos las que trae la imagen
    current = dict(item.split("=", 1) for item in config.get("Env") or [] if "=" in item)
    image_info = docker("image", "inspect", spec["image"])

    try:
        image_env = json.loads(image_info.stdout)[0]["Config"]["Env"] or []
        defaults = dict(item.split("=", 1) for item in image_env if "=" in item)
    except (ValueError, IndexError, KeyError, TypeError):
        defaults = {}

    own = {k: v for k, v in current.items() if defaults.get(k) != v}
    wanted = {k: v for k, v in spec["env"].items() if defaults.get(k) != v}

    return own == wanted


def remove(srv):
    docker("rm", "-f", srv.container)


def current_env(srv):
    # Variables con las que se creo (el panel compara el nombre de Bedrock)
    result = docker("inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", srv.container)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
