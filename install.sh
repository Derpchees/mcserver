#!/bin/bash
#
# MCServer by Derpchees - instalador
# https://github.com/Derpchees/mcserver
#
# Uso:
#   sudo ./install.sh                     instalacion interactiva
#   sudo ./install.sh --config FILE       sin preguntas (ver examples/answers.env)
#   sudo ./install.sh --update            actualiza el panel, conserva la configuracion
#   sudo ./install.sh --lang es           idioma del instalador (en/es)
#

set -euo pipefail

VERSION="1.0.0"
REPO="Derpchees/mcserver"
INSTALL_DIR="/opt/mcpanel"
CONFIG_DIR="/etc/mcpanel"
CONFIG="$CONFIG_DIR/config.env"
SECRET="$CONFIG_DIR/secret.json"
SYSTEMD_DIR="/etc/systemd/system"
IMAGE="itzg/minecraft-server"

ANSWERS=""
UPDATE_ONLY=0
ASSUME_YES=0
UI_LANG=""

while [ $# -gt 0 ]; do
    case "$1" in
        --config) ANSWERS="$2"; shift 2 ;;
        --update) UPDATE_ONLY=1; shift ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        --lang) UI_LANG="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
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
EN[welcome]="This will install:\n\n- A Minecraft server in Docker (Forge, Fabric, Paper or Vanilla)\n- A web panel: console, chat, players, files, backups, settings and resource monitor\n- On-demand start and automatic shutdown when nobody is playing\n- Scheduled backups\n\nYou can change most options later from the panel."
ES[welcome]="Se instalará:\n\n- Un servidor de Minecraft en Docker (Forge, Fabric, Paper o Vanilla)\n- Un panel web: consola, chat, jugadores, archivos, respaldos, ajustes y monitor de recursos\n- Encendido al conectarse y apagado automático cuando no hay nadie jugando\n- Respaldos programados\n\nLa mayoría de las opciones se pueden cambiar después desde el panel."
EN[existing]="An installation already exists. What do you want to do?"
ES[existing]="Ya hay una instalación. ¿Qué quieres hacer?"
EN[opt_update]="Update the panel (keep settings and world)"
ES[opt_update]="Actualizar el panel (conserva ajustes y mundo)"
EN[opt_reconfig]="Reconfigure from scratch (the world is kept)"
ES[opt_reconfig]="Configurar de nuevo (el mundo se conserva)"
EN[opt_uninstall]="Uninstall"
ES[opt_uninstall]="Desinstalar"
EN[opt_cancel]="Cancel"
ES[opt_cancel]="Cancelar"
EN[name]="Server name (shown in the panel):"
ES[name]="Nombre del servidor (se muestra en el panel):"
EN[data_disk]="Where should the SERVER live (world, mods, configs)?\nA fast disk (SSD) is recommended."
ES[data_disk]="¿Dónde va el SERVIDOR (mundo, mods, configuración)?\nSe recomienda un disco rápido (SSD)."
EN[backup_disk]="Where should the BACKUPS go?\nA different physical disk protects you if the server disk fails."
ES[backup_disk]="¿Dónde van los RESPALDOS?\nUn disco físico distinto te protege si falla el del servidor."
EN[unmounted]="Not mounted"
ES[unmounted]="Sin montar"
EN[free]="free"
ES[free]="libres"
EN[mount_where]="The partition will be mounted permanently (it is NOT formatted).\n\nMount point:"
ES[mount_where]="La partición se montará de forma permanente (NO se formatea).\n\nPunto de montaje:"
EN[mount_fail]="Could not mount the partition:"
ES[mount_fail]="No se pudo montar la partición:"
EN[folder_data]="Folder for the server files:"
ES[folder_data]="Carpeta para los archivos del servidor:"
EN[folder_backups]="Folder for the backups:"
ES[folder_backups]="Carpeta para los respaldos:"
EN[type]="Server type:"
ES[type]="Tipo de servidor:"
EN[type_forge]="Mods (Forge)"
ES[type_forge]="Mods (Forge)"
EN[type_fabric]="Mods (Fabric)"
ES[type_fabric]="Mods (Fabric)"
EN[type_paper]="Plugins, optimized (Paper)"
ES[type_paper]="Plugins, optimizado (Paper)"
EN[type_vanilla]="Official, no mods (Vanilla)"
ES[type_vanilla]="Oficial, sin mods (Vanilla)"
EN[version]="Minecraft version (for example 1.20.1), or LATEST:"
ES[version]="Versión de Minecraft (por ejemplo 1.20.1) o LATEST:"
EN[ram]="RAM for Minecraft in GB.\nThis machine has %s GB. Leave at least 2 GB for the system."
ES[ram]="RAM para Minecraft en GB.\nEste equipo tiene %s GB. Deja al menos 2 GB para el sistema."
EN[ram_bad]="Enter a whole number of GB between 1 and %s."
ES[ram_bad]="Escribe un número entero de GB entre 1 y %s."
EN[cpu]="CPU cores Minecraft may use.\nThis machine has %s. Use 0 for no limit."
ES[cpu]="Núcleos de CPU que puede usar Minecraft.\nEste equipo tiene %s. Usa 0 para no limitar."
EN[cpu_bad]="Enter a number between 0 and %s."
ES[cpu_bad]="Escribe un número entre 0 y %s."
EN[listen]="On which network should the game and the panel be reachable?"
ES[listen]="¿En qué red se podrá entrar al juego y al panel?"
EN[all_networks]="All networks"
ES[all_networks]="Todas las redes"
EN[game_port]="Game port:"
ES[game_port]="Puerto del juego:"
EN[panel_port]="Panel port:"
ES[panel_port]="Puerto del panel:"
EN[port_busy]="Port %s is already in use. Choose another one."
ES[port_busy]="El puerto %s ya está en uso. Elige otro."
EN[address]="Address players will use (shown in the panel):"
ES[address]="Dirección que usarán los jugadores (se muestra en el panel):"
EN[autostop]="Start the server when someone connects and stop it when nobody is playing?\n\nSaves RAM and power. The first connection takes a minute while it starts."
ES[autostop]="¿Encender el servidor cuando alguien se conecte y apagarlo cuando no haya nadie?\n\nAhorra RAM y energía. La primera conexión tarda un minuto mientras arranca."
EN[idle]="Minutes without players before stopping:"
ES[idle]="Minutos sin jugadores antes de apagar:"
EN[backups]="Make an automatic backup every day?"
ES[backups]="¿Hacer un respaldo automático cada día?"
EN[backup_time]="Backup time (24h, HH:MM). Server time zone: %s"
ES[backup_time]="Hora del respaldo (24 h, HH:MM). Zona horaria del servidor: %s"
EN[backup_keep]="How many automatic backups to keep:"
ES[backup_keep]="Cuántos respaldos automáticos conservar:"
EN[password]="Password for the panel (files, console, players, settings).\nAt least 6 characters:"
ES[password]="Contraseña del panel (archivos, consola, jugadores, ajustes).\nMínimo 6 caracteres:"
EN[password2]="Repeat the password:"
ES[password2]="Repite la contraseña:"
EN[password_bad]="The passwords do not match or are shorter than 6 characters."
ES[password_bad]="Las contraseñas no coinciden o tienen menos de 6 caracteres."
EN[eula]="Minecraft requires accepting the Mojang EULA:\nhttps://aka.ms/MinecraftEULA\n\nDo you accept it?"
ES[eula]="Minecraft requiere aceptar el EULA de Mojang:\nhttps://aka.ms/MinecraftEULA\n\n¿Lo aceptas?"
EN[eula_no]="The EULA must be accepted to run a Minecraft server."
ES[eula_no]="Hay que aceptar el EULA para correr un servidor de Minecraft."
EN[summary]="Summary"
ES[summary]="Resumen"
EN[confirm]="Install with these settings?"
ES[confirm]="¿Instalar con estos ajustes?"
EN[cancelled]="Installation cancelled. Nothing was changed."
ES[cancelled]="Instalación cancelada. No se cambió nada."
EN[installing]="Installing"
ES[installing]="Instalando"
EN[step_packages]="Installing packages (Docker, socat, ...)"
ES[step_packages]="Instalando paquetes (Docker, socat, ...)"
EN[step_files]="Copying the panel"
ES[step_files]="Copiando el panel"
EN[step_image]="Downloading the Minecraft image (may take a few minutes)"
ES[step_image]="Descargando la imagen de Minecraft (puede tardar unos minutos)"
EN[step_container]="Creating the Minecraft container"
ES[step_container]="Creando el contenedor de Minecraft"
EN[step_services]="Starting services"
ES[step_services]="Iniciando servicios"
EN[done]="Installation complete!"
ES[done]="¡Instalación completa!"
EN[done_body]="Panel:  %s\nGame:   %s\n\nMinecraft is starting for the first time to create the world; it can take a few minutes (longer with mods).\n\nChange the password:  sudo mcpanel-passwd\nUninstall:            sudo %s/uninstall.sh"
ES[done_body]="Panel:  %s\nJuego:  %s\n\nMinecraft está arrancando por primera vez para crear el mundo; puede tardar unos minutos (más con mods).\n\nCambiar la contraseña:  sudo mcpanel-passwd\nDesinstalar:            sudo %s/uninstall.sh"
EN[updated]="Panel updated to version %s. Settings and world were kept."
ES[updated]="Panel actualizado a la versión %s. Se conservaron los ajustes y el mundo."
EN[no_config]="No existing installation found. Run the installer without --update."
ES[no_config]="No hay una instalación. Corre el instalador sin --update."
EN[failed]="The installation failed at:"
ES[failed]="La instalación falló en:"
EN[download]="Downloading the installer files from GitHub..."
ES[download]="Descargando los archivos del instalador desde GitHub..."
EN[s_name]="Name"
ES[s_name]="Nombre"
EN[s_server]="Server"
ES[s_server]="Servidor"
EN[s_data]="World folder"
ES[s_data]="Carpeta del mundo"
EN[s_backups]="Backups"
ES[s_backups]="Respaldos"
EN[s_resources]="Resources"
ES[s_resources]="Recursos"
EN[s_network]="Network"
ES[s_network]="Red"
EN[s_auto]="Auto stop"
ES[s_auto]="Apagado automático"
EN[s_daily]="daily at"
ES[s_daily]="diario a las"
EN[s_keep]="keep"
ES[s_keep]="conservar"
EN[s_off]="off"
ES[s_off]="desactivado"
EN[s_nolimit]="no CPU limit"
ES[s_nolimit]="sin límite de CPU"
EN[s_cores]="cores"
ES[s_cores]="núcleos"
EN[s_game]="game"
ES[s_game]="juego"


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
    echo -e "\n[mcpanel] $*" >&2
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
    whiptail --title "$(t title)" --msgbox "$1" 20 76 1>&2
}

