#!/usr/bin/env python3
#
# MCServer by Derpchees - acceso seguro (HTTPS) con una CA propia
#
# Los navegadores solo permiten cosas como las notificaciones en paginas
# seguras. Sin dominios ni servicios externos, el servidor crea su propia
# autoridad de certificados (CA) y con ella el certificado del panel:
#
#   - la CA dura 10 anos; cada dispositivo la instala una vez
#     (Administracion > Acceso seguro > Descargar certificado, o /ca.crt)
#   - el certificado del panel cubre las IP del equipo (red local, ZeroTier,
#     Tailscale...) y su nombre; dura 397 dias y el agente lo renueva solo
#     antes de vencer o si cambian las IP. Al renovarlo no hay que volver a
#     instalar nada en los dispositivos: lo firma la misma CA.
#
# Desde la terminal (lo usa el instalador):
#   python3 localca.py enable | disable | renew
#

import ipaddress
import os
import re
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcpanel_core as core  # noqa: E402

TLS_DIR = os.path.join(os.path.dirname(core.CONFIG_ENV), "tls")
CA_KEY = os.path.join(TLS_DIR, "ca.key")
CA_CERT = os.path.join(TLS_DIR, "ca.crt")
KEY = os.path.join(TLS_DIR, "key.pem")
CERT = os.path.join(TLS_DIR, "cert.pem")

CA_DAYS = 3650
CERT_DAYS = 397          # el maximo que aceptan Apple y los navegadores
RENEW_DAYS = 30          # se renueva cuando faltan menos de 30 dias

# Interfaces que no son de la red de la casa ni de una VPN
SKIP_IFACES = re.compile(r"^(lo|docker\d*|br-|veth|virbr|lxcbr|cni|flannel)")


class CertError(Exception):
    pass


def openssl(*args, data=None):
    result = subprocess.run(["openssl"] + [str(a) for a in args], capture_output=True, text=True, input=data)

    if result.returncode != 0:
        raise CertError((result.stderr or result.stdout).strip()[-300:] or "openssl falló")

    return result.stdout


def host_names():
    name = socket.gethostname().split(".")[0]
    return sorted({name, name + ".local", "localhost"})


def host_ips():
    # IPv4 del equipo en sus redes (sin las de Docker)
    ips = set()
    result = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True)

    for line in result.stdout.splitlines():
        parts = line.split()

        if len(parts) >= 4 and not SKIP_IFACES.match(parts[1]):
            ips.add(parts[3].split("/")[0])

    bind = core.live_cfg("PANEL_BIND", core.PANEL_BIND)

    try:
        if not ipaddress.ip_address(bind).is_unspecified:
            ips.add(bind)
    except ValueError:
        pass

    ips.add("127.0.0.1")
    return sorted(ips, key=lambda ip: tuple(int(x) for x in ip.split(".")))


def cert_info(path):
    # (vence en epoch, IPs, nombres) del certificado, o None
    if not os.path.isfile(path):
        return None

    try:
        text = openssl("x509", "-in", path, "-noout", "-enddate", "-ext", "subjectAltName")
    except CertError:
        return None

    m = re.search(r"notAfter=(.+)", text)
    expires = int(time.mktime(time.strptime(m.group(1).replace("  ", " ").strip(), "%b %d %H:%M:%S %Y %Z"))) if m else 0

    return {
        "expires": expires,
        "ips": sorted(re.findall(r"IP Address:([0-9.]+)", text)),
        "names": sorted(re.findall(r"DNS:([^,\s]+)", text))
    }


def create_ca():
    os.makedirs(TLS_DIR, mode=0o700, exist_ok=True)
    name = socket.gethostname().split(".")[0]

    openssl("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
            "-keyout", CA_KEY, "-out", CA_CERT, "-days", CA_DAYS,
            "-subj", "/O=MCServer/CN=MCServer CA (%s)" % name,
            "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    os.chmod(CA_KEY, 0o600)
    os.chmod(CA_CERT, 0o644)


def create_cert():
    ips = host_ips()
    names = host_names()
    san = ",".join(["IP:" + ip for ip in ips] + ["DNS:" + n for n in names])

    with tempfile.TemporaryDirectory() as tmp:
        csr = os.path.join(tmp, "req.csr")
        ext = os.path.join(tmp, "ext.cnf")
        key = os.path.join(tmp, "key.pem")
        cert = os.path.join(tmp, "cert.pem")

        with open(ext, "w") as f:
            f.write("basicConstraints=critical,CA:FALSE\n"
                    "keyUsage=critical,digitalSignature,keyEncipherment\n"
                    "extendedKeyUsage=serverAuth\n"
                    "subjectAltName=%s\n" % san)

        openssl("req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                "-keyout", key, "-out", csr, "-subj", "/O=MCServer/CN=" + names[0])
        openssl("x509", "-req", "-in", csr, "-CA", CA_CERT, "-CAkey", CA_KEY, "-CAcreateserial",
                "-out", cert, "-days", CERT_DAYS, "-sha256", "-extfile", ext)

        # Se reemplazan juntos: el panel nunca ve un certificado sin su clave
        os.makedirs(TLS_DIR, mode=0o700, exist_ok=True)
        os.replace(key, KEY)
        os.replace(cert, CERT)
        os.chmod(KEY, 0o600)
        os.chmod(CERT, 0o644)

    return ips, names


def needs_renewal():
    info = cert_info(CERT)

    if not info:
        return True

    if info["expires"] - time.time() < RENEW_DAYS * 86400:
        return True

    # Una IP nueva (otra red, VPN) tambien necesita estar en el certificado
    return not set(host_ips()) <= set(info["ips"])


def enable():
    if not os.path.isfile(CA_CERT) or not os.path.isfile(CA_KEY):
        create_ca()

    if needs_renewal():
        create_cert()

    core.set_config({"TLS_CERT": CERT, "TLS_KEY": KEY})
    return status()


def disable():
    # La CA se conserva: si se vuelve a activar, los dispositivos ya la tienen
    core.set_config({"TLS_CERT": "", "TLS_KEY": ""})


def renew_if_needed():
    # Lo llama el agente cada dia. True si hubo que renovar (y reiniciar el panel)
    if not core.live_cfg("TLS_CERT", "") or not os.path.isfile(CA_KEY):
        return False

    if not needs_renewal():
        return False

    create_cert()
    return True


def status():
    cert = cert_info(CERT)
    ca = cert_info(CA_CERT)
    active = bool(core.live_cfg("TLS_CERT", ""))

    return {
        "enabled": active,
        "running": core.tls_enabled(),
        "port": core.PANEL_PORT,
        "ips": cert["ips"] if cert else host_ips(),
        "names": cert["names"] if cert else host_names(),
        "expires": cert["expires"] if cert else None,
        "ca_expires": ca["expires"] if ca else None,
        "ca_available": os.path.isfile(CA_CERT)
    }


def ca_bytes():
    with open(CA_CERT, "rb") as f:
        return f.read()


def restart_panel_soon():
    # Despues de responder: el panel vuelve a arrancar con o sin HTTPS
    subprocess.run(["systemd-run", "--on-active=3", "--unit", "mcpanel-web-restart-%d" % int(time.time()),
                    "--collect", "--quiet", "systemctl", "restart", "mcpanel-web"], capture_output=True)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) == 2 else ""

    if command == "enable":
        info = enable()
        print("https  " + "  ".join(info["ips"]))
    elif command == "disable":
        disable()
    elif command == "renew":
        print("renovado" if renew_if_needed() else "vigente")
    else:
        print("Uso: localca.py enable | disable | renew", file=sys.stderr)
        sys.exit(2)
