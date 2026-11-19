# Security and release cautions

- Publish **source and Dockerfile only**. Never commit `.env`, `/data`, passwords, auth JSON, saved characters, SSH host keys or game binaries.
- The container runs entrypoint, SFTP provisioning and dashboard supervisor as root; SCUM process is `scum` unprivileged. This is a security boundary for trusted administrators, **not** a hardened multi-tenant hosting platform.
- Web dashboard currently uses direct HTTP. Remote login needs HTTPS reverse proxy (or VPN) and appropriate forwarded headers / secure-cookie configuration (`WEB_COOKIE_SECURE=true` behind HTTPS). Avoid public exposure without rate-limiting, TLS, authentication abuse testing and an audit.
- Password operations can be slow on Unraid user shares; investigate before scale-out. Do not remove bcrypt or storage synchronization to gain speed.
- SFTP users can write game files; limit users to trusted operators; credentials are distinct from Unraid host SSH.
- Legacy `scum` SFTP account is enabled by default. Rotate its credential before external exposure.
- Container restart is not a full world integrity test; validate save persistence and conduct recovery drills using game-appropriate tools.
- A running Wine process does not guarantee SCUM is accepting player connections.
