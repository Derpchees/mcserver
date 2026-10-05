#!/bin/bash
#
# MCServer by Derpchees - instalador
# https://github.com/Derpchees/mcserver
#
# Uso:
#   sudo ./install.sh                     instalacion interactiva
#   sudo ./install.sh --config FILE       sin preguntas (ver examples/answers.env)
#   sudo ./install.sh --update            actualiza el panel, conserva datos y cuentas
#   sudo ./install.sh --lang es           idioma del instalador (en/es)
#
# El instalador prepara el sistema (discos, red, puertos). La cuenta de
# administrador y los servidores se crean despues desde el navegador.
#

set -euo pipefail

VERSION="2.3.5"
REPO="Derpchees/mcserver"
INSTALL_DIR="/opt/mcpanel"
CONFIG_DIR="/etc/mcpanel"
CONFIG="$CONFIG_DIR/config.env"
SYSTEMD_DIR="/etc/systemd/system"
IMAGE="itzg/minecraft-server"

ANSWERS=""
UPDATE_ONLY=0
UI_LANG=""

while [ $# -gt 0 ]; do
    case "$1" in
        --config) ANSWERS="$2"; shift 2 ;;
        --update) UPDATE_ONLY=1; shift ;;
        --lang) UI_LANG="$2"; shift 2 ;;
        -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done


# ============================================================
# Textos
# ============================================================

declare -A EN ES

