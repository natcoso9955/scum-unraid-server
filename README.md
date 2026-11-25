<p align="center">
  <img src="assets/SCUM-Dedicated-Server-Logo.png"
       alt="SCUM Dedicated Server logo"
       width="800">
</p>

# SCUM Dedicated Server for Unraid

<!-- SCUM BADGES -->
[![Build](https://github.com/natcoso9955/scum-unraid-server/actions/workflows/dockerhub.yml/badge.svg)](https://github.com/natcoso9955/scum-unraid-server/actions/workflows/dockerhub.yml)
[![Version](https://img.shields.io/github/v/tag/natcoso9955/scum-unraid-server?sort=semver&include_prereleases&style=flat-square&label=version)](https://github.com/natcoso9955/scum-unraid-server/tags)
[![Docker Pulls](https://img.shields.io/docker/pulls/natcoso9955/scum-unraid?style=flat-square&logo=docker&label=Docker%20Pulls)](https://hub.docker.com/r/natcoso9955/scum-unraid)
[![License](https://img.shields.io/github/license/natcoso9955/scum-unraid-server?style=flat-square)](LICENSE)
![Platform](https://img.shields.io/badge/platform-linux%2Famd64-blue?style=flat-square&logo=linux)
![Languages](https://img.shields.io/badge/languages-Python%20%7C%20Shell-3776AB?style=flat-square&logo=python)
<!-- END SCUM BADGES -->

A community-maintained Docker solution for hosting a **SCUM Dedicated Server** on Unraid 7 and compatible Linux systems.

Installs the SCUM dedicated server through SteamCMD, with optional automatic updates on container startup, and runs the Windows server under Wine. Includes a web-based management dashboard, graceful server controls, persistent game data, and integrated SFTP access with unified user management.

Supports deployment using Docker Compose or an Unraid Docker template. Community Applications distribution is planned.

## Features

- SteamCMD installation and optional startup updates (app `3792580`); optional full file validation with `STEAMCMD_VALIDATE`
- SCUM via Wine + Xvfb, with graceful Ctrl+C shutdown handling
- Game networking: UDP 7777, 7778, 7779 and TCP 7779 (configurable **host** port mappings)
- Web dashboard with game controls, uptime, logs, and master token/user sessions (container TCP 8080)
- Individual SFTP accounts with shared web/SFTP credentials for enabled named users
- Persistent game files, saves, authentication data and logs under `/data`

## Important

- **Credentials:** Set unique strong `MANAGER_TOKEN` and `SFTP_PASSWORD` values before the first launch. The legacy `scum` SFTP password can be rotated later.
- **Remote access:** The dashboard serves HTTP internally. Use your own HTTPS reverse proxy or trusted VPN; never expose its plain HTTP listener directly to the internet. Read [SECURITY.md](SECURITY.md).
- **SFTP permissions:** Enabled SFTP users can modify shared game files. Grant access only to trusted people.
- **Game readiness:** A running dashboard or healthy container does **not** prove that SCUM is joinable.
- **Host configuration:** The project was tested with `vm.max_map_count=1048576`; check your Linux host setting if necessary.
- **Backups:** The image does not include a custom backup scheduler, restore interface or retention manager. Back up persistent game data separately; SCUM's own backup behaviour is independent.
- **Licence and affiliation:** The project's own source is licensed under [MIT](LICENSE). This is an unofficial community project, not affiliated with or endorsed by the developers of SCUM. Unraid® is a trademark of Lime Technology, Inc. This project is not affiliated with or endorsed by Lime Technology.

## Installation

See the **[Installation Guide](INSTALLATION.md)** for Unraid template setup, Docker Compose, ports, first-run credentials, SFTP, persistent data and troubleshooting.

For maintainers publishing Docker images or updating the Unraid template, see the [Release Runbook](RELEASE-RUNBOOK.md).

### Building locally from source

Validate the Compose configuration:

```bash
docker compose -f docker-compose.yml config --quiet
```

Build the image:

```bash
docker compose -f docker-compose.yml build scum
```

SCUM game files are downloaded separately through SteamCMD and are **not bundled with the Docker image**.
