#!/bin/bash
#
# Carga la configuracion compartida. Todos los scripts la incluyen.
#

MCPANEL_CONFIG="${MCPANEL_CONFIG:-/etc/mcpanel/config.env}"

if [ ! -f "$MCPANEL_CONFIG" ]; then
    echo "mcpanel: no existe $MCPANEL_CONFIG (corre install.sh)" >&2
    exit 1
fi

# shellcheck source=/dev/null
. "$MCPANEL_CONFIG"

CONTAINER="${CONTAINER:-mcpanel-minecraft}"
LOG_DIR="${LOG_DIR:-/var/log/mcpanel}"
STATE_DIR="${STATE_DIR:-/var/lib/mcpanel}"
RUN_DIR="${RUN_DIR:-/run/mcpanel}"

mkdir -p "$LOG_DIR" "$STATE_DIR" "$RUN_DIR"


mc_running() {
    [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ]
}


mc_health() {
    docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-health{{end}}' \
        "$CONTAINER" 2>/dev/null
}


mc_rcon() {
    docker exec "$CONTAINER" rcon-cli "$@" 2>/dev/null
}
