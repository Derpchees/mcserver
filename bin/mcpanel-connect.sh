#!/bin/bash
#
# Atiende una conexion del proxy: enciende Minecraft si hace falta y
# conecta al jugador con el contenedor.
#

. /opt/mcpanel/bin/mcpanel-common.sh

MC_HOST="127.0.0.1"
MC_PORT="${MC_INTERNAL_PORT:-25566}"
LOG="$LOG_DIR/proxy.log"

now() {
    date '+%Y-%m-%d %H:%M:%S'
}

echo "$(now) | PETICION RECIBIDA | Minecraft estaba: $(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo desconocido)" >> "$LOG"

if ! mc_running; then
    echo "$(now) | INICIO AUTOMATICO | docker start $CONTAINER" >> "$LOG"
    docker start "$CONTAINER" >> "$LOG" 2>&1

    for i in $(seq 1 300); do
        if nc -z "$MC_HOST" "$MC_PORT" 2>/dev/null; then
            echo "$(now) | MINECRAFT DISPONIBLE | espera=${i}s" >> "$LOG"
            break
        fi
        sleep 1
    done
else
    echo "$(now) | MINECRAFT YA ESTABA ENCENDIDO" >> "$LOG"
fi

exec socat STDIO "TCP:${MC_HOST}:${MC_PORT}"
