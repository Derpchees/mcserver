# MCServer by Derpchees

[English](README.md) · **Español**

Un panel web para correr **varios servidores de Minecraft Java en un mismo equipo**, cada uno en Docker, con cuentas de usuario. Incluye un instalador que configura todo en Debian o Ubuntu.

Cada persona crea su cuenta desde la pantalla de entrar y, en el mismo paso, su propio servidor: elige el tipo, la versión, la RAM y la CPU. Los servidores se encienden cuando alguien se conecta, se apagan cuando nadie juega y se respaldan solos cada día.

## Funciones

- **Cuentas y servidores**
  - La primera vez que abres el panel, un asistente crea la primera cuenta: el **dueño del sistema**, un administrador total que nadie más puede cambiar ni borrar. Solo él puede cambiar roles y desinstalar.
  - En ese asistente eliges si los visitantes sin cuenta pueden ver y encender servidores.
  - Después cualquiera puede registrarse y crear su servidor, dentro de los límites que fija el administrador. El registro se puede desactivar.
- **Quién puede hacer qué**

  | | Visitantes | Dueño del servidor | Administrador |
  |---|---|---|---|
  | Ver el estado de cualquier servidor | Sí | Sí | Sí |
  | Encender un servidor | Sí | Sí | Sí |
  | Apagar, reiniciar, consola, chat, archivos, jugadores, ajustes, respaldos | No | El suyo | Todos |
  | Usuarios, límites, desinstalar | No | No | Sí |

- **Panel principal**: estado, jugadores en línea con su skin, la cuenta regresiva del apagado automático y un monitor de recursos (CPU, memoria, temperaturas, almacenamiento por disco).
- **Consola y chat**: lado a lado en computadora, con pestañas en celular. Incluye el historial del chat del servidor.
- **Mods, plugins y modpacks (Modrinth)**: en la pestaña Mods buscas mods de servidor (los que son solo de cliente se ocultan) o plugins para Paper, y los agregas o quitas de a varios: marcando resultados, pegando una lista de nombres o enlaces, o seleccionando todos. Ahí mismo eliges un modpack para el servidor y puedes volver al tipo anterior. No requiere clave.
- **Mensaje del servidor (MOTD)**: se edita junto al estado del servidor, con paleta de colores y estilos de Minecraft y vista previa.
- **Servidor favorito**: la estrella junto a Iniciar hace que el panel abra ese servidor. Se guarda en tu cuenta o, sin sesión, en el navegador.
- **Jugadores**: todos los que han entrado, con su skin en 3D. Expulsar, banear, suspensión temporal, mensajes privados, modo de juego, teletransporte, operador y lista blanca.
- **Archivos**: arrastrar y soltar en cualquier parte (también carpetas), selección múltiple, mover, renombrar, descarga en ZIP y editor de texto.
- **Respaldos**: automáticos y manuales. Eliges cada cuánto para cada servidor, con una frecuencia cuando está encendido y otra cuando está apagado (o ninguna, porque el mundo no cambia). Los jugadores reciben un aviso en el chat un minuto antes, al empezar y al terminar. El mundo se pausa mientras se copia para que el respaldo quede consistente.
- **Almacenamiento** (Administración): elige dónde viven los servidores y los respaldos, y reserva una cantidad fija de espacio para ellos, para que nada más en el disco pueda ocuparlo. Puede crear una partición en espacio libre o en un disco vacío (y otra con el resto, por ejemplo para cámaras de seguridad), montar una partición existente, crear un volumen LVM o reservar un archivo de disco. Nunca formatea, achica ni borra particiones que ya existen. Si se desconecta el disco de respaldos, los respaldos se pausan y se reanudan cuando vuelve; si falta el disco de los servidores, no se encienden.
- **Ajustes**: `server.properties` sin editar archivos (dificultad, PvP, lista blanca...), además de los recursos y la automatización del servidor.
- **Notificaciones del navegador**: servidor en línea, apagado o caído; respaldo terminado o fallido; y, para el administrador, temperatura alta o disco o memoria casi llenos.
- **Borrado seguro**: borrar un servidor, una cuenta o todo el sistema pide doble confirmación.
- Inglés y español, tema claro y oscuro.

