#!/usr/bin/env python3
#
# MCServer by Derpchees - acceso seguro (HTTPS) con un dominio gratis
#
# La forma mas facil para todos: un subdominio gratis de DuckDNS y un
# certificado de Let's Encrypt, en el que todos los navegadores ya confian.
# Nadie tiene que instalar nada en su dispositivo.
#
#   1. el subdominio apunta a la IP del panel (puede ser privada: la de
#      ZeroTier, Tailscale o la red de la casa; nada queda en internet)
#   2. acme.sh pide el certificado probando el dominio por DNS (DuckDNS),
#      sin abrir puertos
#   3. acme.sh lo renueva solo (dura 90 dias, se renueva a los 60) y
#      reinicia el panel al renovarlo
#
# La otra opcion, sin dominio, es la CA propia (localca.py). Cada modo usa
# sus propios archivos; TLS_MODE en config.env dice cual esta activo.
#
# Desde el panel: Administracion > Acceso seguro. Desde la terminal (lo usa
# el instalador):
#   python3 duckdns.py enable <subdominio> <token> [--game]
#   python3 duckdns.py disable
#

import ipaddress
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcpanel_core as core  # noqa: E402

from sysadmin import tasks  # noqa: E402

ACME_HOME = "/root/.acme.sh"
ACME = os.path.join(ACME_HOME, "acme.sh")
TLS_DIR = os.path.join(os.path.dirname(core.CONFIG_ENV), "tls")
CERT = os.path.join(TLS_DIR, "le-cert.pem")
KEY = os.path.join(TLS_DIR, "le-key.pem")
SUBDOMAIN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
TOKEN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def run(*args, env=None, ok=(0,)):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True,
                            env=dict(os.environ, **(env or {})), cwd="/root" if os.path.isdir("/root") else None)

    if result.returncode not in ok:
        raise tasks.TaskError((result.stderr or result.stdout).strip()[-400:] or "Falló: " + str(args[0]))

    return result


def panel_ip():
    # IP a la que apunta el dominio: la del panel (o la direccion publica)
    for value in (core.live_cfg("PANEL_BIND", core.PANEL_BIND), core.get_setting("public_host") or core.PUBLIC_HOST):
        try:
            ip = ipaddress.ip_address(value)
            if not ip.is_unspecified:
                return str(ip)
        except ValueError:
            continue

    raise tasks.TaskError("No se sabe la IP del panel: pon la dirección pública (una IP) en Administración")


def cert_expiry():
    if not os.path.isfile(CERT):
        return None

    result = subprocess.run(["openssl", "x509", "-enddate", "-noout", "-in", CERT], capture_output=True, text=True)
    m = re.search(r"notAfter=(.+)", result.stdout)

    if not m:
        return None

    try:
        return int(time.mktime(time.strptime(m.group(1).replace("  ", " ").strip(), "%b %d %H:%M:%S %Y %Z")))
    except ValueError:
        return None


def status():
    active = core.live_cfg("TLS_MODE", "") == "duckdns"
    return {
        "enabled": active,
        "domain": core.live_cfg("PANEL_DOMAIN", "") if active else "",
        "port": core.PANEL_PORT,
        "expires": cert_expiry() if active else None,
        "task": tasks.status("https")
    }


def validate(subdomain, token):
    subdomain = str(subdomain or "").strip().lower().replace(".duckdns.org", "")
    subdomain = re.sub(r"^https?://", "", subdomain).strip("/")
    token = str(token or "").strip().lower()

    if not SUBDOMAIN.match(subdomain):
        raise tasks.TaskError("Subdominio no válido: solo letras, números y guiones")

    if not TOKEN.match(token):
        raise tasks.TaskError("El token de DuckDNS no parece válido")

    return subdomain, token


def enable_steps(subdomain, token, game_address=False):
    domain = subdomain + ".duckdns.org"
    ip = panel_ip()

    tasks.step("https", "point", domain=domain, ip=ip)
    url = "https://www.duckdns.org/update?" + urllib.parse.urlencode({"domains": subdomain, "token": token, "ip": ip})

    with urllib.request.urlopen(url, timeout=20) as response:
        if response.read().decode().strip() != "OK":
            raise tasks.TaskError("DuckDNS no aceptó el subdominio o el token")

    if not os.path.isfile(ACME):
        tasks.step("https", "install_acme")
        run("sh", "-c", "curl -fsSL https://get.acme.sh | sh", env={"HOME": "/root"})

        if not os.path.isfile(ACME):
            raise tasks.TaskError("No se pudo instalar acme.sh")

    # acme.sh guarda el token (solo root) para las renovaciones
    tasks.step("https", "issue", domain=domain)
    run(ACME, "--issue", "--dns", "dns_duckdns", "-d", domain, "--server", "letsencrypt",
        env={"DuckDNS_Token": token, "HOME": "/root"}, ok=(0, 2))

    tasks.step("https", "install_cert")
    os.makedirs(TLS_DIR, mode=0o700, exist_ok=True)
    run(ACME, "--install-cert", "-d", domain, "--key-file", KEY, "--fullchain-file", CERT,
        "--reloadcmd", "systemctl restart mcpanel-web", env={"HOME": "/root"})
    os.chmod(KEY, 0o600)

    core.set_config({"TLS_MODE": "duckdns", "TLS_CERT": CERT, "TLS_KEY": KEY, "PANEL_DOMAIN": domain})

    if game_address:
        core.set_setting("public_host", domain)

    return domain


def restart_panel_soon():
    # Despues de responder: el panel vuelve a arrancar con o sin HTTPS
    subprocess.run(["systemd-run", "--on-active=3", "--unit", "mcpanel-web-restart-%d" % int(time.time()),
                    "--collect", "--quiet", "systemctl", "restart", "mcpanel-web"], capture_output=True)


def enable(subdomain, token, game_address=False):
    subdomain, token = validate(subdomain, token)

    def work():
        enable_steps(subdomain, token, game_address)
        tasks.step("https", "restart")
        restart_panel_soon()

    tasks.start("https", work, done_event="https")
    return {"ok": True, "message": "Tarea iniciada", "url": "https://%s.duckdns.org:%d/" % (subdomain, core.PANEL_PORT)}


def disable():
    domain = core.live_cfg("PANEL_DOMAIN", "")

    # Sin renovaciones pendientes de un dominio que ya no se usa
    if domain and os.path.isfile(ACME):
        subprocess.run([ACME, "--remove", "-d", domain], capture_output=True, env=dict(os.environ, HOME="/root"))

    core.set_config({"TLS_MODE": "", "TLS_CERT": "", "TLS_KEY": "", "PANEL_DOMAIN": ""})

    if core.get_setting("public_host") == domain:
        core.set_setting("public_host", "")


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "enable":
        sub, tok = validate(sys.argv[2], sys.argv[3])
        print("https://%s:%d/" % (enable_steps(sub, tok, "--game" in sys.argv), core.PANEL_PORT))
    elif len(sys.argv) == 2 and sys.argv[1] == "disable":
        disable()
    else:
        print("Uso: duckdns.py enable <subdominio> <token> [--game] | disable", file=sys.stderr)
        sys.exit(2)
