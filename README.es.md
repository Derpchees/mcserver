# MCServer by Derpchees

[English](README.md) · **Español**

Un panel web para administrar un servidor de Minecraft Java en Docker, con un instalador interactivo que configura todo en un equipo con Debian o Ubuntu.

Está pensado para un servidor en casa que compartes con amigos: el servidor se enciende cuando alguien se conecta, se apaga cuando no hay nadie jugando y se respalda solo cada día.

## Funciones

- **Panel principal**: estado del servidor, jugadores en línea con su skin, botones para iniciar, apagar y reiniciar, y la cuenta regresiva del apagado automático.
- **Consola y chat**: consola en vivo con colores por nivel, y el chat del servidor con todo su historial. Puedes mandar comandos, o mensajes al chat que aparecen como `[Server]` en el juego. En computadora se ven lado a lado; en celular se alternan con pestañas.
- **Jugadores**: todos los que han entrado, con su skin en 3D que gira. Expulsar, banear, suspensión temporal (se levanta sola), mensajes privados, modo de juego, teletransporte, operador y lista blanca.
- **Archivos**: navegar, subir arrastrando (también carpetas), descargar (carpetas como ZIP), renombrar, mover, borrar, seleccionar varios a la vez y editar archivos de texto como `server.properties`.
- **Respaldos**: respaldo diario programado que conserva los últimos N, y respaldos manuales. Mientras se respalda, el guardado del mundo se pausa (`save-off`) para que la copia quede consistente.
- **Ajustes**: dificultad, modo de juego, PvP, lista blanca, distancia de visión, máximo de jugadores y más, sin editar archivos a mano.
- **Monitor de recursos**: CPU, memoria y temperatura del procesador con gráficas en vivo, y el almacenamiento de cada disco con lo que ocupa cada parte (servidor, respaldos, Docker, sistema) y la temperatura de los discos.
- **Encendido al conectarse y apagado automático**: Minecraft se queda apagado hasta que alguien se conecta, y se apaga tras un tiempo configurable sin jugadores.
- Inglés y español, tema claro y oscuro, y botón para desinstalar.

El servidor de Minecraft corre en la conocida imagen [`itzg/minecraft-server`](https://github.com/itzg/docker-minecraft-server). Tipos de servidor: **Forge, Fabric, Paper y Vanilla**.

## Requisitos

- Debian 12+ o Ubuntu 22.04+ (64 bits). El instalador no funciona en otras distribuciones.
- Un usuario con `sudo`.
- RAM suficiente para tu servidor: unos 2–4 GB para Vanilla o Paper, 6 GB o más con mods.
- Docker. El instalador lo instala si no lo tienes.

## Instalación

```bash
git clone https://github.com/Derpchees/mcserver.git
cd mcserver
sudo ./install.sh
```

O en una línea, sin clonar:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Derpchees/mcserver/main/install.sh)
```

El instalador pregunta, en inglés o español:

1. **Nombre del servidor**: aparece en el panel y en la lista multijugador.
2. **Dónde va el servidor**: una lista de tus discos con su espacio libre. Si una partición no está montada, puede montarla de forma permanente. Nunca formatea nada.
3. **Dónde van los respaldos**: idealmente en otro disco físico.
4. **Tipo de servidor y versión de Minecraft**: la versión correcta de Java se elige sola.
5. **RAM y núcleos de CPU** para Minecraft.
6. **Red**: todas las redes, o una sola interfaz, por ejemplo tu IP de ZeroTier o Tailscale. También los puertos del juego y del panel.
7. **Apagado automático**: si lo quieres usar y tras cuántos minutos sin jugadores.
8. **Respaldos diarios**: a qué hora y cuántos conservar.
9. **Contraseña del panel**, y aceptar el [EULA de Minecraft](https://aka.ms/MinecraftEULA).

Al terminar muestra la dirección del panel, por ejemplo `http://192.168.1.10:8090`. Después Minecraft arranca por primera vez para crear el mundo. Tarda unos minutos, más con mods.

### Instalar sin preguntas

Copia [`examples/answers.env`](examples/answers.env) y complétalo (`ACCEPT_EULA="yes"` y `PASSWORD` son obligatorios). Luego corre:

```bash
sudo ./install.sh --config mis-respuestas.env
```

## Después de instalar

| Tarea | Cómo |
|---|---|
| Abrir el panel | `http://<ip-del-servidor>:8090`, o el puerto que elegiste |
| Cambiar la contraseña del panel | `sudo mcpanel-passwd` |
| Actualizar el panel (conserva ajustes y mundo) | `git pull && sudo ./install.sh --update` |
| Cambiar la configuración de la instalación | Edita `/etc/mcpanel/config.env` y luego `sudo systemctl restart mcpanel-web mcpanel-proxy mcpanel-autostop` |
| Desinstalar | **Ajustes → Zona de peligro** en el panel, o `sudo /opt/mcpanel/uninstall.sh` |

Al desinstalar se conservan el mundo y los respaldos, salvo que elijas borrarlos. Docker no se quita.

## Cómo funciona

```
jugador ─► :25565 mcpanel-proxy ──► 127.0.0.1:25566 Docker (itzg/minecraft-server)
               │ enciende el contenedor si está apagado
navegador ► :8090 mcpanel-web (panel)
               mcpanel-autostop   apaga el contenedor cuando no hay nadie
               mcpanel-backup     respaldos programados y manuales
```

| Ruta | Contenido |
|---|---|
| `/opt/mcpanel` | Panel y scripts |
| `/etc/mcpanel/config.env` | Configuración de la instalación |
| `/etc/mcpanel/secret.json` | Hash de la contraseña (PBKDF2), solo lo lee root |
| `/var/log/mcpanel` | Registros: proxy, apagado automático, respaldos, acciones de administración |
| `/var/lib/mcpanel` | Mensajes de chat enviados desde el panel, bans temporales |

Servicios: `mcpanel-web`, `mcpanel-proxy`, `mcpanel-autostop`, `mcpanel-backup.timer`.

## Seguridad

- El panel usa HTTP sin cifrar. **No lo expongas a internet.** Úsalo en tu red local, o entra por una VPN como ZeroTier, Tailscale o WireGuard. En la instalación puedes hacer que solo escuche en la interfaz de la VPN.
- La **consola, los archivos, los respaldos, los jugadores y los ajustes** piden contraseña. El panel principal, el chat y los botones de iniciar, apagar y reiniciar los puede usar cualquiera que llegue al panel.
- Tras 5 contraseñas incorrectas, esa dirección se bloquea 5 minutos.
- El panel corre como root porque administra Docker y servicios del sistema. Las operaciones con archivos están limitadas a la carpeta del servidor.

## Problemas comunes

- **El panel no carga**: `sudo systemctl status mcpanel-web` y `sudo journalctl -u mcpanel-web -n 50`.
- **Los jugadores no pueden entrar**: revisa el proxy con `sudo systemctl status mcpanel-proxy`, revisa que el firewall permita el puerto del juego, y revisa la dirección que muestra el panel.
- **El servidor no arranca**: mira la consola en el panel, o corre `docker logs mcpanel-minecraft`. El primer arranque de un servidor con mods puede tardar varios minutos.
- **Falló un respaldo**: revisa `/var/log/mcpanel/backup.log`.

## Licencia

[MIT](LICENSE). Minecraft es una marca de Mojang Studios; este proyecto no está afiliado a Mojang ni a Microsoft.
