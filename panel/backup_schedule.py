#
# MCServer by Derpchees - horario de los respaldos automaticos
# https://github.com/Derpchees/mcserver
#
# Es una sola serie de respaldos automaticos (mismo historial y mismo
# limite de respaldos a conservar); solo cambia cada cuanto se hacen:
#   - con el servidor encendido: cada backup_every_hours
#   - con el servidor apagado: cada backup_every_hours_off (0 = nunca;
#     apagado el mundo no cambia)
#
# Los turnos caen siempre en la misma rejilla, contada desde una fecha fija:
#   hora de inicio + k * intervalo   (k entero)
# asi "cada 6 h desde las 04:00" da 04, 10, 16 y 22, y "cada 2 dias"
# alterna siempre los mismos dias. Un respaldo toca cuando el ultimo es
# anterior al turno mas reciente; si el equipo estuvo apagado, al volver
# se hace el que falto.
#
# Lo usan el agente (cuando respaldar y avisar) y el panel (proximo respaldo).
#

import os
import re
import time

MIN_HOURS = 1
MAX_HOURS = 30 * 24

# Fecha fija desde la que se cuentan los turnos
ANCHOR_DAY = (2024, 1, 1)


def interval_hours(srv, running):
    # Horas entre respaldos segun el estado; 0 = no se respalda
    hours = srv.backup_every_hours if running else srv.backup_every_hours_off

    if not hours:
        return 0

    return max(MIN_HOURS, min(MAX_HOURS, int(hours)))


def slots(backup_time, every_hours, now=None):
    # (turno mas reciente <= ahora, siguiente turno)
    now = time.time() if now is None else now
    hour, minute = [int(x) for x in backup_time.split(":")]
    start = time.mktime(ANCHOR_DAY + (hour, minute, 0, 0, 0, -1))
    step = every_hours * 3600
    last = start + ((now - start) // step) * step
    return last, last + step


def last_file(srv):
    return os.path.join(srv.state_dir, "last_auto_backup")


def last_auto(srv):
    # Hora del ultimo respaldo automatico. Las versiones anteriores guardaban
    # solo la fecha (uno al dia): se toma esa fecha a la hora elegida.
    try:
        with open(last_file(srv), "r") as f:
            text = f.read().strip()
    except OSError:
        return 0

    if re.match(r"^\d+(\.\d+)?$", text):
        return float(text)

    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return time.mktime(time.strptime(text + " " + srv.backup_time, "%Y-%m-%d %H:%M"))

    return 0


def mark_done(srv, when=None):
    os.makedirs(srv.state_dir, exist_ok=True)

    with open(last_file(srv), "w") as f:
        f.write("%d" % (time.time() if when is None else when))


def is_due(srv, running, now=None):
    hours = interval_hours(srv, running)

    if not hours:
        return False

    last_slot, _ = slots(srv.backup_time, hours, now)
    return last_auto(srv) < last_slot


def next_run(srv, running, now=None):
    # Proximo respaldo automatico con el estado actual (None si no hay)
    now = time.time() if now is None else now
    hours = interval_hours(srv, running)

    if not srv.backups or not hours:
        return None

    last_slot, next_slot = slots(srv.backup_time, hours, now)

    # Si el turno actual aun no se cubrio, el agente lo hara enseguida
    return next_slot if last_auto(srv) >= last_slot else now
