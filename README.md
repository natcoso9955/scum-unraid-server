# SCUM Dedicated Server for Unraid

Community-maintained SCUM dedicated server for Unraid 7. The v0.1.0-rc1 image is a release candidate; standalone Unraid template installation and runtime validation are still required.

## Capabilities
- SteamCMD installation/update (app `3792580`), optional `STEAMCMD_VALIDATE`
- SCUM via Wine + Xvfb, with graceful Ctrl+C on game/container stop
- Docker-published UDP 7777, 7778, 7779 and TCP 7779
- Dashboard on container TCP 8080, legacy master token and user/password sessions
- Individual SFTP accounts, same password as panel, isolated from Unraid host
- Persistent world/auth/logs in `/data`
- No custom backup/scheduler/restore feature (SCUM's native backups remain)

## Important
- Licensed under MIT. Review [SECURITY.md](SECURITY.md) before exposing management services remotely. Validate the Unraid template before submitting it to Community Applications.
- `MANAGER_TOKEN` and `SFTP_PASSWORD` are mandatory on first run. Do not publish the web dashboard on plain HTTP over the internet. TLS reverse proxy/VPN required for remote web use.
- Existing SFTP users can modify game files, so grant access only to trusted people.
- The web manager process being up is **not proof** that the game is joinable.
- `vm.max_map_count >= 1048576` was needed in the owner's Unraid test; confirm it on the host before launch.
- No official SCUM affiliation.

## Deployment
For installation and publishing guidance, see [RELEASE-RUNBOOK.md](RELEASE-RUNBOOK.md). For existing installations, preserve the current `/data` mapping and credentials; do not overwrite working `.env` or Compose configuration with generic examples.

Local source test: `docker compose -f docker-compose.yml config --quiet`, then `docker compose -f docker-compose.yml build scum`.
