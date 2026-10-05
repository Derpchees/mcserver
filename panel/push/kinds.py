#
# MCServer by Derpchees - Que avisos quiere recibir cada cuenta
#
# Los eventos se agrupan en temas; cada cuenta puede silenciar los que no
# le interesen (users.notify_mute, separados por coma). Lo usan la campana
# de la pagina (webpanel/admin.py) y los avisos push (push/store.py).
#

GROUPS = {
    "online": ("server_started",),
    "offline": ("server_stopped",),
    "problems": ("server_crashed", "server_error", "backup_failed"),
    "backups": ("backup_ok",),
}

# Lo que no esta arriba (alertas del equipo, discos, HTTPS, servidor borrado)
SYSTEM = "system"

ALL = tuple(GROUPS) + (SYSTEM,)


def group_of(kind):
    base = (kind or "").split(":")[0]

    for name, kinds in GROUPS.items():
        if base in kinds:
            return name

    return SYSTEM


def muted_of(user):
    try:
        value = user["notify_mute"] or ""
    except (KeyError, IndexError):
        value = ""

    return {name for name in value.split(",") if name in ALL}


def clean(names):
    # Lista recibida de la pagina -> texto para la base
    if not isinstance(names, list):
        names = []

    return ",".join(name for name in ALL if name in names)


def wanted(events, muted):
    return [event for event in events if group_of(event["kind"]) not in muted] if muted else events
