"""Small file-backed SCUM panel/SFTP identity registry.

This module runs as root inside the container. Never expose the files by SFTP.
"""
import bcrypt
import hmac
import json
import os
import re
import secrets
import subprocess
import threading
import time
from pathlib import Path

AUTH_DIR = Path('/data/ssh')    # root-owned /data/ssh, unreachable from SFTP users
USERS_FILE = AUTH_DIR / 'users.json'
HTPASSWD = AUTH_DIR / 'users.htpasswd'
GAME_DIR = Path('/data/game')
ACL_MARKER = AUTH_DIR / '.game-acl-v1'
LOCK = threading.RLock()
SESSIONS = {}  # Server-side, ephemeral, survives no container recreation
SESSION_TTL = 8 * 3600
USERNAME = re.compile(r'^[a-z][a-z0-9_-]{2,31}$')
RESERVED = {'scum', 'root', 'admin', 'daemon', 'nobody', 'sshd'}


def _run(args, input_text=None):
    result = subprocess.run(args, input=input_text, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f'Account provisioning operation failed: {args[0]}')
    return result.stdout


def _load():
    try:
        entries = json.loads(USERS_FILE.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    if not isinstance(entries, dict) or entries.get('schema') != 1 or not isinstance(entries.get('users'), dict):
        raise RuntimeError('Invalid persistent user registry; refusing to overwrite')
    return entries['users']


def _atomic(path, value):
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    if AUTH_DIR.is_symlink():
        raise RuntimeError('Authentication directory cannot be a symlink')
    tmp = path.with_name('.' + path.name + '.' + secrets.token_hex(8))
    try:
        with os.fdopen(os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as f:
            f.write(value)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _write(users):
    _atomic(USERS_FILE, json.dumps({'schema': 1, 'users': users}, indent=2, sort_keys=True) + '\n')
    _atomic(HTPASSWD, ''.join(f'{name}:{entry["web_hash"]}\n' for name, entry in sorted(users.items()) if entry.get('enabled')))


def _validate_username(name):
    if not isinstance(name, str) or not USERNAME.fullmatch(name) or name in RESERVED:
        raise ValueError('Username must be 3–32 lowercase letters, digits, _ or -, start with a letter, and not be reserved')
    # Do not take over an existing host/container OS account outside our registry.


def _validate_password(password):
    if not isinstance(password, str) or not 16 <= len(password) <= 72:
        raise ValueError('Password must be 16–72 characters')
    if any(ord(c) < 32 or ord(c) == 127 for c in password) or ':' in password:
        raise ValueError('Password must not contain control characters or colon')
    if len(password.encode('utf-8')) > 72:
        raise ValueError('Password must not exceed 72 UTF-8 bytes (bcrypt limit)')


def _hashes(password):
    web_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('ascii')
    # Password travels via stdin and never a command argument.
    shadow_hash = _run(['openssl', 'passwd', '-6', '-stdin'], password + '\n').strip()
    if not shadow_hash.startswith('$6$'):
        raise RuntimeError('Failed to generate Linux password hash')
    return web_hash, shadow_hash


def _os_exists(name):
    return subprocess.run(['getent', 'passwd', name], capture_output=True, check=False).returncode == 0


def _sync_user(name, entry):
    if not _os_exists(name):
        _run(['useradd', '-M', '-g', 'scum', '-d', '/game', '-s', '/usr/sbin/nologin', name])
    # chpasswd -e takes an encrypted Linux shadow hash on stdin.
    _run(['chpasswd', '-e'], f'{name}:{entry["shadow_hash"]}\n')
    if not entry.get('enabled', True) or not entry.get('sftp_enabled', True):
        _run(['usermod', '-L', name])
    else:
        _run(['usermod', '-U', name])


def sync_on_start():
    with LOCK:
        users = _load()
        for name, entry in users.items():
            _validate_username(name)
            _sync_user(name, entry)
        _write(users)  # rebuild .htpasswd from protected canonical registry
        return len(users)


def _set_game_permissions():
    """One-time shared group ACL for existing game files and inherited future files.

    May take time on large Steam installations; invoked only when first account created.
    """
    if ACL_MARKER.exists():
        return
    # Apply group access to existing files; directories get inherited default ACLs.
    _run(['setfacl', '-R', '-m', 'g:scum:rwX', str(GAME_DIR)])
    _run(['sh', '-c', 'find /data/game -type d -exec setfacl -m d:g:scum:rwx {} +'])
    _atomic(ACL_MARKER, 'ACL sharing configured\n')


def list_users():
    with LOCK:
        return [{'username': name, 'enabled': bool(e['enabled']), 'sftp_enabled': bool(e['sftp_enabled'])}
                for name, e in sorted(_load().items())]


def create(name, password, sftp_enabled=True):
    _validate_username(name)
    _validate_password(password)
    if not isinstance(sftp_enabled, bool):
        raise ValueError('sftp_enabled must be boolean')
    with LOCK:
        users = _load()
        if name in users or _os_exists(name):
            raise ValueError('Username is already in use')
        web_hash, shadow_hash = _hashes(password)
        if sftp_enabled:
            _set_game_permissions()
        entry = {'web_hash': web_hash, 'shadow_hash': shadow_hash, 'enabled': True,
                 'sftp_enabled': sftp_enabled}
        # Provision OS account first: a failed provisioning must not create a usable web login.
        _sync_user(name, entry)
        users[name] = entry
        _write(users)
        return {'username': name, 'enabled': True, 'sftp_enabled': sftp_enabled}


def verify(name, password):
    if not isinstance(name, str) or not isinstance(password, str):
        return False
    with LOCK:
        entry = _load().get(name)
        if not entry or not entry.get('enabled'):
            return False
        try:
            return bcrypt.checkpw(password.encode('utf-8'), entry['web_hash'].encode('ascii'))
        except (ValueError, KeyError):
            return False


def login(name, password):
    if not verify(name, password):
        raise PermissionError('Invalid username or password')
    sid = secrets.token_urlsafe(32)
    with LOCK:
        SESSIONS[sid] = (name, time.monotonic() + SESSION_TTL)
    return sid


def session_username(sid):
    with LOCK:
        session = SESSIONS.get(sid)
        if not session:
            return None
        name, expiry = session
        if time.monotonic() >= expiry or not _load().get(name, {}).get('enabled'):
            SESSIONS.pop(sid, None)
            return None
        return name


def logout(sid):
    with LOCK:
        SESSIONS.pop(sid, None)


def invalidate_user(name):
    with LOCK:
        for sid, (n, _) in list(SESSIONS.items()):
            if n == name:
                del SESSIONS[sid]


def change_password(name, password):
    _validate_password(password)
    with LOCK:
        users = _load()
        if name not in users:
            raise ValueError('Unknown username')
        web_hash, shadow_hash = _hashes(password)
        entry = dict(users[name], web_hash=web_hash, shadow_hash=shadow_hash)
        _sync_user(name, entry)
        users[name] = entry
        _write(users)
        invalidate_user(name)


def modify(name, enabled=None, sftp_enabled=None):
    with LOCK:
        users = _load()
        if name not in users:
            raise ValueError('Unknown username')
        entry = dict(users[name])
        if enabled is not None:
            if not isinstance(enabled, bool):
                raise ValueError('enabled must be boolean')
            entry['enabled'] = enabled
        if sftp_enabled is not None:
            if not isinstance(sftp_enabled, bool):
                raise ValueError('sftp_enabled must be boolean')
            if sftp_enabled:
                _set_game_permissions()
            entry['sftp_enabled'] = sftp_enabled
        _sync_user(name, entry)
        users[name] = entry
        _write(users)
        if not entry['enabled']:
            invalidate_user(name)
        return {'username': name, 'enabled': entry['enabled'], 'sftp_enabled': entry['sftp_enabled']}


def delete(name):
    with LOCK:
        users = _load()
        if name not in users:
            raise ValueError('Unknown username')
        # Lock first and invalidate web session; don't delete game files.
        _run(['usermod', '-L', name])
        invalidate_user(name)
        del users[name]
        _write(users)
        if _os_exists(name):
            _run(['userdel', name])


def password_policy():
    return {'minimum_length': 16, 'maximum_length': 72}

if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['sync']:
        print(f'[scum-init] Restored {sync_on_start()} panel/SFTP account(s)')
    else:
        sys.exit('Use: user_accounts.py sync')
