# MCServer by Derpchees — guía para Claude

Panel web para correr varios servidores de Minecraft (Java y Bedrock) en un equipo Linux (Debian/Ubuntu), cada uno en Docker (`itzg/minecraft-server` o `itzg/minecraft-bedrock-server`), con cuentas de usuario. Pensado para **redes de casa o VPN** (ZeroTier, Tailscale), nunca expuesto a internet. Repo público: https://github.com/Derpchees/mcserver (rama `main`, licencia MIT).

Lee esto en lugar de recorrer todo el proyecto. Los detalles privados del entorno del dueño están en `CLAUDE.local.md` (no se sube a GitHub).

## Reglas del proyecto

- **Todo automático.** Cada función debe quedar en el panel (un clic o un formulario) y, si aplica, en `install.sh` (pregunta interactiva + clave en `examples/answers.env`). Nunca entregar comandos sueltos o scripts para que la persona los corra. El panel corre como root, así que los cambios del sistema (discos, certificados, actualizaciones) son tareas del panel.
- **Modular.** Un archivo pequeño por tema. Nada de archivos gigantes. Al agregar algo, crear su módulo/archivo propio.
- **Sin React ni herramientas de compilación.** El dueño lo descartó a propósito.
- **Bilingüe.** Toda cadena visible va en inglés y español en `panel/web/js/01-i18n.js` (bloques `en:` y `es:`, mismas claves). Los mensajes que el backend devuelve en español se traducen en `SERVER_MESSAGES_EN` / `SERVER_PREFIXES_EN` del mismo archivo.
- **Comentarios del código en español sin acentos**, al estilo existente. Mensajes de commit en inglés.
- **No romper instalaciones existentes.** Columnas nuevas de la base: agregarlas en `SCHEMA` y con `ALTER TABLE` en `db()` de `mcpanel_core.py`, con un valor por defecto que conserve el comportamiento anterior.
- Nunca formatear, achicar ni borrar particiones con datos sin copia verificada (ver `storage/rebuild.py`).

## Estructura

```
install.sh / uninstall.sh   instalador (whiptail, en/es, --update, --config answers.env); VERSION="x.y.z" aquí
bin/                        mcpanel-backup.sh (respaldos), mcpanel-passwd
systemd/                    mcpanel-web.service, mcpanel-agent.service (corren como root)
panel/
  mcpanel.py                punto de entrada del panel web (HTTP y HTTPS en el mismo puerto)
  mcpanel-agent.py          agente: proxy de juego (enciende al conectar), apagado automático,
                            respaldos programados, alertas, discos, renovación del certificado propio
  mcpanel_core.py           config (/etc/mcpanel/config.env, releída en vivo), SQLite, modelo Server,
                            contenedores Docker (container_spec / build_container / container_matches)
  backup_schedule.py        turnos de respaldo (intervalo encendido/apagado)
  announce.py               avisos en el chat del juego (tellraw)
  webpanel/                 backend del panel, un módulo por tema; handler.py = rutas HTTP;
                            common.py es la capa base (sin ciclos de import)
  storage/                  almacenamiento: discos, particiones, LVM, archivos reservados, mover datos,
                            rehacer disco, vigilancia de discos (watch.py, lo usa el agente)
  sysadmin/                 tareas del sistema: duckdns.py (HTTPS con Let's Encrypt), localca.py
                            (HTTPS con CA propia), update.py (actualizar desde GitHub), tasks.py
  bedrock/                  servidores Bedrock (tipo BEDROCK): signaling.py (NetherNet: estado HTTP y
                            puertos UDP), console.py (comandos con send-command, sin RCON), firstboot.py,
                            packs.py y addons.py (add-ons: .mcaddon/.mcpack, activar en el mundo)
  push/                     notificaciones push (Web Push): vapid.py (firma ES256 sin librerias),
                            store.py (dispositivos suscritos), sender.py (hilo del agente),
                            kinds.py (temas de avisos que cada cuenta silencia)
  web/
    index.html              la página
    sw.js                   service worker: muestra las notificaciones push (no va en app.js)
    css/NN-*.css, js/NN-*.js  se unen EN ORDEN NUMÉRICO en /app.css y /app.js (webassets.py)
```

### Detalles importantes del frontend

