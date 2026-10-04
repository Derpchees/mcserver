#!/usr/bin/env python3
#
# MCServer by Derpchees - avisos en el chat del juego
# https://github.com/Derpchees/mcserver
#
# Manda un aviso a todos los jugadores (tellraw) y lo guarda en el
# historial del chat del panel. Solo si el servidor esta encendido.
#
#   python3 announce.py <servidor> <aviso>
#
# Lo usan mcpanel-backup.sh (al empezar y al terminar un respaldo) y el
# agente (un minuto antes de un respaldo automatico).
#

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mcpanel_core as core  # noqa: E402

LABEL = {"es": "Respaldo", "en": "Backup"}

MESSAGES = {
    "backup_soon": {
        "es": "Respaldo automático en 1 minuto. Puede haber un pequeño tirón.",
        "en": "Automatic backup in 1 minute. There may be a short lag spike."
    },
    "backup_start": {
        "es": "Guardando una copia del mundo...",
        "en": "Saving a copy of the world..."
    },
    "backup_done": {
        "es": "Respaldo completado.",
        "en": "Backup completed."
    },
    "backup_failed": {
        "es": "El respaldo falló. Se avisó al administrador.",
        "en": "The backup failed. The admin was notified."
    }
}


def announce(srv, key):
    if key not in MESSAGES or core.container_state(srv)[0] != "running":
        return False

    lang = "es" if core.DEFAULT_LANG == "es" else "en"
    label = LABEL[lang]
    text = MESSAGES[key][lang]
    payload = json.dumps(["", {"text": "[%s] " % label, "color": "gold"}, {"text": text}], ensure_ascii=False)

    try:
        result = subprocess.run(["docker", "exec", srv.container, "rcon-cli", "tellraw", "@a", payload],
                                capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False

    if result.returncode != 0:
        return False

    # tellraw no queda en los logs de Minecraft: se guarda para el chat del panel
    try:
        os.makedirs(srv.state_dir, exist_ok=True)

        with open(os.path.join(srv.state_dir, "chat.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "type": "say", "name": label,
                                "role": "server", "text": text}, ensure_ascii=False) + "\n")
    except OSError:
        pass

    return True


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: announce.py <servidor> <aviso>", file=sys.stderr)
        sys.exit(2)

    server = core.get_server_by_slug(sys.argv[1])
    sys.exit(0 if server and announce(server, sys.argv[2]) else 1)
