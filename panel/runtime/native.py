#
# MCServer by Derpchees - servidores como procesos normales (Windows)
#
# Sin Docker: el panel descarga Java y el servidor (native/), y cada
# servidor corre bajo su vigilante (native/runner.py), que sigue vivo
# aunque el panel se reinicie. Mismas funciones que runtime/docker.py:
#   build    prepara los archivos y deja launch.json (con que se arranca)
#   matches  compara lo preparado con la configuracion actual
#   state    lee el estado que escribe el vigilante
#

import json
import os
import secrets
import socket
import time

import mcpanel_core as core

from native import procs, props, rcon as rcon_client, winsys

# Los puertos internos de RCON van lejos de los del juego
RCON_OFFSET = 10000
START_WAIT = 15
STOP_WAIT = 100

AIKAR_FLAGS = (
    "-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions "
    "-XX:+DisableExplicitGC -XX:+AlwaysPreTouch -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 "
    "-XX:G1HeapRegionSize=8M -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4 "
    "-XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90 "
    "-XX:G1RSetUpdatingPauseTimePercent=5 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem "
    "-XX:MaxTenuringThreshold=1 -Dusing.aikars.flags=https://mcflags.emc.gs -Daikars.new.flags=true"
).split()


# ============================================================
# Rutas
# ============================================================

def launch_path(srv):
    return os.path.join(srv.state_dir, "launch.json")


def spec_path(srv):
    return os.path.join(srv.state_dir, "native-spec.json")


def runner_path(srv):
    return os.path.join(os.path.dirname(srv.run_file), srv.slug + ".runner.json")


def console_path(srv):
    return os.path.join(srv.log_dir, "console.log")


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    os.replace(tmp, path)


def console_log(srv, text):
    # Lo que hace el panel sale en la consola del servidor (descargas, errores)
    os.makedirs(srv.log_dir, exist_ok=True)

    with open(console_path(srv), "a", encoding="utf-8") as f:
        f.write("%d\t[MCServer] %s\n" % (time.time() * 1000, text))


# ============================================================
# Como debe quedar
# ============================================================

def spec_of(srv):
    # Lo que, si cambia, obliga a preparar de nuevo el servidor
    spec = {
        "type": srv.type,
        "version": srv.version,
        "java": srv.java,
        "max_gb": srv.max_gb,
        "cpu": srv.cpu,
        "restart": not srv.autostop,
        "port": srv.internal_port,
        "env": dict(sorted(srv.extra_env.items()))
    }

    if srv.type == "AUTO_CURSEFORGE":
        spec["cf_key"] = bool(core.get_setting("cf_api_key"))

    return spec


def build(srv, start=False):
    if state(srv)[0] == "running":
        stop(srv)

    log = lambda text: console_log(srv, text)  # noqa: E731
    log("Preparando el servidor")

    try:
        launch = prepare_bedrock(srv, log) if core.is_bedrock(srv) else prepare_java(srv, log)
    except Exception as error:
        log("ERROR: %s" % error)
        raise

    launch.update({
        "slug": srv.slug,
        "cwd": srv.data_dir,
        "log": console_path(srv),
        "state": runner_path(srv),
        "stop_command": "stop",
        "restart": not srv.autostop,
        "cpus": srv.cpu if srv.cpu and srv.cpu > 0 else 0
    })

    write_json(launch_path(srv), launch)
    write_json(spec_path(srv), spec_of(srv))
    log("Listo")

    if start:
        ok, error = start_runner(srv)

        if not ok:
            raise RuntimeError(error)