EN[title]="MCServer by Derpchees $VERSION"
ES[title]="MCServer by Derpchees $VERSION"
EN[need_root]="Run the installer with sudo."
ES[need_root]="Ejecuta el instalador con sudo."
EN[bad_os]="This installer supports Debian and Ubuntu (apt). Detected:"
ES[bad_os]="Este instalador es para Debian y Ubuntu (apt). Detectado:"
EN[welcome]="MCServer runs several Minecraft servers on this machine, each in Docker, with a web panel:\n\n- Every person creates an account and their own server (Forge, NeoForge, Fabric, Paper or Vanilla) and picks its RAM and CPU\n- Console, chat, players, files, backups, settings and resource monitor\n- Servers start when someone connects and stop when nobody plays\n- Daily backups and browser notifications\n\nThis installer prepares the system. You will create the administrator account in the browser at the end."
ES[welcome]="MCServer corre varios servidores de Minecraft en este equipo, cada uno en Docker, con un panel web:\n\n- Cada persona crea su cuenta y su propio servidor (Forge, NeoForge, Fabric, Paper o Vanilla) y elige su RAM y CPU\n- Consola, chat, jugadores, archivos, respaldos, ajustes y monitor de recursos\n- Los servidores se encienden al conectarse y se apagan cuando nadie juega\n- Respaldos diarios y notificaciones del navegador\n\nEste instalador prepara el sistema. Al final crearás la cuenta de administrador en el navegador."
EN[existing]="MCServer is already installed. What do you want to do?"
ES[existing]="MCServer ya está instalado. ¿Qué quieres hacer?"
EN[opt_update]="Update (keep accounts, servers and worlds)"
ES[opt_update]="Actualizar (conserva cuentas, servidores y mundos)"
EN[opt_reconfig]="Change the system settings (servers are kept)"
ES[opt_reconfig]="Cambiar la configuración del sistema (los servidores se conservan)"
EN[opt_uninstall]="Uninstall"
ES[opt_uninstall]="Desinstalar"
EN[opt_cancel]="Cancel"
ES[opt_cancel]="Cancelar"
EN[data_disk]="Where should the SERVERS live (worlds, mods, configs)?\nEach server gets its own folder here. A fast disk (SSD) is recommended."
ES[data_disk]="¿Dónde van los SERVIDORES (mundos, mods, configuración)?\nCada servidor tendrá su carpeta aquí. Se recomienda un disco rápido (SSD)."
EN[backup_disk]="Where should the BACKUPS go?\nA different physical disk protects you if the server disk fails."
ES[backup_disk]="¿Dónde van los RESPALDOS?\nUn disco físico distinto te protege si falla el de los servidores."
EN[unmounted]="Not mounted"
ES[unmounted]="Sin montar"
EN[free]="free"
ES[free]="libres"
EN[mount_where]="The partition will be mounted permanently (it is NOT formatted).\n\nMount point:"
ES[mount_where]="La partición se montará de forma permanente (NO se formatea).\n\nPunto de montaje:"
EN[mount_fail]="Could not mount the partition:"
ES[mount_fail]="No se pudo montar la partición:"
EN[folder_data]="Folder for the servers:"
ES[folder_data]="Carpeta para los servidores:"
EN[folder_backups]="Folder for the backups:"
ES[folder_backups]="Carpeta para los respaldos:"
EN[listen]="On which network should the panel and the game servers be reachable?"
ES[listen]="¿En qué red se podrá entrar al panel y a los servidores?"
EN[all_networks]="All networks"
ES[all_networks]="Todas las redes"
EN[panel_port]="Panel port:"
ES[panel_port]="Puerto del panel:"
EN[game_port]="First game port. Each new server uses the next free one (25565, 25566, ...):"
ES[game_port]="Primer puerto de juego. Cada servidor nuevo usa el siguiente libre (25565, 25566, ...):"
EN[port_busy]="Port %s is already in use. Choose another one."
ES[port_busy]="El puerto %s ya está en uso. Elige otro."
EN[address]="Address players will use to connect (IP or domain, without port):"
ES[address]="Dirección que usarán los jugadores para conectarse (IP o dominio, sin puerto):"
EN[eula]="Minecraft servers require accepting the Mojang EULA:\nhttps://aka.ms/MinecraftEULA\n\nServers created in this panel accept it. Do you accept it?"
EN[https_menu]="Secure access (HTTPS). Browsers only allow notifications on secure pages:"
ES[https_menu]="Acceso seguro (HTTPS). Los navegadores solo permiten notificaciones en páginas seguras:"
EN[https_opt_duckdns]="Free domain (DuckDNS): nothing to install on devices (recommended)"
ES[https_opt_duckdns]="Dominio gratis (DuckDNS): nada que instalar en los dispositivos (recomendado)"
EN[https_opt_local]="Own certificate: no outside services; each device installs it once"
ES[https_opt_local]="Certificado propio: sin servicios externos; cada dispositivo lo instala una vez"
EN[https_opt_no]="Not now (it can be turned on later in Admin)"
ES[https_opt_no]="Ahora no (se puede activar después en Administración)"
EN[https_steps]="1. Open duckdns.org and sign in with Google, GitHub or Reddit.\n2. In \"sub domain\" type a name (e.g. my-server) and press \"add domain\". Do not change the IP.\n3. Copy the token shown at the top.\n\nName (only the part before .duckdns.org):"
ES[https_steps]="1. Abre duckdns.org y entra con Google, GitHub o Reddit.\n2. En \"sub domain\" escribe un nombre (ej. mi-servidor) y pulsa \"add domain\". No cambies la IP.\n3. Copia el token que aparece arriba.\n\nNombre (solo la parte antes de .duckdns.org):"
EN[https_token]="Paste the DuckDNS token:"
ES[https_token]="Pega el token de DuckDNS:"
EN[https_ca]="HTTPS is on. On each device, open %s/ca.crt once and install the certificate (Admin > Secure access explains how)."
ES[https_ca]="HTTPS activado. En cada dispositivo abre una vez %s/ca.crt e instala el certificado (Administración > Acceso seguro explica cómo)."
EN[https_fail]="HTTPS could not be turned on now. You can retry in Admin > Secure access."
ES[https_fail]="No se pudo activar HTTPS ahora. Puedes reintentarlo en Administración > Acceso seguro."
EN[step_https]="Secure access (HTTPS)"
ES[step_https]="Acceso seguro (HTTPS)"
ES[eula]="Los servidores de Minecraft requieren aceptar el EULA de Mojang:\nhttps://aka.ms/MinecraftEULA\n\nLos servidores creados en este panel lo aceptan. ¿Lo aceptas?"
EN[eula_no]="The EULA must be accepted to run Minecraft servers."
ES[eula_no]="Hay que aceptar el EULA para correr servidores de Minecraft."
EN[summary]="Summary"
ES[summary]="Resumen"
EN[confirm]="Install with these settings?"
ES[confirm]="¿Instalar con estos ajustes?"
EN[cancelled]="Installation cancelled. Nothing was changed."
ES[cancelled]="Instalación cancelada. No se cambió nada."
EN[s_servers]="Servers"
ES[s_servers]="Servidores"
EN[s_backups]="Backups"
ES[s_backups]="Respaldos"
EN[s_network]="Network"
ES[s_network]="Red"
EN[s_ports]="Ports"
ES[s_ports]="Puertos"
EN[s_address]="Address"
ES[s_address]="Dirección"
EN[step_packages]="Installing packages (Docker, Python, ...)"
ES[step_packages]="Instalando paquetes (Docker, Python, ...)"
EN[step_files]="Copying MCServer"
ES[step_files]="Copiando MCServer"
EN[step_image]="Downloading the Minecraft image (may take a few minutes)"
ES[step_image]="Descargando la imagen de Minecraft (puede tardar unos minutos)"
EN[step_services]="Starting services"
ES[step_services]="Iniciando servicios"
EN[done]="Installation complete!"
ES[done]="¡Instalación completa!"
EN[done_body]="Open the panel to create the administrator account:\n\n    %s\n\nThen anyone can create an account and their server from the login page (you can turn this off in Administration).\n\nForgot a password:  sudo mcpanel-passwd <user>\nUninstall:          sudo %s/uninstall.sh"
ES[done_body]="Abre el panel para crear la cuenta de administrador:\n\n    %s\n\nDespués cualquiera puede crear su cuenta y su servidor desde la pantalla de entrar (lo puedes desactivar en Administración).\n\n¿Olvidaste una contraseña?  sudo mcpanel-passwd <usuario>\nDesinstalar:                sudo %s/uninstall.sh"
EN[updated]="MCServer updated to version %s. Accounts, servers and worlds were kept."
ES[updated]="MCServer actualizado a la versión %s. Se conservaron cuentas, servidores y mundos."
EN[no_config]="No existing installation found. Run the installer without --update."
ES[no_config]="No hay una instalación. Corre el instalador sin --update."
EN[step_firewall]="Opening the panel and game ports in the firewall (ufw)"
ES[step_firewall]="Abriendo los puertos del panel y de los juegos en el firewall (ufw)"
EN[failed]="The installation failed at:"
ES[failed]="La instalación falló en:"
EN[download]="Downloading the installer files from GitHub..."
ES[download]="Descargando los archivos del instalador desde GitHub..."


