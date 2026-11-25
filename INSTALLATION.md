# Installation guide — SCUM Dedicated Server

This guide covers installing the community-maintained [SCUM Dedicated Server Docker image](https://hub.docker.com/r/natcoso9955/scum-unraid) through an Unraid Docker template or from source with Docker Compose.

> **Status:** Check the [published image tags](https://hub.docker.com/r/natcoso9955/scum-unraid/tags) and the [Unraid template](https://github.com/natcoso9955/unRAID-docker/blob/master/scum-server.xml) for the version currently offered. A release-candidate tag is not a stable-release guarantee. SCUM game files are **downloaded by SteamCMD on first launch** and are not included in the image.

## Requirements

- An **x86-64 Linux host** with Docker; the Unraid template targets **Unraid 7**.
- At least **16 GB of RAM available** is recommended for this configuration; actual needs vary with world and player load.
- Sufficient persistent disk capacity for SteamCMD, Wine, the SCUM server, saves, and updates. Allow substantially more than the roughly 15 GB observed for one game installation.
- Internet access for SteamCMD's initial installation and future updates.
- Unique strong values for `MANAGER_TOKEN` and `SFTP_PASSWORD`.

### Unraid host kernel setting

The project was tested with `vm.max_map_count=1048576`. Check your host value in the **Unraid terminal**:

```bash
sysctl vm.max_map_count
```

If below `1048576`, and required by this deployment, apply a temporary change:

```bash
sysctl -w vm.max_map_count=1048576
```

This setting is **not persistent across Unraid reboots**. Configure persistence separately according to your Unraid setup. Do not run this command inside the container.

## Option A — Unraid Docker template

1. Open the template in the existing [Unraid template repository](https://github.com/natcoso9955/unRAID-docker/blob/master/scum-server.xml), or select **SCUM Dedicated Server** from Community Applications if it has been accepted and is available.
2. Set **Game Data** to a persistent host directory (for example `/mnt/user/appdata/scum-server`). It maps to `/data` in the container. Reuse the **same host directory** when replacing/upgrading the container.
3. Set a strong, unique **`SFTP_PASSWORD`** for the initial legacy `scum` SFTP account, and a separate long random **`MANAGER_TOKEN`** for master dashboard administration. These are environment variables supplied in the template, not Python source edits.
4. Review the exposed **host** ports and change them if another service already uses those numbers. In Unraid **Advanced View**, check the UDP **7779** entry as well as TCP **7779**; older template revisions may hide the UDP entry. All mappings must be distinct from other containers using the same protocol.
5. Keep `UPDATE_ON_START=true` if you want SteamCMD to check for updates on startup; set `STEAMCMD_VALIDATE=true` only if you deliberately want a full validation. Leave `WEB_COOKIE_SECURE=false` for initial **HTTP-only LAN testing**.
6. Click **Apply**, review the generated `docker run` command, and confirm every intended host port is actually mapped before starting. The first launch may take longer while SteamCMD installs the game.
7. Visit the dashboard on `http://UNRAID-IP:8383/` if you kept the default host port, or use your chosen mapped dashboard host port. Authenticate using the master token; create individual dashboard/SFTP users from the account management UI.
8. Check the logs and dashboard for successful server startup. A responding dashboard or Docker health check **does not prove SCUM is joinable**; verify with an actual SCUM client.

### Default port mappings

| Purpose | Container port | Example host port | Protocol |
| --- | --- | --- | --- |
| Game | `7777` | `7777` | UDP |
| Game | `7778` | `7778` | UDP |
| Game | `7779` | `7779` | UDP |
| Game direct connection | `7779` | `7779` | TCP |
| SFTP | `2222` | `2222` | TCP |
| Dashboard (HTTP) | `8080` | `8383` | TCP |

**Host** and **container** ports are not interchangeable: for example `17779:7779/udp` and `17779:7779/tcp` expose host port `17779`, while the server still uses container port `7779`. Whether nonstandard *external game ports* work for remote client discovery/connection depends on your network and the game's expectations; verify with a real client. Forward only the game ports required by your setup. Do not expose the dashboard's plain HTTP port directly to the internet.

### SFTP

- Host: Unraid server address or the configured public domain.
- Port: mapped SFTP **host** port (default `2222`).
- Protocol: **SFTP** (SSH File Transfer Protocol), not FTP.
- Initial username: `scum`; password: the `SFTP_PASSWORD` value, unless rotated later in the dashboard.
- Dashboard-created users use their own matching dashboard/SFTP credentials when SFTP access is enabled.
- SFTP users are chrooted inside the container's `/data`, starting in `/game`. They can modify game files: grant this access only to trusted people.

## Option B — Docker Compose from source

This repository's Compose file builds a **local image from source** rather than pulling a public Docker Hub tag. Use this method if you want to build or customise the image yourself.

Clone the source repository on the machine where Docker Compose runs:

```bash
git clone https://github.com/natcoso9955/scum-unraid-server.git
cd scum-unraid-server
cp .env.example .env
```

Edit `.env` privately. At minimum, replace both credential placeholders. Check `SCUM_APPDATA`, the external port settings, and time zone. **Never commit `.env`.**

Validate and build:

```bash
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml build scum
```

Start:

```bash
docker compose -f docker-compose.yml up -d scum
```

Follow logs:

```bash
docker compose -f docker-compose.yml logs -f scum
```

**Important:** the included Compose file fixes the *game host ports* to `7777`/`7778`/`7779`; changing only `GAME_PORT` in `.env` does **not** automatically rewrite those Docker port mappings. To use alternative host ports, edit the `ports:` lines in `docker-compose.yml` and verify the rendered configuration with `docker compose config` before starting. The Compose default dashboard bind is `127.0.0.1`, which means it may not be reachable directly from another LAN machine unless you intentionally change `WEB_BIND_IP`.

## Managing the server

The dashboard provides server lifecycle controls, update actions, logs, uptime information and account management. The master token is separate from named dashboard accounts. If a named user changes their own password, their current web session is invalidated and they must sign in again.

Password updates may take longer on some Unraid storage setups. A successful account change should be verified by signing in again and testing SFTP when enabled.

## Persistence, upgrades and backups

All SCUM game files, saves, Wine state, SteamCMD files, account records, SSH keys and logs live under **`/data`**. Replacing the Docker image or recreating the container should preserve them **as long as the same intact host directory remains mounted to `/data`**.

- Never run two SCUM containers against the **same** `/data` directory at the same time.
- Make a separate backup of your game data before upgrading or migrating. This image does **not** implement its own scheduled backup, restore or retention manager.
- Use the container's graceful Stop action; its template requests a **150-second Docker stop timeout**, but verify actual behaviour in your environment.
- An image upgrade does not automatically migrate an existing Compose deployment to the Unraid Docker Manager; do not have both managers control the same container.

## Secure remote access

The dashboard serves **HTTP** inside Docker. For remote access, use your own HTTPS reverse proxy or a trusted VPN. Do **not** port-forward its raw HTTP listener to the internet. Set `WEB_COOKIE_SECURE=true` only when accessing the dashboard exclusively over HTTPS; secure cookies can prevent login over plain HTTP. Protect the proxy with appropriate access controls and rate limiting. Use strong SFTP credentials and restrict exposure where possible.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Docker says `port is already allocated` | Review **every** host mapping, particularly UDP `7779` in Unraid Advanced View; another container may already bind it |
| Dashboard works but game is not joinable | SteamCMD/update logs, server process, required TCP/UDP ports, actual SCUM client connectivity |
| Login works on HTTP but fails behind HTTPS | Proxy headers, TLS termination, cookie setting, browser session; use `WEB_COOKIE_SECURE=true` for HTTPS-only access |
| SFTP login fails | Mapped host TCP port, user SFTP enablement, password and container logs |
| Files/accounts appear missing after recreation | Confirm the **original host data directory** is still bound to `/data`; don't initialise a second empty directory |
| Container stops before graceful shutdown finishes | Check effective Docker stop timeout and review supervisor/game logs |

For problems, include the relevant redacted container logs and open an [issue](https://github.com/natcoso9955/scum-unraid-server/issues). **Never post tokens, passwords, hashes, or private SSH keys.**

---

This is an unofficial community project and is not affiliated with or endorsed by the developers of SCUM. Unraid® is a trademark of Lime Technology, Inc. This project is not affiliated with or endorsed by Lime Technology.