ui_yesno() {
    whiptail --title "$(t title)" --yesno "$1" 16 76 1>&2
}

ui_input() {
    local result
    result=$(whiptail --title "$(t title)" --inputbox "$1" 12 76 "$2" 3>&1 1>&2 2>&3) || cancel
    echo "$result"
}

ui_password() {
    local result
    result=$(whiptail --title "$(t title)" --passwordbox "$1" 12 76 3>&1 1>&2 2>&3) || cancel
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

# Etiqueta de imagen segun la version de Minecraft (Java necesario)
java_tag() {
    local version="$1" minor

    if [[ "$version" =~ ^1\.([0-9]+) ]]; then
        minor="${BASH_REMATCH[1]}"

        if [ "$minor" -lt 17 ]; then echo "java8"
        elif [ "$minor" -eq 17 ]; then echo "java16"
        elif [ "$minor" -le 20 ] && [[ ! "$version" =~ ^1\.20\.[5-9] ]]; then echo "java17"
        else echo "latest"
        fi
    else
        echo "latest"
    fi
}

write_config_value() {
    # Valor entre comillas dobles, escapando lo necesario para bash
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

. /etc/os-release 2>/dev/null || true

if ! command -v apt-get >/dev/null || [[ ! " ${ID:-} ${ID_LIKE:-} " =~ (debian|ubuntu) ]]; then
    die "$(t bad_os) ${PRETTY_NAME:-?}"
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
# Instalacion de archivos y servicios (comun a todos los modos)
# ============================================================

install_files() {
    mkdir -p "$INSTALL_DIR/panel" "$INSTALL_DIR/bin" "$CONFIG_DIR"

    install -m 755 "$SRC/panel/mcpanel.py" "$INSTALL_DIR/panel/mcpanel.py"

    for f in "$SRC"/bin/*; do
        install -m 755 "$f" "$INSTALL_DIR/bin/$(basename "$f")"
    done

    install -m 755 "$SRC/uninstall.sh" "$INSTALL_DIR/uninstall.sh"
    echo "$VERSION" > "$INSTALL_DIR/VERSION"
    ln -sf "$INSTALL_DIR/bin/mcpanel-passwd" /usr/local/bin/mcpanel-passwd
}

install_units() {
    # Usa los valores de $CONFIG
    # shellcheck source=/dev/null
    . "$CONFIG"

    for unit in mcpanel-web.service mcpanel-proxy.service mcpanel-autostop.service \
                mcpanel-backup@.service mcpanel-backup.timer; do
        install -m 644 "$SRC/systemd/$unit" "$SYSTEMD_DIR/$unit"
    done

    sed -i "s|@BACKUP_CALENDAR@|*-*-* ${BACKUP_TIME:-04:00}:00|" "$SYSTEMD_DIR/mcpanel-backup.timer"

    # Si los respaldos estan en otro disco, el servicio espera a que este montado
    rm -rf "$SYSTEMD_DIR/mcpanel-backup@.service.d"

    if [ -n "${BACKUP_MOUNT:-}" ]; then
        mkdir -p "$SYSTEMD_DIR/mcpanel-backup@.service.d"
        printf '[Unit]\nRequiresMountsFor=%s\n' "$BACKUP_MOUNT" \
            > "$SYSTEMD_DIR/mcpanel-backup@.service.d/mount.conf"
    fi

    systemctl daemon-reload

    systemctl enable --now mcpanel-web.service mcpanel-proxy.service >/dev/null 2>&1
    systemctl restart mcpanel-web.service mcpanel-proxy.service

    if [ "${AUTOSTOP:-yes}" = "yes" ]; then
        systemctl enable --now mcpanel-autostop.service >/dev/null 2>&1
        systemctl restart mcpanel-autostop.service
    else
        systemctl disable --now mcpanel-autostop.service >/dev/null 2>&1 || true
    fi

    if [ "${BACKUPS:-yes}" = "yes" ]; then
        systemctl enable --now mcpanel-backup.timer >/dev/null 2>&1
        systemctl restart mcpanel-backup.timer
    else
        systemctl disable --now mcpanel-backup.timer >/dev/null 2>&1 || true
    fi
}


# ============================================================
# Modo actualizacion
# ============================================================

if [ "$UPDATE_ONLY" -eq 1 ]; then
    [ -f "$CONFIG" ] || die "$(t no_config)"
    install_files
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

# Valores por defecto
SERVER_NAME="Minecraft Server"
TYPE="PAPER"
MC_VERSION="LATEST"
TOTAL_GB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 ))
CORES=$(nproc)
MAX_GB=$(( TOTAL_GB > 6 ? TOTAL_GB * 3 / 4 : (TOTAL_GB > 3 ? TOTAL_GB - 2 : 1) ))
[ "$MAX_GB" -gt 16 ] && MAX_GB=16
CPU_LIMIT=0
LISTEN_IP="0.0.0.0"
GAME_PORT=25565
PANEL_PORT=8090
AUTOSTOP="yes"
IDLE_MINUTES=10
BACKUPS="yes"
BACKUP_TIME="04:00"
BACKUP_KEEP_AUTO=3
DATA_DIR="/srv/minecraft/server"
BACKUP_DIR="/srv/minecraft/backups"
PASSWORD=""
ACCEPT_EULA="no"
PUBLIC_ADDRESS=""

# Archivo de respuestas (modo sin preguntas)
if [ -n "$ANSWERS" ]; then
    [ -f "$ANSWERS" ] || die "No existe $ANSWERS"
    # shellcheck source=/dev/null
    . "$ANSWERS"
    MC_VERSION="${VERSION_MC:-$MC_VERSION}"
fi

primary_ip() {
    { ip -4 route get 1.1.1.1 2>/dev/null || true; } | awk '{for (i=1; i<NF; i++) if ($i=="src") print $(i+1)}' | head -1
}

# Lista de lugares posibles: sistemas de archivos montados y particiones sin montar
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

    # Particiones con sistema de archivos pero sin montar
    lsblk -rpno NAME,FSTYPE,SIZE,MOUNTPOINT,LABEL,TYPE 2>/dev/null | while read -r name fs size mnt label type; do
        [ -n "$fs" ] && [ -z "$mnt" ] || continue
        case "$fs" in ext4|ext3|xfs|btrfs) ;; *) continue ;; esac
        case "$type" in part|disk|lvm) ;; *) continue ;; esac

        echo "mount:$name"
        echo "$(t unmounted): $name  $fs  $size  ${label:-}"
    done
}

choose_location() {
    local prompt="$1" extra_tag="${2:-}" extra_label="${3:-}"
    local items=()

    mapfile -t items < <(disk_menu_items)

    if [ -n "$extra_tag" ]; then
        items=("$extra_tag" "$extra_label" "${items[@]}")
    fi

    ui_menu "$prompt" "${items[@]}"
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
        cp -a /etc/fstab "/etc/fstab.bak-mcpanel-$(date +%Y%m%d-%H%M%S)"
        echo "UUID=$uuid $target $fs defaults,nofail,x-systemd.device-timeout=10s 0 2" >> /etc/fstab
        systemctl daemon-reload
    fi

    if ! mountpoint -q "$target" && ! mount "$target" 2>/tmp/mcpanel-mount.err; then
        ui_msg "$(t mount_fail)\n$(cat /tmp/mcpanel-mount.err)"
        cancel
    fi

    echo "$target"
}

folder_under() {
    local mount="$1" sub="$2"

    if [ "$mount" = "/" ]; then
        echo "/srv/minecraft/$sub"
    else
        echo "${mount%/}/minecraft/$sub"
    fi
}

if [ "$INTERACTIVE" -eq 1 ]; then

    UI_LANG=$(whiptail --title "MCServer by Derpchees $VERSION" --default-item "$UI_LANG" \
        --menu "Language / Idioma" 12 60 2 en "English" es "Español" 3>&1 1>&2 2>&3) || cancel

    ui_msg "$(t welcome)"

    SERVER_NAME=$(ui_input "$(t name)" "$SERVER_NAME")
    [ -n "$SERVER_NAME" ] || SERVER_NAME="Minecraft Server"

    # Disco del servidor
    loc=$(choose_location "$(t data_disk)")
    [[ "$loc" == mount:* ]] && loc=$(mount_partition "${loc#mount:}")
    DATA_MOUNT="$loc"
    DATA_DIR=$(ui_input "$(t folder_data)" "$(folder_under "$loc" server)")

    # Disco de respaldos
    loc=$(choose_location "$(t backup_disk)")
    [[ "$loc" == mount:* ]] && loc=$(mount_partition "${loc#mount:}")
    BACKUP_DIR=$(ui_input "$(t folder_backups)" "$(folder_under "$loc" backups)")

    # Tipo y version
    TYPE=$(ui_menu "$(t type)" \
        FORGE "$(t type_forge)" \
        FABRIC "$(t type_fabric)" \
        PAPER "$(t type_paper)" \
        VANILLA "$(t type_vanilla)")
    MC_VERSION=$(ui_input "$(t version)" "$MC_VERSION")
    [ -n "$MC_VERSION" ] || MC_VERSION="LATEST"

    # Recursos
    while true; do
        MAX_GB=$(ui_input "$(t ram "$TOTAL_GB")" "$MAX_GB")
        [[ "$MAX_GB" =~ ^[0-9]+$ ]] && [ "$MAX_GB" -ge 1 ] && [ "$MAX_GB" -le "$TOTAL_GB" ] && break
        ui_msg "$(t ram_bad "$TOTAL_GB")"
    done

    while true; do
        CPU_LIMIT=$(ui_input "$(t cpu "$CORES")" "$CPU_LIMIT")
        [[ "$CPU_LIMIT" =~ ^[0-9]+$ ]] && [ "$CPU_LIMIT" -le "$CORES" ] && break
        ui_msg "$(t cpu_bad "$CORES")"
    done

    # Red
    net_items=("0.0.0.0" "$(t all_networks)")

    while read -r iface addr; do
        case "$iface" in lo|docker*|br-*|veth*) continue ;; esac
        net_items+=("${addr%/*}" "$iface")
    done < <(ip -4 -o addr show | awk '{print $2, $4}')

    LISTEN_IP=$(ui_menu "$(t listen)" "${net_items[@]}")

    while true; do
        GAME_PORT=$(ui_input "$(t game_port)" "$GAME_PORT")
        valid_port "$GAME_PORT" && port_free "$GAME_PORT" && break
        ui_msg "$(t port_busy "$GAME_PORT")"
    done

    while true; do
        PANEL_PORT=$(ui_input "$(t panel_port)" "$PANEL_PORT")
        valid_port "$PANEL_PORT" && port_free "$PANEL_PORT" && [ "$PANEL_PORT" != "$GAME_PORT" ] && break
        ui_msg "$(t port_busy "$PANEL_PORT")"
    done

    shown_ip="$LISTEN_IP"
    [ "$shown_ip" = "0.0.0.0" ] && shown_ip="$(primary_ip)"
    PUBLIC_ADDRESS=$(ui_input "$(t address)" "$shown_ip:$GAME_PORT")

    # Apagado automatico
    if ui_yesno "$(t autostop)"; then
        AUTOSTOP="yes"
        IDLE_MINUTES=$(ui_input "$(t idle)" "$IDLE_MINUTES")
        [[ "$IDLE_MINUTES" =~ ^[0-9]+$ ]] && [ "$IDLE_MINUTES" -ge 1 ] || IDLE_MINUTES=10
    else
        AUTOSTOP="no"
    fi

    # Respaldos
    if ui_yesno "$(t backups)"; then
        BACKUPS="yes"
        tz=$(timedatectl show -p Timezone --value 2>/dev/null || echo UTC)

        while true; do
            BACKUP_TIME=$(ui_input "$(t backup_time "$tz")" "$BACKUP_TIME")
            [[ "$BACKUP_TIME" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] && break
        done

        BACKUP_KEEP_AUTO=$(ui_input "$(t backup_keep)" "$BACKUP_KEEP_AUTO")
        [[ "$BACKUP_KEEP_AUTO" =~ ^[0-9]+$ ]] && [ "$BACKUP_KEEP_AUTO" -ge 1 ] || BACKUP_KEEP_AUTO=3
    else
        BACKUPS="no"
    fi

    # Contrasena
    while true; do
        PASSWORD=$(ui_password "$(t password)")
        again=$(ui_password "$(t password2)")
        [ "$PASSWORD" = "$again" ] && [ "${#PASSWORD}" -ge 6 ] && break
        ui_msg "$(t password_bad)"
    done

    # EULA
    if ui_yesno "$(t eula)"; then
        ACCEPT_EULA="yes"
    else
        ui_msg "$(t eula_no)"
        cancel
    fi

    # Resumen
    cpu_text="$(t s_nolimit)"
    [ "$CPU_LIMIT" -gt 0 ] && cpu_text="$CPU_LIMIT $(t s_cores)"

    backup_text="$(t s_off)"
    [ "$BACKUPS" = "yes" ] && backup_text="$BACKUP_DIR\n               $(t s_daily) $BACKUP_TIME, $(t s_keep) $BACKUP_KEEP_AUTO"

    auto_text="$(t s_off)"
    [ "$AUTOSTOP" = "yes" ] && auto_text="$IDLE_MINUTES min"

    summary="$(t s_name):      $SERVER_NAME
$(t s_server):    $TYPE $MC_VERSION
$(t s_data):    $DATA_DIR
$(t s_backups):    $backup_text
$(t s_resources):  ${MAX_GB} GB RAM, $cpu_text
$(t s_network):       $LISTEN_IP  ($(t s_game) $GAME_PORT, panel $PANEL_PORT)
$(t s_auto):  $auto_text"

    ui_yesno "$(t summary)\n\n$summary\n\n$(t confirm)" || cancel
    clear

else
    # Validaciones del modo sin preguntas
    [ "$ACCEPT_EULA" = "yes" ] || die "$(t eula_no) (ACCEPT_EULA=yes)"
    [ "${#PASSWORD}" -ge 6 ] || die "$(t password_bad) (PASSWORD)"
    valid_port "$GAME_PORT" && port_free "$GAME_PORT" || die "$(t port_busy "$GAME_PORT")"
    valid_port "$PANEL_PORT" && port_free "$PANEL_PORT" || die "$(t port_busy "$PANEL_PORT")"
    [ -n "$PUBLIC_ADDRESS" ] || PUBLIC_ADDRESS="$([ "$LISTEN_IP" = "0.0.0.0" ] && primary_ip || echo "$LISTEN_IP"):$GAME_PORT"
fi

TYPE=$(echo "$TYPE" | tr '[:lower:]' '[:upper:]')

case "$TYPE" in
    FORGE|FABRIC|PAPER|VANILLA) ;;
    *) die "TYPE: FORGE, FABRIC, PAPER, VANILLA" ;;
esac

INIT_GB=$(( MAX_GB / 2 ))
[ "$INIT_GB" -lt 1 ] && INIT_GB=1

# Usuario dueno de los archivos del mundo: el que corrio sudo, o 1000
MC_UID="${MC_UID:-${SUDO_UID:-1000}}"
MC_GID="${MC_GID:-${SUDO_GID:-1000}}"
[ "$MC_UID" -eq 0 ] && MC_UID=1000 && MC_GID=1000

# Montaje que deben tener los respaldos (si estan en otro disco)
BACKUP_MOUNT=""
backup_parent="$BACKUP_DIR"
while [ ! -d "$backup_parent" ]; do backup_parent=$(dirname "$backup_parent"); done
backup_mnt=$(findmnt -no TARGET -T "$backup_parent" 2>/dev/null | head -1 || true)
[ -n "$backup_mnt" ] && [ "$backup_mnt" != "/" ] && BACKUP_MOUNT="$backup_mnt"

CONTAINER="${CONTAINER:-mcpanel-minecraft}"
MC_INTERNAL_PORT="${MC_INTERNAL_PORT:-25566}"


# ============================================================
# Instalacion
# ============================================================

step() {
    CURRENT_STEP="$1"
    info "$1"
}

trap 'echo; echo "$(t failed) ${CURRENT_STEP:-?}" >&2' ERR
set -e

step "$(t step_packages)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
packages="socat netcat-openbsd jq pigz python3 curl whiptail"
command -v docker >/dev/null || packages="$packages docker.io"
# shellcheck disable=SC2086
apt-get install -y -qq $packages >/dev/null
systemctl enable --now docker >/dev/null 2>&1

step "$(t step_files)"
install_files

mkdir -p "$DATA_DIR" "$BACKUP_DIR" /var/lib/mcpanel /var/log/mcpanel
chown "$MC_UID:$MC_GID" "$DATA_DIR" "$BACKUP_DIR"

{
    echo "# MCServer by Derpchees - generado por install.sh $VERSION el $(date '+%Y-%m-%d %H:%M')"
    echo "# Despues de editarlo: sudo systemctl restart mcpanel-web mcpanel-proxy mcpanel-autostop"
    write_config_value SERVER_NAME "$SERVER_NAME"
    write_config_value LANG_DEFAULT "$UI_LANG"
    write_config_value CONTAINER "$CONTAINER"
    write_config_value TYPE "$TYPE"
    write_config_value VERSION_MC "$MC_VERSION"
    write_config_value MAX_GB "$MAX_GB"
    write_config_value CPU_LIMIT "$CPU_LIMIT"
    write_config_value DATA_DIR "$DATA_DIR"
    write_config_value BACKUP_DIR "$BACKUP_DIR"
    write_config_value BACKUP_MOUNT "$BACKUP_MOUNT"
    write_config_value BACKUPS "$BACKUPS"
    write_config_value BACKUP_TIME "$BACKUP_TIME"
    write_config_value BACKUP_KEEP_AUTO "$BACKUP_KEEP_AUTO"
    write_config_value LISTEN_IP "$LISTEN_IP"
    write_config_value GAME_PORT "$GAME_PORT"
    write_config_value MC_INTERNAL_PORT "$MC_INTERNAL_PORT"
    write_config_value PANEL_PORT "$PANEL_PORT"
    write_config_value PANEL_BIND "$LISTEN_IP"
    write_config_value PUBLIC_ADDRESS "$PUBLIC_ADDRESS"
    write_config_value AUTOSTOP "$AUTOSTOP"
    write_config_value IDLE_MINUTES "$IDLE_MINUTES"
    write_config_value MC_UID "$MC_UID"
    write_config_value MC_GID "$MC_GID"
    write_config_value INSTALL_DIR "$INSTALL_DIR"
    write_config_value SECRET_FILE "$SECRET"
} > "$CONFIG"
chmod 644 "$CONFIG"

printf '%s\n' "$PASSWORD" | "$INSTALL_DIR/bin/mcpanel-passwd" --stdin >/dev/null

step "$(t step_image)"
tag=$(java_tag "$MC_VERSION")
docker pull -q "$IMAGE:$tag" >/dev/null

step "$(t step_container)"
docker network inspect mcpanel-net >/dev/null 2>&1 || docker network create mcpanel-net >/dev/null

if docker inspect "$CONTAINER" >/dev/null 2>&1; then
    docker rm -f "$CONTAINER" >/dev/null
fi

run_args=(
    --name "$CONTAINER"
    --network mcpanel-net
    -p "127.0.0.1:$MC_INTERNAL_PORT:25565"
    -v "$DATA_DIR:/data"
    -e EULA=TRUE
    -e "TYPE=$TYPE"
    -e "VERSION=$MC_VERSION"
    -e "INIT_MEMORY=${INIT_GB}G"
    -e "MAX_MEMORY=${MAX_GB}G"
    -e "UID=$MC_UID"
    -e "GID=$MC_GID"
    -e "TZ=$(timedatectl show -p Timezone --value 2>/dev/null || echo UTC)"
    -e "MOTD=$SERVER_NAME"
    --stop-timeout 60
)

[ "$TYPE" = "PAPER" ] && run_args+=(-e USE_AIKAR_FLAGS=true)
[ "$CPU_LIMIT" -gt 0 ] && run_args+=(--cpus "$CPU_LIMIT")

# Sin apagado automatico, Minecraft queda siempre encendido
if [ "$AUTOSTOP" = "yes" ]; then
    run_args+=(--restart no)
else
    run_args+=(--restart unless-stopped)
fi

docker create "${run_args[@]}" "$IMAGE:$tag" >/dev/null

step "$(t step_services)"
install_units

# Primer arranque: descarga el servidor y crea el mundo
docker start "$CONTAINER" >/dev/null

trap - ERR

panel_ip="$LISTEN_IP"
[ "$panel_ip" = "0.0.0.0" ] && panel_ip="$(primary_ip)"

if [ "$INTERACTIVE" -eq 1 ]; then
    ui_msg "$(t done)\n\n$(t done_body "http://$panel_ip:$PANEL_PORT" "$PUBLIC_ADDRESS" "$INSTALL_DIR")"
fi

echo
echo "$(t done)"
echo -e "$(t done_body "http://$panel_ip:$PANEL_PORT" "$PUBLIC_ADDRESS" "$INSTALL_DIR")"