t() {
    local key="$1"
    shift
    local text

    if [ "$UI_LANG" = "es" ]; then
        text="${ES[$key]:-${EN[$key]:-$key}}"
    else
        text="${EN[$key]:-$key}"
    fi

    # shellcheck disable=SC2059
    printf "$text" "$@"
}


# ============================================================
# Utilidades
# ============================================================

INTERACTIVE=1
[ -n "$ANSWERS" ] && INTERACTIVE=0

die() {
    echo -e "\n[mcserver] $*" >&2
    exit 1
}

info() {
    echo -e "\n==> $*"
}

cancel() {
    # Puede llamarse dentro de $(...): todo va a la terminal, no a stdout
    if [ "$INTERACTIVE" -eq 1 ]; then
        clear >/dev/tty 2>/dev/null || true
    fi
    echo "$(t cancelled)" >&2
    exit 1
}

ui_msg() {
    whiptail --title "$(t title)" --msgbox "$1" 22 78 1>&2
}

ui_yesno() {
    whiptail --title "$(t title)" --yesno "$1" 18 78 1>&2
}

ui_input() {
    local result
    result=$(whiptail --title "$(t title)" --inputbox "$1" 12 78 "$2" 3>&1 1>&2 2>&3) || cancel
    echo "$result"
}

