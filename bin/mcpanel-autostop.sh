#!/bin/bash
#
# Apaga Minecraft cuando no hay jugadores durante IDLE_MINUTES y deja
# el estado en $RUN_DIR/autostop.json para el panel (cuenta regresiva y
# nombres de los jugadores en linea).
#

. /opt/mcpanel/bin/mcpanel-common.sh

IDLE_SECONDS=$(( ${IDLE_MINUTES:-10} * 60 ))
CHECK_INTERVAL=10
LOG="$LOG_DIR/autostop.log"
STATE="$RUN_DIR/autostop.json"

idle_since=0
players=""
player_names="[]"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | $1" >> "$LOG"
}

write_state() {
    cat > "$STATE.tmp" <<EOF
{
  "enabled": true,
  "running": $1,
  "health": "$2",
  "players": $3,
  "names": ${6:-[]},
  "idle_seconds": $4,
  "remaining_seconds": $5,
  "timeout_seconds": $IDLE_SECONDS
}
EOF
    mv -f "$STATE.tmp" "$STATE"
}

# Deja en $players el numero y en $player_names un arreglo JSON
query_players() {
    local output list

    output=$(mc_rcon list)

    players=$(echo "$output" | grep -oE 'There are [0-9]+' | grep -oE '[0-9]+' | head -1)

    list=$(
        echo "$output" |
            sed -e 's/\x1b\[[0-9;]*m//g' -n -e 's/.*online: *//p' |
            tr -cd 'A-Za-z0-9_, ' |
            tr ',' '\n' |
            tr -d ' ' |
            grep -v '^$' |
            sed 's/.*/"&"/' |
            paste -sd, -
    )

    player_names="[$list]"
}

write_state false "offline" 0 0 "$IDLE_SECONDS"
log "AUTOSTOP INICIADO | espera=${IDLE_SECONDS}s"

while true; do

    if ! mc_running; then
        idle_since=0
        write_state false "offline" 0 0 "$IDLE_SECONDS"
        sleep "$CHECK_INTERVAL"
        continue
    fi

    health=$(mc_health)

    # Arrancando: todavia no se cuenta
    if [ "$health" != "healthy" ]; then
        idle_since=0
        write_state true "$health" 0 0 "$IDLE_SECONDS"
        sleep "$CHECK_INTERVAL"
        continue
    fi

    query_players

    # Si no se pudo consultar, nunca se apaga
    if ! [[ "$players" =~ ^[0-9]+$ ]]; then
        idle_since=0
        write_state true "$health" 0 0 "$IDLE_SECONDS"
        sleep "$CHECK_INTERVAL"
        continue
    fi

    if [ "$players" -gt 0 ]; then
        [ "$idle_since" -ne 0 ] && log "JUGADORES DETECTADOS: $players | cancelando cuenta regresiva"
        idle_since=0
        write_state true "$health" "$players" 0 "$IDLE_SECONDS" "$player_names"
    else
        now=$(date +%s)

        if [ "$idle_since" -eq 0 ]; then
            idle_since=$now
            log "0 JUGADORES | iniciando cuenta regresiva de ${IDLE_SECONDS}s"
        fi

        elapsed=$((now - idle_since))
        remaining=$((IDLE_SECONDS - elapsed))
        [ "$remaining" -lt 0 ] && remaining=0

        write_state true "$health" 0 "$elapsed" "$remaining"

        if [ "$elapsed" -ge "$IDLE_SECONDS" ]; then
            query_players

            if [ "$players" = "0" ]; then
                log "0 JUGADORES DURANTE ${IDLE_SECONDS}s | APAGANDO MINECRAFT"
                docker stop "$CONTAINER" >> "$LOG" 2>&1
                log "MINECRAFT APAGADO AUTOMATICAMENTE"
            else
                log "JUGADOR DETECTADO EN VERIFICACION FINAL | cancelando"
            fi

            idle_since=0
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