- Los JS son **scripts clásicos concatenados**, no módulos ES: el HTML usa `onclick="..."` con funciones globales. `99-start.js` debe seguir siendo el último.
- Cuidado con `const`/`let` de nivel superior usados por código que se ejecuta al cargar en un archivo anterior (zona muerta temporal). Las declaraciones `function` sí se elevan en todo el bundle.
- `MCPANEL_DEV=1` hace que el panel relea `web/` en cada petición.
- Idioma, tema y campana viven en `#prefsBox`: con sesion se mudan al menu de la cuenta. Administracion y Ajustes del servidor usan pestanas (`data-admtab`, `#/admin/<pestana>`; `data-settab`, `#/s/<id>/settings/<pestana>`). Al cambiar de vista `route()` cierra cualquier ventana (`closeModal`).
- Caras y skins de jugadores: `playerHeadUrl` / `playerSkinUrl` (el panel usa la skin de Quick Skin o la de Mojang; `webpanel/skins.py`), nunca mc-heads.net directo.
- Ayudas comunes: `$`, `el`, `t`, `tn`, `api`, `postJson`, `openModal`, `confirmDialog`, `doubleConfirm`, `showToast`, `formatBytes`.

### Detalles importantes del backend

- Dentro de una petición de servidor se usa `S()` / `use_server()` (`webpanel/common.py`).
- Bedrock (`core.is_bedrock`): desde la 1.26 usa NetherNet: HTTP por TCP en `BEDROCK_PORT_START` (19132, pasa por el proxy del agente) y el juego por UDP directo, 20 puertos por servidor (`bedrock/signaling.py`). Sin RCON ni Java; el nombre en la lista va en `SERVER_NAME` (la imagen no reescribe un `server.properties` existente). Tiene add-ons en lugar de mods (`webpanel/addons.py`, solo gratuitos: subidos o de CurseForge, juego 78022). Un servidor no cambia de Java a Bedrock.
- Rutas `/s/<id>/...` = de un servidor (`server_get` / `server_post` en `handler.py`); `/admin/...` = administración; varias acciones son solo del **dueño del sistema** (`is_owner`).
- Cambios con el servidor encendido quedan pendientes (`containers.request_rebuild`); `container_matches` compara con el contenedor real para no dejar pendientes falsos.
- Las rutas de datos (`DATA_ROOT`, `BACKUP_ROOT`) pueden cambiar en vivo: usar `core.data_root()` / `core.backup_root()`, nunca las constantes.
- Sesiones en la tabla `sessions` (solo el hash del token).
- App instalable: `webpanel/pwa.py` (manifiesto e iconos PNG dibujados en Python). Notificaciones: la página usa `showSystemNotification` (24-push.js), nunca `new Notification` directo (no existe en Android).

## Versiones y publicación

- La versión vive en `install.sh` (`VERSION="x.y.z"`); el instalador la escribe en `/opt/mcpanel/VERSION` y el pie de página la muestra. **Subirla en cada publicación**: el botón "Actualizar" del panel compara con la de GitHub.
- Funciones nuevas grandes suben el número del medio (2.3 → 2.4); arreglos, el último.
- Commits: título en inglés, imperativo, estilo `MCServer 2.3.5: ...` para versiones; cuerpo explicando el porqué; cerrar con la línea `Co-Authored-By` que indique el sistema.
- Push a `main` solo cuando el dueño lo pide (lo suele pedir: "dale push", "haz push").
- Los usuarios actualizan desde **Administración → Actualizaciones** (descarga `main` y corre `install.sh --update`).

## Cómo probar

En la PC del dueño (Windows) no hay Docker ni Linux. Herramientas instaladas para el usuario:

- Python 3.12: `$LOCALAPPDATA/Programs/Python/Python312/python.exe`, con `pyflakes`, `esprima` (sintaxis del bundle JS: `esprima.parseScript(app.js)`) y `playwright` + Chromium headless (capturas e interacción real).
- **Siempre**: `python -m pyflakes` sobre los módulos tocados, comprobar la sintaxis de `/app.js` con esprima, y bash `-n` en los scripts.
- **Demo local**: un lanzador que arranca el panel real con Docker, `/proc`, discos y `rcon` simulados y datos de ejemplo. Hoy vive fuera del repo (en el scratchpad de una sesión), así que puede no existir: si hace falta probar la interfaz, ofrecer reconstruirlo o agregarlo al repo como `dev/demo.py`.
- Lo que depende de Linux real (discos, certificados, Docker) se prueba en el servidor del dueño sin tocar su instalación (ver `CLAUDE.local.md`).
- El navegador headless siempre reporta las notificaciones como bloqueadas: para probarlas, simular `window.Notification`.
