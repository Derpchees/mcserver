#!/bin/bash
#
# Proxy "bajo demanda": escucha en el puerto publico del juego y, cuando
# alguien se conecta, enciende Minecraft si estaba apagado y pasa la
# conexion al contenedor (que solo escucha en 127.0.0.1).
#

. /opt/mcpanel/bin/mcpanel-common.sh

LISTEN_IP="${LISTEN_IP:-0.0.0.0}"
GAME_PORT="${GAME_PORT:-25565}"

while true; do
    echo "Esperando conexiones en ${LISTEN_IP}:${GAME_PORT}..."

    socat "TCP-LISTEN:${GAME_PORT},fork,reuseaddr,bind=${LISTEN_IP}" \
        EXEC:/opt/mcpanel/bin/mcpanel-connect.sh

    sleep 1
done
