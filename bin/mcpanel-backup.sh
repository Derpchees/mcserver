#!/bin/bash
#
# Respaldo de un servidor de Minecraft
#
#   mcpanel-backup.sh <servidor> auto    respaldo programado; conserva BACKUP_KEEP_AUTO
#   mcpanel-backup.sh <servidor> manual  respaldo manual; se conserva hasta borrarlo
#
# Si Minecraft esta encendido se pausa el guardado (save-off; en Bedrock
# save hold) mientras se copia, para que el mundo quede consistente.
#

# El codigo esta junto a este script (normalmente /opt/mcpanel)
INSTALL_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
CORE="$INSTALL_DIR/panel/mcpanel_core.py"
ANNOUNCE="$INSTALL_DIR/panel/announce.py"
SLUG="${1:-}"
TYPE="${2:-manual}"

if [ -z "$SLUG" ] || { [ "$TYPE" != "auto" ] && [ "$TYPE" != "manual" ]; }; then
    echo "Uso: $0 <servidor> auto|manual" >&2
    exit 2
fi

# Rutas del servidor (las escribe el panel)
ENV_FILE=$(python3 "$CORE" server-env "$SLUG") || { echo "No existe el servidor $SLUG" >&2; exit 1; }
# shellcheck source=/dev/null
. "$ENV_FILE"

KEEP="${BACKUP_KEEP_AUTO:-3}"
LOG="$LOG_DIR/backup.log"
LOCK="$RUN_DIR/$SLUG.backup.lock"

mkdir -p "$LOG_DIR" "$RUN_DIR"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | $TYPE | $1" | tee -a "$LOG"
}

event() {
    python3 "$CORE" event "$SLUG" "$1" "$2" "$3" 2>/dev/null || true
}

rcon() {
    docker exec "$CONTAINER" rcon-cli "$@" >/dev/null 2>&1
}

# Bedrock no tiene RCON: los comandos van a su consola con send-command
bedrock() {
    docker exec --privileged "$CONTAINER" send-command "$@" >/dev/null 2>&1
}

# Pausa el guardado y espera a que los archivos se puedan copiar
pause_saving() {
    if [ "${EDITION:-java}" != "bedrock" ]; then
        rcon save-off || return 1
        rcon save-all flush
        sleep 5
        return 0
    fi

    local since
    since=$(date +%s)
    bedrock save hold || return 1

    for _ in $(seq 1 30); do
        sleep 2
        bedrock save query
        docker logs --since "$since" "$CONTAINER" 2>&1 | grep -q "ready to be copied" && return 0
    done

    return 0
}

resume_saving() {
    if [ "${EDITION:-java}" = "bedrock" ]; then
        bedrock save resume
    else
        rcon save-on
    fi
}

# Aviso en el chat del juego (solo si el servidor esta encendido)
announce() {
    python3 "$ANNOUNCE" "$SLUG" "$1" >/dev/null 2>&1 || true
}

fail() {
    log "ERROR | $1"
    event backup_failed error "$1"
    [ "${announced:-0}" -eq 1 ] && announce backup_failed
    exit 1
}

exec 9>"$LOCK"
flock -n 9 || { log "YA HAY UN RESPALDO EN CURSO | cancelado"; exit 1; }

# Si los respaldos van en otro disco y no esta montado, no se escribe
# en la carpeta vacia del disco del sistema
if [ -n "$BACKUP_MOUNT" ] && ! mountpoint -q "$BACKUP_MOUNT"; then
    fail "$BACKUP_MOUNT no está montado"
fi

mkdir -p "$BACKUP_DIR"

stamp=$(date '+%Y%m%d-%H%M%S')
final="$BACKUP_DIR/mc-$TYPE-$stamp.tar.gz"
tmp="$final.partial"
saving_off=0

cleanup() {
    [ "$saving_off" -eq 1 ] && resume_saving
    rm -f "$tmp"
}

trap cleanup EXIT

announced=0

if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ]; then
    announce backup_start
    announced=1

    if pause_saving; then
        saving_off=1
        log "INICIANDO | Minecraft encendido, guardado pausado"
    else
        log "INICIANDO | no se pudo pausar el guardado, se respalda igual"
    fi
else
    log "INICIANDO | Minecraft apagado"
fi

start=$(date +%s)
compressor="gzip -6"
command -v pigz >/dev/null && compressor="pigz -6"

tar \
    --use-compress-program="$compressor" \
    --exclude="$(basename "$DATA_DIR")/.cache" \
    --exclude="$(basename "$DATA_DIR")/bedrock_server-*" \
    -cf "$tmp" \
    -C "$(dirname "$DATA_DIR")" \
    "$(basename "$DATA_DIR")"

status=$?

if [ "$saving_off" -eq 1 ]; then
    resume_saving
    saving_off=0
fi

# tar devuelve 1 si algun archivo cambio durante la copia (logs);
# el respaldo sigue siendo valido
[ "$status" -gt 1 ] && fail "tar terminó con código $status"

mv -f "$tmp" "$final"
chown "${MC_UID:-1000}:${MC_GID:-1000}" "$final" 2>/dev/null

size=$(du -h "$final" | cut -f1)
log "COMPLETADO | $(basename "$final") | $size | $(( $(date +%s) - start ))s"
event backup_ok success "$size"
[ "$announced" -eq 1 ] && announce backup_done

# Solo se conservan los KEEP respaldos automaticos mas recientes
if [ "$TYPE" = "auto" ]; then
    ls -1t "$BACKUP_DIR"/mc-auto-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
        rm -f "$old"
        log "BORRADO RESPALDO ANTERIOR | $(basename "$old")"
    done
fi

exit 0