Cada servidor de Minecraft corre en la imagen [`itzg/minecraft-server`](https://github.com/itzg/docker-minecraft-server). Tipos: **Forge, NeoForge, Fabric, Paper y Vanilla**.

## Requisitos

- Debian 12+ o Ubuntu 22.04+ (64 bits), con `sudo`.
- RAM suficiente para los servidores que vayan a estar encendidos a la vez: unos 2–4 GB cada uno para Vanilla o Paper, 6 GB o más cada uno con mods. Los servidores apagados no usan RAM.
- Docker. El instalador lo instala si no lo tienes.

## Instalación

```bash
git clone https://github.com/Derpchees/mcserver.git
cd mcserver
sudo ./install.sh
```

O en una línea:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Derpchees/mcserver/main/install.sh)
```

El instalador prepara el equipo. Pregunta, en inglés o español:

1. **Dónde van los servidores**: una lista de tus discos con su espacio libre. Puede montar una partición sin montar de forma permanente. Nunca formatea nada.
2. **Dónde van los respaldos**: idealmente en otro disco físico.
3. **Red**: todas las redes, o una sola interfaz, por ejemplo tu IP de ZeroTier o Tailscale.
4. **Puertos**: el del panel, y el primer puerto de juego. Cada servidor nuevo toma el siguiente libre.
5. **Dirección que usan los jugadores**: una IP o un dominio.
6. Aceptar el [EULA de Minecraft](https://aka.ms/MinecraftEULA).

Si el firewall `ufw` está activo, abre el puerto del panel y 50 puertos de juego en la red elegida.

Al terminar, **abre la dirección del panel que muestra y crea la cuenta de administrador**.

Para instalar sin preguntas, copia [`examples/answers.env`](examples/answers.env), complétalo y corre `sudo ./install.sh --config mis-respuestas.env`.

## Después de instalar

| Tarea | Cómo |
|---|---|
| Crear al administrador | Abre el panel por primera vez |
| Crear un servidor | Regístrate desde la pantalla de entrar, o **+ Crear un servidor** en el inicio |
| Cambiar recursos, versión o automatización | Servidor → **Ajustes → Servidor y recursos** |
| Límites y registro | **Administración** (solo administradores) |
| Activar notificaciones | **Mi cuenta → Notificaciones del navegador** |
| Olvidé una contraseña | `sudo mcpanel-passwd <usuario>` (`--list` muestra los usuarios) |
| Actualizar (conserva cuentas, servidores y mundos) | `git pull && sudo ./install.sh --update` |
| Desinstalar | **Administración → Zona de peligro**, o `sudo /opt/mcpanel/uninstall.sh` |

### Importar un servidor que ya tienes

Puedes registrar un mundo existente sin moverlo. La importación copia del contenedor anterior la versión del cargador de mods (por ejemplo `FORGE_VERSION`), así tus mods siguen funcionando:

```bash
sudo python3 /opt/mcpanel/panel/mcpanel_core.py import-server \
    --name "Mi servidor" --owner admin --data-dir /ruta/a/la-carpeta-del-mundo \
    --type FORGE --version 1.20.1 --ram 8 --from-container nombre-del-contenedor-viejo
```

## Cómo funciona

```
jugador ─► :25565, :25566, ... mcpanel-agent ──► 127.0.0.1 Docker (un contenedor por servidor)
                                 │ enciende el servidor al conectarse,
                                 │ lo apaga cuando no hay nadie, respalda y avisa
navegador ► :8090 mcpanel-web (panel y cuentas)
```

| Ruta | Contenido |
|---|---|
| `/opt/mcpanel` | Panel, agente y scripts |
| `/etc/mcpanel/config.env` | Configuración del sistema que escribe el instalador |
| `/var/lib/mcpanel/mcpanel.db` | Cuentas, servidores, límites y eventos (SQLite). Las contraseñas se guardan como hash PBKDF2. |
| `/var/log/mcpanel/servers/<servidor>/` | Registros de cada servidor: proxy, apagado automático, respaldos, acciones de administración |

Servicios: `mcpanel-web` y `mcpanel-agent`.

## Seguridad

- El panel usa HTTP sin cifrar. **No lo expongas a internet.** Úsalo en tu red local o por una VPN (ZeroTier, Tailscale, WireGuard). El instalador puede hacer que solo escuche en la interfaz de la VPN.
- Cualquiera que llegue al panel puede ver el estado de todos los servidores, encender cualquiera y, mientras el registro esté activo, crear una cuenta y un servidor. Desactiva el registro en **Administración** cuando todos tengan su cuenta.
- Tras 5 contraseñas incorrectas, esa dirección se bloquea 5 minutos.
- El panel y el agente corren como root porque administran Docker. Las operaciones con archivos están limitadas a la carpeta de cada servidor.

## Problemas comunes

- **El panel no carga**: `sudo systemctl status mcpanel-web` y `sudo journalctl -u mcpanel-web -n 50`.
- **Los jugadores no pueden entrar, o un servidor no se enciende al conectarse**: `sudo journalctl -u mcpanel-agent -n 50`. Revisa también el firewall y la dirección que muestra el panel.
- **Un servidor nuevo se queda en "Preparando"**: la primera vez se descarga la imagen de Minecraft (cerca de 1 GB). Si falla, el servidor muestra el error y el motivo.
- **Falló un respaldo**: `/var/log/mcpanel/servers/<servidor>/backup.log`.

## Licencia

[MIT](LICENSE). Minecraft es una marca de Mojang Studios; este proyecto no está afiliado a Mojang ni a Microsoft.
