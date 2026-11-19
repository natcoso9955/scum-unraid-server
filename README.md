# SCUM Dedicated Server for Unraid — release candidate source

This is a **pre-publication release candidate**, assembled from the Phase 2.4 server source and Phase 2.4.1 UI update. Field testing was performed by the project owner on Unraid 7; this assembled candidate has **not** been run through a complete Docker build or SCUM runtime test. Windows SCUM server runs under Wine; platform compatibility is community-supported. The final cosmetic Sign Out alignment change and basic Docker HEALTHCHECK are included here but have not yet been field-tested.

## Capabilities
- SteamCMD installation/update (app `3792580`), optional `STEAMCMD_VALIDATE`
- SCUM via Wine + Xvfb, with graceful Ctrl+C on game/container stop
- Docker-published UDP 7777, 7778, 7779 and TCP 7779
- Dashboard on container TCP 8080, legacy master token and user/password sessions
- Individual SFTP accounts, same password as panel, isolated from Unraid host
- Persistent world/auth/logs in `/data`
- No custom backup/scheduler/restore feature (SCUM's native backups remain)

## Important
- For public release, **review SECURITY.md**, choose a licence, replace publishing placeholders, and validate the Unraid template in Community Apps.
- `MANAGER_TOKEN` and `SFTP_PASSWORD` are mandatory on first run. Do not publish the web dashboard on plain HTTP over the internet. TLS reverse proxy/VPN required for remote web use.
- Existing SFTP users can modify game files, so grant access only to trusted people.
- The web manager process being up is **not proof** that the game is joinable.
- `vm.max_map_count >= 1048576` was needed in the owner's Unraid test; confirm it on the host before launch.
- No official SCUM affiliation.

## Deployment
For your *existing* working Unraid project, DO NOT overwrite your `.env` or `docker-compose.yml` with these generic examples. Review `docs/RELEASE-STEPS.md` for a separate, complete release workflow.

Local source test: `docker compose -f docker-compose.yml config --quiet`, then `docker compose -f docker-compose.yml build scum`.