ui_menu() {
    local text="$1"
    shift
    local result
    result=$(whiptail --title "$(t title)" --menu "$text" 22 78 12 "$@" 3>&1 1>&2 2>&3) || cancel
    echo "$result"
}

human() {
    numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "$1"
}

port_free() {
    ! ss -ltnH "( sport = :$1 )" 2>/dev/null | grep -q .
}

valid_port() {
    [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

primary_ip() {
    { ip -4 route get 1.1.1.1 2>/dev/null || true; } | awk '{for (i=1; i<NF; i++) if ($i=="src") print $(i+1)}' | head -1
}

write_config_value() {
    local value="${2//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//\$/\\\$}"
    value="${value//\`/\\\`}"
    echo "$1=\"$value\""
}


# ============================================================
# Comprobaciones
# ============================================================

[ "$(id -u)" -eq 0 ] || die "$(t need_root)"

if [ -z "$UI_LANG" ]; then
    case "${LANG:-}" in
        es*) UI_LANG="es" ;;
        *) UI_LANG="en" ;;
    esac
fi

# /etc/os-release define VERSION y otras variables: se lee en un subshell
# para no pisar las del instalador
OS_IDS=$( . /etc/os-release 2>/dev/null; echo "${ID:-} ${ID_LIKE:-}" )
OS_NAME=$( . /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-?}" )

if ! command -v apt-get >/dev/null || [[ ! " $OS_IDS " =~ (debian|ubuntu) ]]; then
    die "$(t bad_os) $OS_NAME"
fi

# Si se corre solo el script (curl | bash), se descarga el resto del repo
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"

if [ ! -f "$SRC/panel/mcpanel.py" ]; then
    echo "$(t download)"
    command -v curl >/dev/null || apt-get install -y -qq curl >/dev/null
    TMP_SRC="$(mktemp -d)"
    curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/main" | tar xz -C "$TMP_SRC" \
        || die "Download failed"
    SRC="$(find "$TMP_SRC" -maxdepth 1 -mindepth 1 -type d | head -1)"
fi

if [ "$INTERACTIVE" -eq 1 ] && ! command -v whiptail >/dev/null; then
    apt-get install -y -qq whiptail >/dev/null || die "Could not install whiptail"
fi


# ============================================================
# Archivos y servicios (comun a todos los modos)
# ============================================================

