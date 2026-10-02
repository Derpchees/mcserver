#!/bin/bash
#
# MCServer by Derpchees - desinstalador
#
#   sudo ./uninstall.sh                     pregunta antes de borrar
#   sudo ./uninstall.sh --yes               sin preguntas (conserva mundos y respaldos)
#   sudo ./uninstall.sh --yes --purge-data --purge-backups
#
# Por defecto conserva los mundos y los respaldos de todos los servidores.
# No desinstala Docker ni desmonta discos (las lineas de /etc/fstab se quedan).
#

set -uo pipefail

CONFIG="/etc/mcpanel/config.env"
CORE="/opt/mcpanel/panel/mcpanel_core.py"
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

DATA_ROOT=""
BACKUP_ROOT=""
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

# Carpetas de cada servidor (los importados pueden estar fuera de las raices)
SERVER_DIRS=()
BACKUP_DIRS=()

if [ -f "$CORE" ]; then
    while IFS='|' read -r data backups; do
        [ -n "$data" ] && SERVER_DIRS+=("$data")
        [ -n "$backups" ] && BACKUP_DIRS+=("$backups")
    done < <(python3 - "$CORE" <<'PY' 2>/dev/null
import sys, importlib.util
spec = importlib.util.spec_from_file_location("core", sys.argv[1])
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
for srv in core.list_servers():
    print("%s|%s" % (srv.data_dir, srv.backup_dir))
PY
)
fi

if [ "$ASSUME_YES" -eq 0 ]; then
    say "This removes MCServer: the panel, the agent, every Minecraft container, all accounts and the settings." \
        "Esto quita MCServer: el panel, el agente, todos los contenedores de Minecraft, las cuentas y la configuración."
    ask "$(say "Continue?" "¿Continuar?")" || exit 1

    ask "$(say "Also DELETE every world and server file (${#SERVER_DIRS[@]} servers)?" \
            "¿BORRAR también todos los mundos y archivos de los servidores (${#SERVER_DIRS[@]} servidores)?")" && PURGE_DATA=1

    ask "$(say "Also DELETE every backup?" "¿BORRAR también todos los respaldos?")" && PURGE_BACKUPS=1
fi

# Nunca borrar rutas peligrosas aunque la configuracion este mal
safe_to_delete() {
    local path
    path=$(realpath -m "$1")

    case "$path" in
        ""|/|/bin*|/boot*|/dev*|/etc*|/home|/lib*|/mnt|/media|/opt|/proc*|/root|/run*|/sbin*|/srv|/sys*|/usr*|/var|/var/lib|/tmp)
            return 1 ;;
    esac

    [ "$(echo "$path" | tr -cd '/' | wc -c)" -ge 2 ]
}

delete_dir() {
    if safe_to_delete "$1"; then
        echo "==> $(say "Deleting" "Borrando") $1"
        rm -rf -- "$1"
    else
        say "Skipped unsafe path: $1" "Se omitió una ruta peligrosa: $1"
    fi
}

echo "==> $(say "Stopping services" "Deteniendo servicios")"

systemctl disable --now mcpanel-agent.service >/dev/null 2>&1 || true
systemctl stop 'mcpanel-backup-*' >/dev/null 2>&1 || true

echo "==> $(say "Removing the Minecraft containers" "Quitando los contenedores de Minecraft")"

if command -v docker >/dev/null; then
    for container in $(docker ps -aq --filter label=mcpanel.server); do
        docker stop "$container" >/dev/null 2>&1 || true
        docker rm "$container" >/dev/null 2>&1 || true
    done
    docker network rm mcpanel-net >/dev/null 2>&1 || true
fi

if [ "$PURGE_DATA" -eq 1 ]; then
    for dir in "${SERVER_DIRS[@]}"; do delete_dir "$dir"; done
    [ -n "$DATA_ROOT" ] && [ -d "$DATA_ROOT" ] && delete_dir "$DATA_ROOT"
fi

if [ "$PURGE_BACKUPS" -eq 1 ]; then
    for dir in "${BACKUP_DIRS[@]}"; do delete_dir "$dir"; done
    [ -n "$BACKUP_ROOT" ] && [ -d "$BACKUP_ROOT" ] && delete_dir "$BACKUP_ROOT"
fi

echo "==> $(say "Removing MCServer" "Quitando MCServer")"

# Reglas de firewall que agrego el instalador
if [ -f /etc/mcpanel/ufw-rules ] && command -v ufw >/dev/null; then
    while read -r rule; do
        # shellcheck disable=SC2086
        [ -n "$rule" ] && ufw delete allow $rule >/dev/null 2>&1
    done < /etc/mcpanel/ufw-rules
fi


rm -f /etc/systemd/system/mcpanel-agent.service /usr/local/bin/mcpanel-passwd
rm -rf /etc/mcpanel /var/lib/mcpanel /var/log/mcpanel /run/mcpanel

# El panel se detiene al final: si la desinstalacion se lanzo desde el
# panel, esta corriendo en su propia unidad y no se ve afectada
systemctl disable --now mcpanel-web.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/mcpanel-web.service
rm -rf /opt/mcpanel
systemctl daemon-reload

echo
say "Uninstalled." "Desinstalado."

[ "$PURGE_DATA" -eq 0 ] && [ "${#SERVER_DIRS[@]}" -gt 0 ] && \
    say "The worlds were kept in: ${SERVER_DIRS[*]}" "Los mundos se conservaron en: ${SERVER_DIRS[*]}"
[ "$PURGE_BACKUPS" -eq 0 ] && [ -n "$BACKUP_ROOT" ] && [ -d "$BACKUP_ROOT" ] && \
    say "Backups were kept in: $BACKUP_ROOT" "Los respaldos se conservaron en: $BACKUP_ROOT"

say "Docker and the itzg/minecraft-server image were not removed." \
    "Docker y la imagen itzg/minecraft-server no se quitaron."
