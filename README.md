# MCServer by Derpchees

**English** · [Español](README.es.md)

A self-hosted web panel to run **several Minecraft Java servers on one machine**, each in Docker, with user accounts. It comes with an installer that sets everything up on Debian or Ubuntu.

Each person creates an account from the login page and, in the same step, their own server: they choose the type, version, RAM and CPU. Servers start when someone connects, shut down when nobody is playing, and back themselves up every day.

## Features

- **Accounts and servers**
  - The first time you open the panel, a wizard creates the first account: the **system owner**, a full administrator nobody else can change or delete. Only the owner can change roles and uninstall.
  - In that wizard you choose whether visitors without an account can see and start servers.
  - Anyone can then sign up and create their server, within limits set by the administrator. Sign-up can be turned off.
- **Who can do what**

  | | Visitors | Server owner | Administrator |
  |---|---|---|---|
  | See the status of any server | Yes | Yes | Yes |
  | Start a server | Yes | Yes | Yes |
  | Stop, restart, console, chat, files, players, settings, backups | No | Their own | All |
  | Users, limits, uninstall | No | No | Yes |

- **Dashboard**: status, online players with their skins, an auto-shutdown countdown and a resource monitor (CPU, memory, temperatures, per-disk storage).
- **Console and chat**: side by side on a computer, tabs on a phone. Includes the server chat history.
- **Mods, plugins and modpacks (Modrinth)**: in the Mods tab you search server-side mods (client-only mods are hidden) or plugins for Paper and add or remove many at once: by ticking results, pasting a list of names or links, or selecting all. The same tab picks a modpack for the server, and you can go back to the previous type. No key needed.
- **Server message (MOTD)**: edited next to the server status, with Minecraft colors, styles and a live preview.
- **Favorite server**: the star next to Start makes the panel open that server. It is saved in your account or, without logging in, in the browser.
- **Players**: everyone who has joined, with a 3D skin. Kick, ban, temporary suspension, private messages, game mode, teleport, operator and whitelist.
- **Files**: drag and drop anywhere (folders too), multi-select, move, rename, ZIP download and a text editor.
- **Backups**: daily and manual. The world is paused while copying so the backup stays consistent.
- **Settings**: `server.properties` without editing files (difficulty, PvP, whitelist...), plus the server's resources and automation.
- **Browser notifications**: server online, stopped or crashed; backup finished or failed; and, for the administrator, high temperature, almost-full disk or memory.
- **Safe deleting**: deleting a server, an account or the whole system asks for a double confirmation.
- English and Spanish, light and dark themes.

Each Minecraft server runs in the [`itzg/minecraft-server`](https://github.com/itzg/docker-minecraft-server) image. Types: **Forge, NeoForge, Fabric, Paper and Vanilla**.

## Requirements

- Debian 12+ or Ubuntu 22.04+ (64-bit), with `sudo`.
- Enough RAM for the servers you plan to run at the same time: about 2–4 GB each for Vanilla or Paper, 6 GB or more each for modded servers. Stopped servers use no RAM.
- Docker. The installer installs it if it is missing.

## Install

```bash
git clone https://github.com/Derpchees/mcserver.git
cd mcserver
sudo ./install.sh
```

Or in one line:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Derpchees/mcserver/main/install.sh)
```

The installer prepares the machine. It asks, in English or Spanish:

1. **Where the servers live**: a list of your disks with their free space. It can mount an unmounted partition permanently. It never formats anything.
2. **Where backups go**: ideally a different physical disk.
3. **Network**: all networks, or one interface such as a ZeroTier or Tailscale address.
4. **Ports**: the panel port, and the first game port. Each new server takes the next free one.
5. **Address players use**: an IP or domain.
6. Acceptance of the [Minecraft EULA](https://aka.ms/MinecraftEULA).

If the `ufw` firewall is active, it opens the panel port and 50 game ports on the chosen network.

When it finishes, **open the panel address it prints and create the administrator account**.

To install without questions, copy [`examples/answers.env`](examples/answers.env), fill it in and run `sudo ./install.sh --config my-answers.env`.

## After installing

| Task | How |
|---|---|
| Create the administrator | Open the panel the first time |
| Create a server | Sign up from the login page, or **+ Create a server** on the home page |
| Change resources, version or automation | Server → **Settings → Server and resources** |
| Limits and sign-up | **Administration** (administrators only) |
| Turn on notifications | **My account → Browser notifications** |
| Forgot a password | `sudo mcpanel-passwd <user>` (`--list` shows the users) |
| Update (keeps accounts, servers and worlds) | `git pull && sudo ./install.sh --update` |
| Uninstall | **Administration → Danger zone**, or `sudo /opt/mcpanel/uninstall.sh` |

### Import a server you already have

You can register an existing world without moving it. Import copies the mod-loader version (for example `FORGE_VERSION`) from the old container, so your mods keep working:

```bash
sudo python3 /opt/mcpanel/panel/mcpanel_core.py import-server \
    --name "My server" --owner admin --data-dir /path/to/world-folder \
    --type FORGE --version 1.20.1 --ram 8 --from-container old-container-name
```

## How it works

```
player ──► :25565, :25566, ... mcpanel-agent ──► 127.0.0.1 Docker (one container per server)
                                 │ starts the server when someone connects,
                                 │ stops it when empty, runs backups, raises alerts
browser ─► :8090 mcpanel-web (panel and accounts)
```

| Path | Contents |
|---|---|
| `/opt/mcpanel` | Panel, agent and scripts |
| `/etc/mcpanel/config.env` | System settings written by the installer |
| `/var/lib/mcpanel/mcpanel.db` | Accounts, servers, limits and events (SQLite). Passwords are stored as PBKDF2 hashes. |
| `/var/log/mcpanel/servers/<server>/` | Logs of each server: proxy, auto stop, backups, admin actions |

Services: `mcpanel-web` and `mcpanel-agent`.

## Security

- The panel uses plain HTTP. **Do not expose it to the internet.** Use it on your local network or through a VPN (ZeroTier, Tailscale, WireGuard). The installer can bind it to the VPN interface only.
- Anyone who can reach the panel can see every server's status, start any server and, while sign-up is on, create an account and a server. Turn sign-up off in **Administration** once everyone has an account.
- After 5 wrong passwords, the address is blocked for 5 minutes.
- The panel and the agent run as root because they manage Docker. File operations are confined to each server's folder.

## Troubleshooting

- **The panel does not load**: `sudo systemctl status mcpanel-web` and `sudo journalctl -u mcpanel-web -n 50`.
- **Players cannot connect, or a server does not start on connect**: `sudo journalctl -u mcpanel-agent -n 50`. Also check your firewall and the address shown in the panel.
- **A new server stays in "Preparing"**: the first time, the Minecraft image is downloaded (about 1 GB). If it fails, the server shows the error and the reason.
- **A backup failed**: `/var/log/mcpanel/servers/<server>/backup.log`.

## License

[MIT](LICENSE). Minecraft is a trademark of Mojang Studios; this project is not affiliated with Mojang or Microsoft.
