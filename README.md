# MCServer by Derpchees

**English** · [Español](README.es.md)

A self-hosted web panel for a Minecraft Java server running in Docker, plus an interactive installer that sets everything up on a Debian or Ubuntu machine.

It is built for a home server shared with friends: the server starts when someone connects, shuts down when nobody is playing, and backs itself up every day.

## Features

- **Dashboard**: server status, online players with their skins, one-click start, stop and restart, and an automatic-shutdown countdown.
- **Console and chat**: live console with colored log levels, and the server chat with its full history. You can send commands, or chat messages that show up as `[Server]` in game. On a computer they sit side by side; on a phone they switch with tabs.
- **Players**: everyone who has joined, with a rotating 3D skin. Kick, ban, temporary suspension (lifted automatically), private messages, game mode, teleport, operator and whitelist.
- **Files**: browse, upload by drag and drop (folders too), download (folders as ZIP), rename, move, delete, select many at once, and edit text files such as `server.properties`.
- **Backups**: scheduled daily backups that keep the last N, plus manual backups. While a backup runs the world is paused (`save-off`) so the copy stays consistent.
- **Settings**: difficulty, game mode, PvP, whitelist, view distance, max players and more, without editing files by hand.
- **Resource monitor**: CPU, memory and CPU temperature with live charts, plus per-disk storage showing what takes the space (server, backups, Docker, system) and drive temperatures.
- **On-demand start and auto stop**: Minecraft stays off until someone connects, and stops after a configurable time with no players.
- English and Spanish, light and dark themes, and an uninstall button.

The Minecraft server itself runs in the well-known [`itzg/minecraft-server`](https://github.com/itzg/docker-minecraft-server) image. Supported server types: **Forge, Fabric, Paper and Vanilla**.

## Requirements

- Debian 12+ or Ubuntu 22.04+ (64-bit). Other distributions are not supported by the installer.
- A user with `sudo`.
- Enough RAM for the server you want: about 2–4 GB for Vanilla or Paper, 6 GB or more for a modded server.
- Docker. The installer installs it if it is missing.

## Install

```bash
git clone https://github.com/Derpchees/mcserver.git
cd mcserver
sudo ./install.sh
```

Or in one line, without cloning:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Derpchees/mcserver/main/install.sh)
```

The installer asks, in English or Spanish:

1. **Server name**: shown in the panel and in the multiplayer list.
2. **Where the server lives**: a list of your disks with their free space. If a partition is not mounted, it can mount it permanently for you. It never formats anything.
3. **Where backups go**: ideally a different physical disk.
4. **Server type and Minecraft version**: the right Java version is picked automatically.
5. **RAM and CPU cores** for Minecraft.
6. **Network**: all networks, or one interface such as a ZeroTier or Tailscale address. Also the game and panel ports.
7. **Auto stop**: whether to use it, and after how many minutes without players.
8. **Daily backups**: time of day and how many to keep.
9. **Panel password**, and acceptance of the [Minecraft EULA](https://aka.ms/MinecraftEULA).

At the end it prints the panel address, for example `http://192.168.1.10:8090`. Minecraft then starts for the first time to create the world. This takes a few minutes, longer with mods.

### Install without questions

Copy [`examples/answers.env`](examples/answers.env), fill it in (`ACCEPT_EULA="yes"` and `PASSWORD` are required), then run:

```bash
sudo ./install.sh --config my-answers.env
```

## After installing

| Task | How |
|---|---|
| Open the panel | `http://<server-ip>:8090`, or the port you chose |
| Change the panel password | `sudo mcpanel-passwd` |
| Update the panel (keeps settings and world) | `git pull && sudo ./install.sh --update` |
| Change the installation settings | Edit `/etc/mcpanel/config.env`, then `sudo systemctl restart mcpanel-web mcpanel-proxy mcpanel-autostop` |
| Uninstall | **Settings → Danger zone** in the panel, or `sudo /opt/mcpanel/uninstall.sh` |

Uninstalling keeps the world and the backups unless you choose to delete them. It does not remove Docker.

## How it works

```
player ──► :25565 mcpanel-proxy ──► 127.0.0.1:25566 Docker (itzg/minecraft-server)
               │ starts the container if it is off
browser ─► :8090 mcpanel-web (panel)
               mcpanel-autostop   stops the container when empty
               mcpanel-backup     scheduled and manual backups
```

| Path | Contents |
|---|---|
| `/opt/mcpanel` | Panel and scripts |
| `/etc/mcpanel/config.env` | Installation settings |
| `/etc/mcpanel/secret.json` | Password hash (PBKDF2), readable only by root |
| `/var/log/mcpanel` | Logs: proxy, auto stop, backups, admin actions |
| `/var/lib/mcpanel` | Chat messages sent from the panel, temporary bans |

Services: `mcpanel-web`, `mcpanel-proxy`, `mcpanel-autostop`, `mcpanel-backup.timer`.

## Security

- The panel uses plain HTTP. **Do not expose it to the internet.** Use it on your local network, or reach it through a VPN such as ZeroTier, Tailscale or WireGuard. During installation you can bind it to the VPN interface only.
- The **console, files, backups, players and settings** need the password. The dashboard, the chat and the start, stop and restart buttons can be used by anyone who can reach the panel.
- After 5 wrong passwords, the address is blocked for 5 minutes.
- The panel runs as root because it manages Docker and system services. File operations are confined to the server folder.

## Troubleshooting

- **The panel does not load**: `sudo systemctl status mcpanel-web` and `sudo journalctl -u mcpanel-web -n 50`.
- **Players cannot connect**: check the proxy with `sudo systemctl status mcpanel-proxy`, check that your firewall allows the game port, and check the address shown in the panel.
- **The server does not start**: watch the console in the panel, or run `docker logs mcpanel-minecraft`. The first start of a modded server can take several minutes.
- **A backup failed**: see `/var/log/mcpanel/backup.log`.

## License

[MIT](LICENSE). Minecraft is a trademark of Mojang Studios; this project is not affiliated with Mojang or Microsoft.
