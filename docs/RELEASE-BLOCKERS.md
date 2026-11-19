# Pre-publication gates

- [ ] Confirm this assembled source matches the *actual deployed* Phase 2.4.1 version on Lupus; reconcile any changes not captured in the prior archives.
- [ ] Run real Docker image build on Unraid or CI and smoke-test dashboard/SFTP.
- [ ] Test Unraid Docker Manager template install (not only Compose Manager), especially initial environment variables and mapped ports.
- [ ] Re-test SteamCMD install on a clean data directory and SCUM direct-connect TCP 7779 with current game version.
- [ ] Verify default credentials cannot be accidentally published; add admin/login rate limiting and review CSRF/session security before internet deployment.
- [ ] Test password change latency and logging (cosmetic Sign Out alignment can be included here).
- [ ] Document and verify HTTPS reverse proxy or VPN, no public plain HTTP dashboard.
- [ ] Choose OSI-approved license and verify third-party rights / game-server redistribution terms.
- [ ] Provide actual public image, GitHub URLs, icon, and support location.
- [ ] Run Community Apps Validate + Scan and resolve submission findings.
- [ ] Character and world save recovery test. The custom restore system is deliberately absent.
