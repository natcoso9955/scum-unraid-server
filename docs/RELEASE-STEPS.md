# Complete release path (Unraid host and GitHub/Docker Hub)

## A. Keep the working installation intact
Do not overlay the release-candidate files onto the production Compose project until you have tested a separate copy. Never package `/mnt/user/gaming_appdata/scum-server` or `.env` in a public repository.

## B. Validate project offline
From a machine with Docker, build `docker build -f docker/Dockerfile -t scum-unraid:rc1 .`. This only validates image construction, not game connectivity. Run `python3 -m unittest discover -s tests -p 'test_*.py'` in an environment with Python; not on bare Unraid.

## C. Create a public repository
1. Create `scum-unraid-server` on GitHub.
2. Choose an OSI-approved license after reviewing rights to original and third-party files; add a `LICENSE` file. Never add Steam game binaries.
3. Replace `YOUR_GITHUB_USERNAME` and `YOUR_DOCKERHUB_USERNAME` in `ca_profile.xml` and `templates/scum-server.xml`.
4. Commit source without `.env` or runtime data.
5. Create a Docker Hub repository named `scum-unraid`.
6. Set GitHub Actions repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (Docker Hub personal access token, not your account password).
7. Test workflow manually from Actions. For a tagged release, push a tag like `v0.1.0-rc1` and verify public image `USERNAME/scum-unraid:v0.1.0-rc1` exists.
8. Keep `latest` unassigned until an approved stable release. Test pullability by unauthenticated `docker pull`.

## D. Test using a separate disposable Unraid install
1. Do not reuse the running container name, default ports, or `/data` path for a parallel test.
2. Use a *separate* temporary host folder and alternate ports. Do not share SCUM world files between running instances.
3. Validate dashboard login / account creation / SFTP / password rotation / SteamCMD update / game client connect / graceful stop / character persistence.
4. Confirm remote HTTPS and SFTP access restrictions before public release.

## E. Community Applications
1. After publication, update `templates/scum-server.xml` to the actual public image tag and repo URLs. Supply a real icon, support destination, project description and licence.
2. Verify that a **single-container Unraid Docker template** works without Compose or local build tools. Validate required environment secrets and port mappings.
3. In `https://ca.unraid.net/submit`, use Validate then Scan. Fix all errors and submit when clean.

## F. Local Unraid source-install example (not production rollout)
```sh
cd /boot/config/plugins/compose.manager/projects/scum-server
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml build scum
# Run only when no players are online:
docker compose -f docker-compose.yml up -d --no-deps --force-recreate scum
```

## G. Rollback
Keep a *tagged, known-good* previous image (`docker tag scum-unraid:phase1-local scum-unraid:working-backup` before building another image with the same tag), the previous Compose project source, and a **separate** tested world backup. Recreating an older container must not overwrite newer game data unintentionally.
