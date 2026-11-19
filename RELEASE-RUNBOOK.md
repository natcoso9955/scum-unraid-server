# SCUM Docker Hub / existing Unraid template repository — release runbook

**Scope:** Docker image source is published in its own GitHub repository. The user already has an Unraid template repository; copy ONLY `templates/scum-server.xml` into that existing repository. HTTPS is terminated by user's reverse proxy; do not add HTTPS services to the container.

## A. Confirm source matches the working installation

On **Lupus (Unraid host)**, create a *source-only* comparison archive. This does not stop Docker and does not include `.env` or `/data`:

```bash
PROJECT=/boot/config/plugins/compose.manager/projects/scum-server
cd "$PROJECT" || exit 1
zip -r /boot/scum-current-source-review.zip docker docker-compose.yml -x '*/__pycache__/*' '*.pyc'
```

Review/diff against the extracted release source on your Windows PC. Do not copy the release-candidate files over the working deployment before this comparison. The tested Phase 2.4.1 installation is the reference; the candidate was assembled from previous packages.

## B. Configure the release source on Windows (PowerShell)

Extract this ZIP into a new Windows working folder (not Unraid's `/boot` or gaming appdata); `cd` into `scum-publishing-kit`. Edit your GitHub/Docker Hub identities with these required parameters:

```powershell
.\configure-release.ps1 -DockerHubUser 'YOUR_DOCKERHUB_USER' -SourceGitHubUser 'YOUR_GITHUB_USER' -TemplateGitHubUser 'YOUR_TEMPLATE_GITHUB_USER' -TemplateRepo 'YOUR_EXISTING_TEMPLATE_REPO'
```

You may need `powershell -ExecutionPolicy Bypass -File .\configure-release.ps1 ...` for script execution; only use this for a script you have reviewed. Review `templates/scum-server.xml`; leave the template URL pointed at your existing template repo. Create a real licence file (MIT or another OSI-approved licence you have rights to apply) and delete `LICENSE-DECISION-REQUIRED.txt` before publication. Review all code and dependencies' licensing. Remove `Beta` only after production signoff.

## C. Create the image source repository and publish

1. In GitHub, create an empty public repository called `scum-unraid-server` under the account used above (no prefilled README, .gitignore or licence).
2. Create a public `scum-unraid` Docker Hub repository.
3. In source GitHub repository -> Settings -> Secrets and variables -> Actions, add `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (Docker Hub access token, not account password).
4. From the source directory, **Windows PowerShell**:

```powershell
git init
git branch -M main
git add .
git status --short
git diff --cached --name-only
git commit -m "Prepare SCUM Docker release candidate"
git remote add origin https://github.com/YOUR_GITHUB_USER/scum-unraid-server.git
git push -u origin main
```

Do not proceed if any `.env`, auth credentials, game binaries, game database, or `/data` contents appear in staged files.

5. GitHub Actions -> `Docker Hub image candidate` -> `Run workflow` to smoke-check CI. Tag only after CI success and reconciliation with working source:

```powershell
git tag v0.1.0-rc1
git push origin v0.1.0-rc1
```

The workflow publishes `YOUR_DOCKERHUB_USER/scum-unraid:v0.1.0-rc1`. It does not tag `latest`.

## D. Verify the public Docker Hub image on Unraid (no interruption)

```bash
IMAGE=YOUR_DOCKERHUB_USER/scum-unraid:v0.1.0-rc1
docker pull "$IMAGE" || exit 1
docker image inspect "$IMAGE" --format 'ID={{.Id}} ARCH={{.Architecture}}' || exit 1
docker run --rm --entrypoint /bin/sh "$IMAGE" -c 'test -f /opt/scum/supervisor.py && test -f /opt/scum/user_accounts.py && test -f /opt/scum/web/index.html && python3 -c "import bcrypt" && echo IMAGE_CONTENTS_OK'
```

This does **not** validate game startup. For a full test use a separate `/data` directory, distinct container name and ports; never run two SCUM processes against the same save directory. Or schedule a maintenance window to test the published image on the existing install, after preserving a source backup and a separate world backup.

## E. Publish the Unraid template in the existing template repo

Copy `templates/scum-server.xml` from this kit to the *existing* template GitHub repository at its `templates/scum-server.xml` path. Commit and push it there. Do not create or submit a second template repository. Your existing repo's `ca_profile.xml` remains authoritative. Verify the raw template URL returns XML and that `<Repository>` points at the image you actually published.

Use the Unraid Community Apps portal `https://ca.unraid.net/submit` for template Validate -> Scan, referencing your existing repo. Template includes TCP 7779 in addition to UDP ports and an explicit 150-second stop-timeout request; verify effective stop timeout in Unraid. Official guidance: https://ca.unraid.net/submit/help/repository-xml

## F. Credentials, proxy and persistence

- `MANAGER_TOKEN` and `SFTP_PASSWORD` are **environment variables**. The legacy `scum` SFTP password set in ENV is a bootstrap value; a rotated persisted hash under `/data/ssh/` takes precedence on subsequent boots.
- New panel user credentials are managed through the web UI and stored as hashes/registry under `/data/ssh/`, not in ENV.
- `/data` bind mount holds SCUM game, saves, Wine, SteamCMD, SSH keys, accounts and logs. Using the *same* mapping preserves state across new image containers. A different host folder makes data appear missing; do not map to an empty path for migration.
- Web service is plain HTTP inside Docker. Put it behind your reverse proxy and use HTTPS externally; do not forward dashboard TCP 8383 publicly. `WEB_COOKIE_SECURE=true` only when accessing the panel via HTTPS (HTTP-only LAN login will not retain a secure cookie).
- Current source does **not** provide verified public-facing brute-force protection; implement/review access controls at the reverse proxy, and test the app/session security before accepting public remote logins. SFTP needs strong passwords and ideally IP allowlisting or VPN.
- Run `sysctl vm.max_map_count` to check mapping; if below 1048576 and needed, `sysctl -w vm.max_map_count=1048576` is temporary until host reboot. Persistence on Unraid must be configured separately.
- Preserve character/world files via an independent backup mechanism when moving a tested instance.

## G. Template smoke test without breaking existing Compose installation

Installing a second SCUM container with the same host ports, name or data path will conflict. Prefer a disposable separate host directory and **different** ports for first install, with enough free disk for a new server install; or stop/remove the Compose-managed container during a controlled migration and reuse the same `/data` mapping. Never run two game servers against the same files. Confirm logs, dashboard auth, SFTP, TCP 7779 join, Ctrl+C graceful stop, and persistence before releasing as stable.
