#!/bin/bash
#
# Respaldo del servidor de Minecraft
#
#   mcpanel-backup.sh auto    -> respaldo programado; conserva BACKUP_KEEP_AUTO
#   mcpanel-backup.sh manual  -> respaldo manual; se conserva hasta borrarlo
#
# Si Minecraft esta encendido se pausa el guardado (save-off) mientras
# se copia, para que el mundo quede consistente.
#

. /opt/mcpanel/bin/mcpanel-common.sh

TYPE="${1:-manual}"
KEEP="${BACKUP_KEEP_AUTO:-1}"
LOG="$LOG_DIR/backup.log"
LOCK="$RUN_DIR/backup.lock"

if [ "$TYPE" != "auto" ] && [ "$TYPE" != "manual" ]; then
    echo "Uso: $0 auto|manual" >&2
    exit 2
fi

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | $TYPE | $1" | tee -a "$LOG"
}

exec 9>"$LOCK"

if ! flock -n 9; then
    log "YA HAY UN RESPALDO EN CURSO | cancelado"
    exit 1
fi

# Si los respaldos van en otro disco y no esta montado, no se escribe
# en la carpeta vacia del disco del sistema
if [ -n "$BACKUP_MOUNT" ] && ! mountpoint -q "$BACKUP_MOUNT"; then
    log "ERROR | $BACKUP_MOUNT no está montado"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

stamp=$(date '+%Y%m%d-%H%M%S')
final="$BACKUP_DIR/mc-$TYPE-$stamp.tar.gz"
tmp="$final.partial"
saving_off=0

cleanup() {
    [ "$saving_off" -eq 1 ] && mc_rcon save-on >/dev/null
    rm -f "$tmp"
}

trap cleanup EXIT

if mc_running; then
    if mc_rcon save-off >/dev/null; then
        saving_off=1
        mc_rcon save-all flush >/dev/null
        sleep 5
        log "INICIANDO | Minecraft encendido, guardado pausado"
    else
        log "INICIANDO | no se pudo pausar el guardado, se respalda igual"
    fi
else
    log "INICIANDO | Minecraft apagado"
fi

start=$(date +%s)

if command -v pigz >/dev/null; then
    compressor="pigz -6"
else
    compressor="gzip -6"
fi

tar \
    --use-compress-program="$compressor" \
    --exclude="$(basename "$DATA_DIR")/.cache" \
    -cf "$tmp" \
    -C "$(dirname "$DATA_DIR")" \
    "$(basename "$DATA_DIR")"

status=$?

if [ "$saving_off" -eq 1 ]; then
    mc_rcon save-on >/dev/null
    saving_off=0
fi

# tar devuelve 1 si algun archivo cambio durante la copia (logs);
# el respaldo sigue siendo valido
if [ "$status" -gt 1 ]; then
    log "ERROR | tar terminó con código $status"
    exit 1
fi

mv -f "$tmp" "$final"
chown "${MC_UID:-1000}:${MC_GID:-1000}" "$final" 2>/dev/null

log "COMPLETADO | $(basename "$final") | $(du -h "$final" | cut -f1) | $(( $(date +%s) - start ))s"

# Solo se conservan los KEEP respaldos automaticos mas recientes
if [ "$TYPE" = "auto" ]; then
    ls -1t "$BACKUP_DIR"/mc-auto-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
        rm -f "$old"
        log "BORRADO RESPALDO ANTERIOR | $(basename "$old")"
    done
fi

exit 0