def rcon_secret(srv):
    path = os.path.join(srv.state_dir, "rcon.secret")

    try:
        with open(path, "r", encoding="utf-8") as f:
            value = f.read().strip()

        if value:
            return value
    except OSError:
        pass

    value = secrets.token_hex(16)
    os.makedirs(srv.state_dir, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        f.write(value)

    return value


def prepare_java(srv, log):
    from native import java, loaders, modpacks, modsync, mojang

    type_ = srv.type
    loader = srv.extra_env.get(core.LOADER_ENV.get(type_, ""), "")

    # Los modpacks dicen que cargador y version de Minecraft llevan
    if type_ == "MODRINTH":
        type_, mc, loader = modpacks.modrinth(srv.data_dir, srv.extra_env.get("MODRINTH_MODPACK", ""),
                                              srv.extra_env.get("MODRINTH_VERSION", ""), log)
    elif type_ == "AUTO_CURSEFORGE":
        type_, mc, loader = modpacks.curseforge(srv.data_dir, srv.extra_env.get("CF_SLUG", ""),
                                                srv.extra_env.get("CF_FILE_ID", ""),
                                                core.get_setting("cf_api_key"), log)
    else:
        mc = mojang.resolve(srv.version)

    major = int(srv.java) if srv.java else mojang.java_major(mc)
    log("Java %d" % java.pick(major))
    java_exe = java.ensure(major)
    args = loaders.install(srv.data_dir, type_, mc, loader, java_exe, log)

    # Mods y plugins de Modrinth (MODRINTH_PROJECTS, como en Docker)
    entries = [(item.partition(":")[0], item.partition(":")[2])
               for item in srv.extra_env.get("MODRINTH_PROJECTS", "").split(",") if item]

    if type_ in modsync.LOADERS and (entries or os.path.exists(os.path.join(srv.data_dir, modsync.MARK))):
        modsync.sync(srv.data_dir, "plugins" if type_ == "PAPER" else "mods", entries, mc,
                     modsync.LOADERS[type_], log)

    with open(os.path.join(srv.data_dir, "eula.txt"), "w", encoding="utf-8") as f:
        f.write("eula=true\n")

    # Solo el agente habla con el puerto del juego (como el 127.0.0.1 de Docker)
    props.update(os.path.join(srv.data_dir, "server.properties"), {
        "server-ip": "127.0.0.1",
        "server-port": srv.internal_port,
        "enable-rcon": "true",
        "rcon.port": srv.internal_port + RCON_OFFSET,
        "rcon.password": rcon_secret(srv),
        "broadcast-rcon-to-ops": "false"
    })

    memory = ["-Xms%dG" % max(1, srv.max_gb // 2), "-Xmx%dG" % srv.max_gb]
    flags = AIKAR_FLAGS if type_ == "PAPER" else []
    encoding = ["-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8"]

    return {"cmd": [java_exe] + memory + flags + encoding + args, "memory": 0}


def prepare_bedrock(srv, log):
    from native import bedrock_win

    from bedrock import signaling

    bedrock_win.install(srv.data_dir, srv.version, log)

    # NetherNet: HTTP por el puerto interno (pasa por el agente) y el juego
    # por UDP en el rango propio del servidor. Sin Docker el servidor ve las
    # IP de este equipo y las anuncia solo.
    first, last = signaling.udp_range(srv)
    values = {
        "server-port": srv.internal_port,
        "transport": "nethernet",
        "server-udp-ports": "%d-%d" % (first, last),
        # Apagada, la consulta de estado (/v1/join) contesta vacia
        "enable-lan-visibility": "true"
    }

    if srv.extra_env.get("SERVER_NAME"):
        values["server-name"] = srv.extra_env["SERVER_NAME"]

    props.update(os.path.join(srv.data_dir, "server.properties"), values)

    return {"cmd": [os.path.join(srv.data_dir, "bedrock_server.exe")], "memory": srv.max_gb * 1024 ** 3}


def matches(srv):
    return os.path.isfile(launch_path(srv)) and read_json(spec_path(srv)) == json.loads(json.dumps(spec_of(srv)))


def remove(srv):
    stop(srv)

    for path in (launch_path(srv), spec_path(srv)):
        try:
            os.remove(path)
        except OSError:
            pass


def current_env(srv):
    return read_json(spec_path(srv)).get("env", {})


# ============================================================
# Estado
# ============================================================

def runner_info(srv):
    return read_json(runner_path(srv))


def runner_alive(info):
    return bool(info.get("pid")) and winsys.pid_alive(info["pid"], info.get("created"))


def healthy(srv):
    if core.is_bedrock(srv):
        from bedrock import signaling
        return signaling.status(srv.internal_port, 1.0) is not None

    # RCON abre cuando el mundo termino de cargar (el puerto del juego antes)
    try:
        with socket.create_connection(("127.0.0.1", srv.internal_port + RCON_OFFSET), 0.5):
            return True
    except OSError:
        return False


def state(srv):
    if not os.path.isfile(launch_path(srv)):
        return "missing", "missing", 0

    info = runner_info(srv)

    if info.get("status") in ("starting", "running", "stopping", "restarting") and runner_alive(info):
        if info.get("status") == "restarting" or not info.get("child"):
            return "restarting", "starting", 0

        return "running", "healthy" if healthy(srv) else "starting", 0

    code = info.get("exit_code")

    # El vigilante murio sin anotar el final (equipo apagado de golpe)
    if code is None and info.get("status") not in (None, "exited"):
        code = -1

    return "exited", "no-health", code or 0


def started_at(srv):
    info = runner_info(srv)
    return info.get("started") if runner_alive(info) else None


# ============================================================
# Acciones
# ============================================================

def request(info, payload, timeout=10):
    payload = dict(payload, token=info.get("token"))

    try:
        with socket.create_connection(("127.0.0.1", int(info.get("port") or 0)), timeout) as sock:
            sock.sendall(json.dumps(payload).encode("utf-8") + b"\n")
            data = b""

            while not data.endswith(b"\n"):
                chunk = sock.recv(4096)

                if not chunk:
                    break

                data += chunk

        return bool(json.loads(data.decode("utf-8") or "{}").get("ok"))
    except (OSError, ValueError):
        return False


def start(srv):
    return start_runner(srv)


def start_runner(srv):
    # (el nombre "start" lo tapa el parametro de build)
    if state(srv)[0] == "running":
        return True, ""

    if not os.path.isfile(launch_path(srv)):
        return False, "El servidor no está preparado"

    try:
        os.remove(runner_path(srv))
    except OSError:
        pass

    os.makedirs(os.path.dirname(runner_path(srv)), exist_ok=True)

    try:
        procs.spawn_detached([procs.pythonw(), procs.panel_script("native", "runner.py"), launch_path(srv)],
                             cwd=srv.data_dir)
    except RuntimeError as error:
        return False, str(error)

    deadline = time.time() + START_WAIT

    while time.time() < deadline:
        info = runner_info(srv)

        if info.get("status") == "running" and runner_alive(info):
            return True, ""

        if info.get("status") == "exited":
            return False, "El servidor se cerró al iniciar (revisa la consola)"

        time.sleep(0.3)

    return False, "El servidor no inició a tiempo"


def stop(srv):
    info = runner_info(srv)

    if not runner_alive(info):
        return True, ""

    if request(info, {"op": "stop"}):
        deadline = time.time() + STOP_WAIT

        while time.time() < deadline and runner_alive(info):
            time.sleep(0.5)

    # No contesto o no termino: se cierra a la fuerza
    if runner_alive(info):
        if info.get("child"):
            winsys.kill(info["child"])

        winsys.kill(info["pid"])

    return True, ""


def restart(srv):
    stop(srv)
    return start(srv)


def resume_after_boot():
    # Docker vuelve a encender los contenedores "unless-stopped" al prender
    # el equipo; aqui lo hace el agente con los que no se apagaron a mano
    for srv in core.list_servers():
        if srv.state != "ready" or srv.autostop:
            continue

        info = runner_info(srv)

        if info and not info.get("manual") and not runner_alive(info) and info.get("status") != "exited":
            start(srv)


def rcon(srv, args, timeout=20):
    text = " ".join(str(a) for a in args)

    try:
        return True, rcon_client.command(srv.internal_port + RCON_OFFSET, rcon_secret(srv), text, timeout)
    except (OSError, rcon_client.RconError) as error:
        return False, str(error)


def console_send(srv, text):
    info = runner_info(srv)

    if not runner_alive(info):
        return False, "El servidor está apagado"

    return request(info, {"op": "send", "text": text}), ""


def logs(srv, since=None, tail=None, timestamps=False):
    path = console_path(srv)
    lines = []

    for part in (path + ".1", path):
        try:
            with open(part, "r", encoding="utf-8", errors="replace") as f:
                lines += f.read().splitlines()
        except OSError:
            pass

    out = []
    limit = since * 1000 if since is not None else None

    for line in lines:
        stamp, _, text = line.partition("\t")

        try:
            ms = int(stamp)
        except ValueError:
            continue

        if limit is not None and ms < limit:
            continue

        if timestamps:
            text = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms / 1000)) + ".%03dZ %s" % (ms % 1000, text)

        out.append(text)

    if tail is not None:
        out = out[-int(tail):]

    return "\n".join(out) + ("\n" if out else "")


_usage = {}


def stats():
    found = {}
    cores = os.cpu_count() or 1

    for srv in core.list_servers():
        info = runner_info(srv)

        if not info.get("child") or not runner_alive(info):
            continue

        usage = winsys.usage(info["child"])

        if not usage:
            continue

        now = time.time()
        previous = _usage.get(srv.slug)
        _usage[srv.slug] = (now, usage[0])
        cpu = 0.0

        # Como docker stats: 100% = un nucleo
        if previous and now > previous[0]:
            cpu = min(cores * 100.0, max(0.0, (usage[0] - previous[1]) / (now - previous[0]) * 100))

        found[srv.container] = {"cpu": round(cpu, 1), "mem_used": usage[1],
                                "mem_limit": srv.max_gb * 1024 ** 3}

    return found
