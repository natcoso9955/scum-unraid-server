#!/usr/bin/env bash
set -Eeuo pipefail
: "${SFTP_PASSWORD:?Set SFTP_PASSWORD to a strong password}"
if [[ "$SFTP_PASSWORD" == *$'\n'* || "$SFTP_PASSWORD" == *:* ]]; then
  echo 'SFTP_PASSWORD must not contain newlines or colons' >&2; exit 2
fi
if [[ "$(id -u)" != 0 ]]; then echo 'Run container entrypoint as root (game process runs unprivileged)' >&2; exit 2; fi
for folder in game wine steamcmd logs backups config; do
  mkdir -p "/data/$folder"
  chown scum:scum "/data/$folder"
done
# Chroot root directory MUST remain owned by root, and not writable by the SFTP user.
chown root:root /data
chmod 0755 /data
mkdir -p /data/ssh /run/sshd
chmod 0700 /data/ssh
chown root:root /data/ssh
for t in ed25519 rsa; do
  if [[ ! -f /data/ssh/ssh_host_${t}_key ]]; then
    ssh-keygen -q -t "$t" -N '' -f "/data/ssh/ssh_host_${t}_key"
  fi
done
chmod 600 /data/ssh/ssh_host_*_key
chmod 644 /data/ssh/ssh_host_*_key.pub
# Persisted dashboard-managed password hash wins on container restarts.
if [[ -s /data/ssh/scum-password.hash ]]; then
  HASH=$(cat /data/ssh/scum-password.hash)
  usermod -p "$HASH" scum
  unset HASH
else
  printf 'scum:%s\n' "$SFTP_PASSWORD" | chpasswd
fi
unset SFTP_PASSWORD
# Restore dashboard-managed panel users into ephemeral /etc/passwd and /etc/shadow.
# /data/ssh is persistent, root-owned and inaccessible to chrooted SFTP clients.
python3 /opt/scum/user_accounts.py sync
cat >/etc/ssh/sshd_config <<'CONFIG'
Port 2222
ListenAddress 0.0.0.0
HostKey /data/ssh/ssh_host_ed25519_key
HostKey /data/ssh/ssh_host_rsa_key
PasswordAuthentication yes
KbdInteractiveAuthentication no
PubkeyAuthentication no
PermitRootLogin no
AllowGroups scum
PermitTTY no
AllowTcpForwarding no
X11Forwarding no
Subsystem sftp internal-sftp
Match Group scum
    ChrootDirectory /data
    ForceCommand internal-sftp -d /game -u 0002
    PermitTunnel no
CONFIG
/usr/sbin/sshd -t
exec python3 /opt/scum/supervisor.py