install_files() {
    mkdir -p "$INSTALL_DIR/bin" "$CONFIG_DIR"

    # La carpeta panel/ se reemplaza completa (codigo y pagina web);
    # los datos viven en /var/lib/mcpanel, no aqui
    rm -rf "$INSTALL_DIR/panel"
    cp -r "$SRC/panel" "$INSTALL_DIR/panel"
    find "$INSTALL_DIR/panel" -name __pycache__ -type d -prune -exec rm -rf {} +
    find "$INSTALL_DIR/panel" -type d -exec chmod 755 {} +
    find "$INSTALL_DIR/panel" -type f -exec chmod 644 {} +
    chmod 755 "$INSTALL_DIR"/panel/*.py

    for f in "$SRC"/bin/*; do
        install -m 755 "$f" "$INSTALL_DIR/bin/$(basename "$f")"
    done

    install -m 755 "$SRC/uninstall.sh" "$INSTALL_DIR/uninstall.sh"
    echo "$VERSION" > "$INSTALL_DIR/VERSION"
    ln -sf "$INSTALL_DIR/bin/mcpanel-passwd" /usr/local/bin/mcpanel-passwd
}

# Si ufw esta activo abre el panel y un rango de puertos de juego. Las
# reglas se guardan para que uninstall.sh las quite.
configure_firewall() {
    command -v ufw >/dev/null || return 0
    ufw status 2>/dev/null | grep -q "^Status: active" || return 0

    step "$(t step_firewall)"

    local iface="" rules="$CONFIG_DIR/ufw-rules"

    if [ "$LISTEN_IP" != "0.0.0.0" ]; then
        iface=$(ip -4 -o addr show | awk -v ip="$LISTEN_IP" '{split($4, a, "/"); if (a[1] == ip) print $2}' | head -1)
    fi

    local scope=""
    [ -n "$iface" ] && scope="in on $iface "

    : > "$rules"

    for spec in "${scope}to any port $PANEL_PORT proto tcp" \
                "${scope}to any port $GAME_PORT_START:$((GAME_PORT_START + 49)) proto tcp"; do
        # shellcheck disable=SC2086
        ufw allow $spec comment mcserver >/dev/null
        echo "$spec" >> "$rules"
    done
}


install_units() {
    # Servicios de la version 1 (un solo servidor), si existen
    for old in mcpanel-proxy.service mcpanel-autostop.service mcpanel-backup.timer; do
        systemctl disable --now "$old" >/dev/null 2>&1 || true
        rm -f "$SYSTEMD_DIR/$old"
    done
    rm -rf "$SYSTEMD_DIR/mcpanel-backup@.service" "$SYSTEMD_DIR/mcpanel-backup@.service.d"

    for unit in mcpanel-web.service mcpanel-agent.service; do
        install -m 644 "$SRC/systemd/$unit" "$SYSTEMD_DIR/$unit"
    done

    systemctl daemon-reload
    systemctl enable mcpanel-web.service mcpanel-agent.service >/dev/null 2>&1
    systemctl restart mcpanel-web.service mcpanel-agent.service
}


# ============================================================
# Modo actualizacion
# ============================================================

if [ "$UPDATE_ONLY" -eq 1 ]; then
    [ -f "$CONFIG" ] || die "$(t no_config)"

    # Programas que agregaron versiones nuevas (Almacenamiento)
    missing=""
    for pkg in rsync parted openssl; do
        command -v "$pkg" >/dev/null || missing="$missing $pkg"
    done
    command -v mkfs.ext4 >/dev/null || missing="$missing e2fsprogs"
    if [ -n "$missing" ]; then
        export DEBIAN_FRONTEND=noninteractive
        # shellcheck disable=SC2086
        apt-get install -y -qq $missing >/dev/null || true
    fi

    install_files
    python3 "$INSTALL_DIR/panel/mcpanel_core.py" init >/dev/null
    install_units
    echo "$(t updated "$VERSION")"
    exit 0
fi

if [ -f "$CONFIG" ] && [ "$INTERACTIVE" -eq 1 ]; then
    choice=$(ui_menu "$(t existing)" \
        update "$(t opt_update)" \
        reconfig "$(t opt_reconfig)" \
        uninstall "$(t opt_uninstall)" \
        cancel "$(t opt_cancel)")

    case "$choice" in
        update)
            clear
            install_files
            python3 "$INSTALL_DIR/panel/mcpanel_core.py" init >/dev/null
            install_units
            echo "$(t updated "$VERSION")"
            exit 0 ;;
        uninstall)
            clear
            exec "$SRC/uninstall.sh" ;;
        cancel)
            cancel ;;
    esac
fi


# ============================================================
# Preguntas
# ============================================================

DATA_ROOT="/srv/minecraft/servers"
BACKUP_ROOT="/srv/minecraft/backups"
LISTEN_IP="0.0.0.0"
PANEL_PORT=8090
GAME_PORT_START=25565
PUBLIC_HOST=""
ACCEPT_EULA="no"
HTTPS="local"
DUCKDNS_SUBDOMAIN=""
DUCKDNS_TOKEN=""
ADMIN_USER=""
ADMIN_PASSWORD=""

if [ -n "$ANSWERS" ]; then
    [ -f "$ANSWERS" ] || die "No existe $ANSWERS"
    # shellcheck source=/dev/null
    . "$ANSWERS"
fi

disk_menu_items() {
    local target source fstype size avail

    while read -r target source fstype size avail; do
        case "$fstype" in
            tmpfs|devtmpfs|overlay|squashfs|efivarfs|vfat|proc|sysfs|cgroup*|autofs|fuse*|nsfs|ramfs) continue ;;
        esac
        case "$target" in
            /boot*|/snap*|/run*|/var/lib/docker*) continue ;;
        esac

        echo "$target"
        echo "$source  $fstype  $(human "$avail") $(t free) / $(human "$size")"
    done < <(df -B1 --output=target,source,fstype,size,avail 2>/dev/null | tail -n +2 | sort -u -k1,1)

    lsblk -rpno NAME,FSTYPE,SIZE,MOUNTPOINT,LABEL,TYPE 2>/dev/null | while read -r name fs size mnt label type; do
        [ -n "$fs" ] && [ -z "$mnt" ] || continue
        case "$fs" in ext4|ext3|xfs|btrfs) ;; *) continue ;; esac
        case "$type" in part|disk|lvm) ;; *) continue ;; esac

        echo "mount:$name"
        echo "$(t unmounted): $name  $fs  $size  ${label:-}"
    done
}

choose_location() {
    local items=()
    mapfile -t items < <(disk_menu_items)
    ui_menu "$1" "${items[@]}"
}

# Monta una particion sin montar de forma permanente (por UUID, sin formatear)
mount_partition() {
    local dev="$1" label uuid fs target

    label=$(lsblk -no LABEL "$dev" | head -1 | tr -cd 'A-Za-z0-9_-')
    uuid=$(blkid -s UUID -o value "$dev")
    fs=$(blkid -s TYPE -o value "$dev")
    target=$(ui_input "$(t mount_where)" "/mnt/${label:-$(basename "$dev")}")

    mkdir -p "$target"

    if ! grep -q "$uuid" /etc/fstab; then
        cp -a /etc/fstab "/etc/fstab.bak-mcserver-$(date +%Y%m%d-%H%M%S)"
        echo "UUID=$uuid $target $fs defaults,nofail,x-systemd.device-timeout=10s 0 2" >> /etc/fstab
        systemctl daemon-reload
    fi

    if ! mountpoint -q "$target" && ! mount "$target" 2>/tmp/mcserver-mount.err; then
        ui_msg "$(t mount_fail)\n$(cat /tmp/mcserver-mount.err)"
        cancel
    fi

    echo "$target"
}

folder_under() {
    if [ "$1" = "/" ]; then
        echo "/srv/minecraft/$2"
    else
        echo "${1%/}/minecraft/$2"
    fi
}

if [ "$INTERACTIVE" -eq 1 ]; then

    UI_LANG=$(whiptail --title "MCServer by Derpchees $VERSION" --default-item "$UI_LANG" \
        --menu "Language / Idioma" 12 60 2 en "English" es "Español" 3>&1 1>&2 2>&3) || cancel

    ui_msg "$(t welcome)"

    loc=$(choose_location "$(t data_disk)")
    [[ "$loc" == mount:* ]] && loc=$(mount_partition "${loc#mount:}")
    DATA_ROOT=$(ui_input "$(t folder_data)" "$(folder_under "$loc" servers)")

    loc=$(choose_location "$(t backup_disk)")
    [[ "$loc" == mount:* ]] && loc=$(mount_partition "${loc#mount:}")
    BACKUP_ROOT=$(ui_input "$(t folder_backups)" "$(folder_under "$loc" backups)")

    net_items=("0.0.0.0" "$(t all_networks)")

    while read -r iface addr; do
        case "$iface" in lo|docker*|br-*|veth*) continue ;; esac
        net_items+=("${addr%/*}" "$iface")
    done < <(ip -4 -o addr show | awk '{print $2, $4}')

    LISTEN_IP=$(ui_menu "$(t listen)" "${net_items[@]}")

    while true; do
        PANEL_PORT=$(ui_input "$(t panel_port)" "$PANEL_PORT")
        valid_port "$PANEL_PORT" && port_free "$PANEL_PORT" && break
        ui_msg "$(t port_busy "$PANEL_PORT")"
    done

    while true; do
        GAME_PORT_START=$(ui_input "$(t game_port)" "$GAME_PORT_START")
        valid_port "$GAME_PORT_START" && [ "$GAME_PORT_START" != "$PANEL_PORT" ] && break
        ui_msg "$(t port_busy "$GAME_PORT_START")"
    done

    shown_ip="$LISTEN_IP"
    [ "$shown_ip" = "0.0.0.0" ] && shown_ip="$(primary_ip)"
    PUBLIC_HOST=$(ui_input "$(t address)" "$shown_ip")

    HTTPS=$(ui_menu "$(t https_menu)" \
        duckdns "$(t https_opt_duckdns)" \
        local "$(t https_opt_local)" \
        no "$(t https_opt_no)")

    if [ "$HTTPS" = "duckdns" ]; then
        DUCKDNS_SUBDOMAIN=$(ui_input "$(t https_steps)" "")
        DUCKDNS_TOKEN=$(whiptail --title "$(t title)" --passwordbox "$(t https_token)" 12 78 3>&1 1>&2 2>&3) || cancel
    fi

    if ui_yesno "$(t eula)"; then
        ACCEPT_EULA="yes"
    else
        ui_msg "$(t eula_no)"
        cancel
    fi

    summary="$(t s_servers):   $DATA_ROOT
$(t s_backups):   $BACKUP_ROOT
$(t s_network):       $LISTEN_IP
$(t s_ports):     panel $PANEL_PORT, Minecraft $GAME_PORT_START+
$(t s_address):   $PUBLIC_HOST"

    ui_yesno "$(t summary)\n\n$summary\n\n$(t confirm)" || cancel
    clear

else
    [ "$ACCEPT_EULA" = "yes" ] || die "$(t eula_no) (ACCEPT_EULA=yes)"
    valid_port "$PANEL_PORT" && port_free "$PANEL_PORT" || die "$(t port_busy "$PANEL_PORT")"
    valid_port "$GAME_PORT_START" || die "GAME_PORT_START"
    [ -n "$PUBLIC_HOST" ] || PUBLIC_HOST="$([ "$LISTEN_IP" = "0.0.0.0" ] && primary_ip || echo "$LISTEN_IP")"
fi

# Usuario dueno de los archivos de los mundos: el que corrio sudo, o 1000
MC_UID="${MC_UID:-${SUDO_UID:-1000}}"
MC_GID="${MC_GID:-${SUDO_GID:-1000}}"
[ "$MC_UID" -eq 0 ] && MC_UID=1000 && MC_GID=1000

# Montaje que deben tener los respaldos (si estan en otro disco)
BACKUP_MOUNT=""
backup_parent="$BACKUP_ROOT"
while [ ! -d "$backup_parent" ]; do backup_parent=$(dirname "$backup_parent"); done
backup_mnt=$(findmnt -no TARGET -T "$backup_parent" 2>/dev/null | head -1 || true)
[ -n "$backup_mnt" ] && [ "$backup_mnt" != "/" ] && BACKUP_MOUNT="$backup_mnt"


# ============================================================
# Instalacion
# ============================================================

step() {
    CURRENT_STEP="$1"
    info "$1"
}

trap 'echo; echo "$(t failed) ${CURRENT_STEP:-?}" >&2' ERR

step "$(t step_packages)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# rsync, parted y e2fsprogs: el panel mueve datos y prepara discos (Almacenamiento)
packages="python3 pigz curl whiptail rsync parted e2fsprogs openssl"
command -v docker >/dev/null || packages="$packages docker.io"
# shellcheck disable=SC2086
apt-get install -y -qq $packages >/dev/null
systemctl enable --now docker >/dev/null 2>&1

step "$(t step_files)"
install_files

mkdir -p "$DATA_ROOT" "$BACKUP_ROOT" /var/lib/mcpanel /var/log/mcpanel
chown "$MC_UID:$MC_GID" "$DATA_ROOT" "$BACKUP_ROOT"

{
    echo "# MCServer by Derpchees - generado por install.sh $VERSION el $(date '+%Y-%m-%d %H:%M')"
    echo "# Despues de editarlo: sudo systemctl restart mcpanel-web mcpanel-agent"
    write_config_value SYSTEM_NAME "MCServer"
    write_config_value LANG_DEFAULT "$UI_LANG"
    write_config_value DATA_ROOT "$DATA_ROOT"
    write_config_value BACKUP_ROOT "$BACKUP_ROOT"
    write_config_value BACKUP_MOUNT "$BACKUP_MOUNT"
    write_config_value LISTEN_IP "$LISTEN_IP"
    write_config_value PUBLIC_HOST "$PUBLIC_HOST"
    write_config_value PANEL_PORT "$PANEL_PORT"
    write_config_value PANEL_BIND "$LISTEN_IP"
    write_config_value GAME_PORT_START "$GAME_PORT_START"
    write_config_value INTERNAL_PORT_START "$((GAME_PORT_START + 10000))"
    write_config_value MC_UID "$MC_UID"
    write_config_value MC_GID "$MC_GID"
    write_config_value INSTALL_DIR "$INSTALL_DIR"
} > "$CONFIG"
chmod 644 "$CONFIG"

python3 "$INSTALL_DIR/panel/mcpanel_core.py" init >/dev/null

# Administrador sin pasar por el navegador (solo modo sin preguntas)
if [ -n "$ADMIN_USER" ] && [ -n "$ADMIN_PASSWORD" ]; then
    printf '%s\n' "$ADMIN_PASSWORD" | python3 "$INSTALL_DIR/panel/mcpanel_core.py" create-admin "$ADMIN_USER"
fi

step "$(t step_image)"
docker network inspect mcpanel-net >/dev/null 2>&1 || docker network create mcpanel-net >/dev/null
docker pull -q "$IMAGE:latest" >/dev/null

configure_firewall

step "$(t step_services)"
install_units

trap - ERR

panel_ip="$LISTEN_IP"
[ "$panel_ip" = "0.0.0.0" ] && panel_ip="$(primary_ip)"
url="http://$panel_ip:$PANEL_PORT"

# HTTPS: con datos de DuckDNS, dominio gratis (lo recomendado); si no, CA
# propia. Es lo mismo que Administracion > Acceso seguro.
[ -n "$DUCKDNS_SUBDOMAIN" ] && [ -n "$DUCKDNS_TOKEN" ] && [ "$HTTPS" != "no" ] && HTTPS="duckdns"
[ "$HTTPS" = "yes" ] && HTTPS="local"

if [ "$HTTPS" = "duckdns" ]; then
    step "$(t step_https)"
    if https_url=$(python3 "$INSTALL_DIR/panel/sysadmin/duckdns.py" enable "$DUCKDNS_SUBDOMAIN" "$DUCKDNS_TOKEN" --game 2>/tmp/mcserver-https.err); then
        systemctl restart mcpanel-web
        url="${https_url%/}"
    else
        echo "$(t https_fail)" >&2
        tail -3 /tmp/mcserver-https.err >&2 || true
        HTTPS="local"
    fi
    unset DUCKDNS_TOKEN
fi

if [ "$HTTPS" = "local" ]; then
    step "$(t step_https)"
    if python3 "$INSTALL_DIR/panel/sysadmin/localca.py" enable >/dev/null 2>/tmp/mcserver-https.err; then
        systemctl restart mcpanel-web
        url="https://$panel_ip:$PANEL_PORT"
        echo "$(t https_ca "$url")"
    else
        echo "$(t https_fail)" >&2
        tail -3 /tmp/mcserver-https.err >&2 || true
    fi
fi

[ "$INTERACTIVE" -eq 1 ] && ui_msg "$(t done)\n\n$(t done_body "$url" "$INSTALL_DIR")"

echo
echo "$(t done)"
echo -e "$(t done_body "$url" "$INSTALL_DIR")"
