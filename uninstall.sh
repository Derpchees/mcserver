#!/bin/bash
#
# MCServer by Derpchees - desinstalador
#
#   sudo ./uninstall.sh                     pregunta antes de borrar
#   sudo ./uninstall.sh --yes               sin preguntas (conserva mundo y respaldos)
#   sudo ./uninstall.sh --yes --purge-data --purge-backups
#
# Por defecto conserva el mundo y los respaldos. No desinstala Docker ni
# desmonta discos (las lineas agregadas a /etc/fstab se quedan).
#

set -uo pipefail

CONFIG="/etc/mcpanel/config.env"
ASSUME_YES=0
PURGE_DATA=0
PURGE_BACKUPS=0

for arg in "$@"; do
    case "$arg" in
        --yes|-y) ASSUME_YES=1 ;;
        --purge-data) PURGE_DATA=1 ;;
        --purge-backups) PURGE_BACKUPS=1 ;;
        -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo / Ejecuta con sudo." >&2
    exit 1
fi

CONTAINER="mcpanel-minecraft"
DATA_DIR=""
BACKUP_DIR=""
LANG_DEFAULT="en"

# shellcheck source=/dev/null
[ -f "$CONFIG" ] && . "$CONFIG"

say() {
    if [ "$LANG_DEFAULT" = "es" ]; then echo "$2"; else echo "$1"; fi
}

ask() {
    local answer
    read -r -p "$1 [y/N] " answer </dev/tty
    [[ "$answer" =~ ^[yYsS] ]]
}

if [ "$ASSUME_YES" -eq 0 ]; then
    say "This removes the panel, its services, the Minecraft container and its settings." \
        "Esto quita el panel, sus servicios, el contenedor de Minecraft y su configuración."
    ask "$(say "Continue?" "¿Continuar?")" || exit 1

    if [ -n "$DATA_DIR" ] && ask "$(say "Also DELETE the world and server files in $DATA_DIR?" \
            "¿BORRAR también el mundo y los archivos del servidor en $DATA_DIR?")"; then
        PURGE_DATA=1
    fi

    if [ -n "$BACKUP_DIR" ] && ask "$(say "Also DELETE all backups in $BACKUP_DIR?" \
            "¿BORRAR también todos los respaldos en $BACKUP_DIR?")"; then
        PURGE_BACKUPS=1
    fi
fi

# Nunca borrar rutas peligrosas aunque la configuracion este mal
safe_to_delete() {
    local path
    path=$(realpath -m "$1")

    case "$path" in
        ""|/|/bin*|/boot*|/dev*|/etc*|/home|/lib*|/mnt|/media|/opt|/proc*|/root|/run*|/sbin*|/srv|/sys*|/usr*|/var|/var/lib|/tmp)
            return 1 ;;
    esac

    # Al menos dos niveles de profundidad (ej. /srv/minecraft/server)
    [ "$(echo "$path" | tr -cd '/' | wc -c)" -ge 2 ]
}

echo "==> $(say "Stopping services" "Deteniendo servicios")"

for unit in mcpanel-backup.timer mcpanel-autostop.service mcpanel-proxy.service; do
    systemctl disable --now "$unit" >/dev/null 2>&1 || true
done

systemctl stop 'mcpanel-backup@*.service' >/dev/null 2>&1 || true

echo "==> $(say "Removing the Minecraft container" "Quitando el contenedor de Minecraft")"

if command -v docker >/dev/null; then
    docker stop "$CONTAINER" >/dev/null 2>&1 || true
    docker rm "$CONTAINER" >/dev/null 2>&1 || true
    docker network rm mcpanel-net >/dev/null 2>&1 || true
fi

if [ "$PURGE_DATA" -eq 1 ] && [ -n "$DATA_DIR" ]; then
    if safe_to_delete "$DATA_DIR"; then
        echo "==> $(say "Deleting" "Borrando") $DATA_DIR"
        rm -rf -- "$DATA_DIR"
    else
        say "Skipped unsafe path: $DATA_DIR" "Se omitió una ruta peligrosa: $DATA_DIR"
    fi
fi

if [ "$PURGE_BACKUPS" -eq 1 ] && [ -n "$BACKUP_DIR" ]; then
    if safe_to_delete "$BACKUP_DIR"; then
        echo "==> $(say "Deleting" "Borrando") $BACKUP_DIR"
        rm -rf -- "$BACKUP_DIR"
    else
        say "Skipped unsafe path: $BACKUP_DIR" "Se omitió una ruta peligrosa: $BACKUP_DIR"
    fi
fi

echo "==> $(say "Removing the panel" "Quitando el panel")"

rm -f /etc/systemd/system/mcpanel-web.service \
      /etc/systemd/system/mcpanel-proxy.service \
      /etc/systemd/system/mcpanel-autostop.service \
      /etc/systemd/system/mcpanel-backup@.service \
      /etc/systemd/system/mcpanel-backup.timer \
      /usr/local/bin/mcpanel-passwd
rm -rf /etc/systemd/system/mcpanel-backup@.service.d \
       /etc/mcpanel /var/lib/mcpanel /var/log/mcpanel /run/mcpanel

# El panel se detiene al final: si la desinstalacion se lanzo desde el
# panel, esta corriendo en su propia unidad y no se ve afectada
systemctl disable --now mcpanel-web.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/mcpanel-web.service
rm -rf /opt/mcpanel
systemctl daemon-reload

echo
say "Uninstalled." "Desinstalado."

if [ "$PURGE_DATA" -eq 0 ] && [ -n "$DATA_DIR" ] && [ -d "$DATA_DIR" ]; then
    say "The world was kept in: $DATA_DIR" "El mundo se conservó en: $DATA_DIR"
fi

if [ "$PURGE_BACKUPS" -eq 0 ] && [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
    say "Backups were kept in: $BACKUP_DIR" "Los respaldos se conservaron en: $BACKUP_DIR"
fi

say "Docker and the itzg/minecraft-server image were not removed." \
    "Docker y la imagen itzg/minecraft-server no se quitaron."
