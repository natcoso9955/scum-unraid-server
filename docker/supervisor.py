#!/usr/bin/env python3
"""SCUM Phase 2 management supervisor, merged from field-tested Phase 1.

Ctrl+C and character persistence have been field-tested once on Unraid.
This does not establish complete database consistency for all game-state changes.
"""
import fcntl
import json
import os
import pty
import queue
import select
import signal
import subprocess
import sys
import termios
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import hmac
from http.cookies import SimpleCookie
import user_accounts as accounts

ROOT = Path('/data')
GAME = ROOT / 'game'
CMD = ROOT / 'steamcmd' / 'steamcmd.sh'
EXE = GAME / 'SCUM' / 'Binaries' / 'Win64' / 'SCUMServer.exe'
STOP_EVENT = threading.Event()
LOCK = threading.RLock()
PENDING = queue.Queue(maxsize=1)
RECENT = deque(maxlen=500)
STATE = {'phase': 'initialising', 'game_pid': None, 'game_running': False,
         'last_error': None, 'last_action': None, 'started_at': None,
         'shutdown_verified': False}
TOKEN = os.environ.get('MANAGER_TOKEN', '')
WEB = Path('/opt/scum/web/index.html')
LOG_DIR = ROOT / 'logs'
LOG_FILE = LOG_DIR / 'supervisor.log'
GAME_LOG_FILE = LOG_DIR / 'game-console.log'
FILE_LOCK = threading.Lock()
BOOT_MONO = time.monotonic()
GAME_MONO = None
HISTORY_PATH = ROOT / 'logs' / 'lifecycle-history.json'
HISTORY = deque(maxlen=40)
SFTP_SHADOW = ROOT / 'ssh' / 'scum-password.hash'

def load_history():
    try:
        entries = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
        if isinstance(entries, list):
            for entry in entries[-40:]:
                if isinstance(entry, dict):
                    HISTORY.append(entry)
    except (OSError, ValueError, TypeError):
        pass

def record_exit(reason, code):
    global GAME_MONO
    entry = {'at': datetime.now(timezone.utc).isoformat(), 'reason': reason,
             'exit_code': code, 'duration_seconds': int(time.monotonic()-GAME_MONO) if GAME_MONO is not None else None}
    GAME_MONO = None
    with LOCK:
        HISTORY.append(entry)
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            tmp = HISTORY_PATH.with_suffix('.tmp')
            tmp.write_text(json.dumps(list(HISTORY)), encoding='utf-8')
            os.chmod(tmp, 0o600)
            os.replace(tmp, HISTORY_PATH)
        except OSError as exc:
            log(f'WARNING unable to persist lifecycle history: {exc}')

def sftp_status():
    # Only an administrative account status and the public SSH host key; never expose password or hash.
    p = subprocess.run(['getent', 'passwd', 'scum'], capture_output=True, text=True, check=False)
    fingerprint = None
    pub = ROOT / 'ssh' / 'ssh_host_ed25519_key.pub'
    if pub.exists():
        f = subprocess.run(['ssh-keygen', '-lf', str(pub)], capture_output=True, text=True, check=False)
        if f.returncode == 0:
            fingerprint = f.stdout.strip()
    return {'account': 'scum', 'exists': p.returncode == 0,
            'password_persisted': SFTP_SHADOW.is_file(), 'port_inside_container': 2222,
            'host_key_fingerprint': fingerprint,
            'remote_directory': '/game', 'scope': 'SFTP-only chroot /data'}

def rotate_sftp_password(password):
    if not isinstance(password, str) or not 16 <= len(password) <= 128:
        raise ValueError('SFTP password must be 16..128 characters')
    if any(c in password for c in ('\n', '\r', '\x00')):
        raise ValueError('Password must not contain newline or NUL')
    # chpasswd accepts password on stdin. Nothing is placed on argv or written to logs.
    changed = subprocess.run(['chpasswd'], input='scum:'+password+'\n',
                             text=True, capture_output=True, check=False)
    if changed.returncode:
        raise RuntimeError('SFTP password update failed')
    shadow = subprocess.run(['getent', 'shadow', 'scum'], capture_output=True, text=True)
    if shadow.returncode or len(shadow.stdout.split(':')) < 2:
        raise RuntimeError('Password changed, but could not persist hash; check persistent storage before restart')
    hash_value = shadow.stdout.split(':')[1]
    if not hash_value or hash_value in ('!', '*'):
        raise RuntimeError('Password changed, but resulting hash is invalid')
    SFTP_SHADOW.parent.mkdir(parents=True, exist_ok=True)
    tmp = SFTP_SHADOW.with_suffix('.tmp')
    with tmp.open('w') as f:
        f.write(hash_value+'\n')
    os.chmod(tmp, 0o600)
    os.replace(tmp, SFTP_SHADOW)
    log('SFTP account scum password rotated; hash stored in protected persistent storage')


def append_file(path, line):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with FILE_LOCK, path.open('a', encoding='utf-8', errors='replace') as target:
            target.write(line + '\n')
    except OSError as exc:
        print(f'[scum-init] WARNING persistent log write failed: {exc}', flush=True)



def log(message):
    line = f'[scum-init] {message}'
    print(line, flush=True)
    append_file(LOG_FILE, datetime.now(timezone.utc).isoformat() + ' ' + line)
    with LOCK:
        RECENT.append(line)


def set_state(**changes):
    with LOCK:
        STATE.update(changes)


def env_int(key, default, minimum, maximum):
    value = int(os.getenv(key, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f'{key} must be {minimum}..{maximum}')
    return value


def run_as_scum(argv, **kwargs):
    return subprocess.Popen(['gosu', 'scum', *argv],
                            env={**os.environ, 'HOME': '/home/scum'}, **kwargs)


def stop_signal(_signum, _frame):
    STOP_EVENT.set()


signal.signal(signal.SIGTERM, stop_signal)
signal.signal(signal.SIGINT, stop_signal)


def install():
    set_state(phase='updating')
    if not CMD.exists():
        log('Downloading Valve SteamCMD Linux bootstrap')
        download = run_as_scum(['curl', '-fL', '--retry', '3', '--connect-timeout', '20',
                                'https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz',
                                '-o', '/data/steamcmd/steamcmd.tar.gz'])
        if download.wait() != 0:
            raise RuntimeError('SteamCMD bootstrap download failed')
        unpack = run_as_scum(['tar', '-xzf', '/data/steamcmd/steamcmd.tar.gz',
                              '-C', '/data/steamcmd'])
        if unpack.wait() != 0:
            raise RuntimeError('SteamCMD extraction failed')
        (ROOT / 'steamcmd' / 'steamcmd.tar.gz').unlink(missing_ok=True)
    if os.getenv('UPDATE_ON_START', 'true').lower() not in ('true', '1', 'yes') and EXE.exists():
        log('Skipping startup update because UPDATE_ON_START=false')
        return
    steamcmd_update()


def steamcmd_update():
    set_state(phase='updating')
    validate = os.getenv('STEAMCMD_VALIDATE', 'false').lower() in ('true', '1', 'yes')
    arguments = [str(CMD), '+@sSteamCmdForcePlatformType', 'windows',
                 '+force_install_dir', str(GAME), '+login', 'anonymous',
                 '+app_update', '3792580']
    if validate:
        arguments.append('validate')
    arguments.append('+quit')
    log('SteamCMD update starting; full file validation ' + ('ON' if validate else 'OFF'))
    for attempt in range(1, 4):
        p = run_as_scum(arguments)
        while p.poll() is None:
            if STOP_EVENT.is_set():
                p.terminate()
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    p.kill()
                raise InterruptedError('Stopped during SteamCMD update')
            time.sleep(0.5)
        if p.returncode == 0 and EXE.is_file():
            log('SteamCMD update completed; SCUM executable found')
            return
        log(f'SteamCMD attempt {attempt}/3 failed (exit {p.returncode})')
        if attempt != 3:
            time.sleep(10)
    raise RuntimeError('SteamCMD failed to install/verify SCUM executable')


class ManagerHandler(BaseHTTPRequestHandler):
    server_version = 'SCUMManager/0.2.4'

    def log_message(self, fmt, *args):
        return  # Do not expose access requests or credentials in container logs.

    def respond(self, code, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _session_id(self):
        try:
            jar = SimpleCookie()
            jar.load(self.headers.get('Cookie', ''))
            return jar['scum_session'].value if 'scum_session' in jar else None
        except Exception:
            return None

    def identity(self):
        supplied = self.headers.get('Authorization', '')
        if TOKEN and hmac.compare_digest(supplied.encode('utf-8'), ('Bearer ' + TOKEN).encode('utf-8')):
            return {'kind': 'admin', 'username': 'administrator'}
        username = accounts.session_username(self._session_id())
        return {'kind': 'user', 'username': username} if username else None

    def authorized(self):
        return self.identity() is not None

    def _post_allowed(self):
        # Prevent cross-site form requests to cookie-authenticated write endpoints.
        # Custom header requires a CORS preflight for cross-origin browser callers.
        if self.headers.get('X-SCUM-Request') != '1':
            self.respond(403, {'error': 'Missing anti-CSRF request header'})
            return False
        host = self.headers.get('Host', '')
        origin = self.headers.get('Origin')
        if origin and origin not in ('http://' + host, 'https://' + host):
            self.respond(403, {'error': 'Cross-origin writes forbidden'})
            return False
        return True

    def _cookie(self, sid, clear=False):
        cookie = SimpleCookie()
        cookie['scum_session'] = sid
        cookie['scum_session']['path'] = '/'
        cookie['scum_session']['httponly'] = True
        cookie['scum_session']['samesite'] = 'Strict'
        if clear:
            cookie['scum_session']['max-age'] = 0
        if os.getenv('WEB_COOKIE_SECURE', 'false').lower() in ('1', 'true', 'yes'):
            cookie['scum_session']['secure'] = True
        return cookie.output(header='').strip()

    def respond_with_cookie(self, code, payload, sid, clear=False):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Set-Cookie', self._cookie(sid, clear))
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path in ('/', '/index.html'):
            body = WEB.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'none'; frame-ancestors 'none'")
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not self.authorized():
            self.respond(401, {'error': 'Bearer token required'})
            return
        identity = self.identity()
        if url.path == '/api/me':
            self.respond(200, {'username': identity['username'], 'administrator': identity['kind'] == 'admin'})
        elif url.path == '/api/users':
            if identity['kind'] != 'admin':
                self.respond(403, {'error': 'Administrator token required'})
                return
            self.respond(200, {'users': accounts.list_users()})
        elif url.path == '/api/status':
            with LOCK:
                data = dict(STATE)
            data['container_stop_requested'] = STOP_EVENT.is_set()
            data['supervisor_uptime_seconds'] = int(time.monotonic()-BOOT_MONO)
            data['game_uptime_seconds'] = int(time.monotonic()-GAME_MONO) if GAME_MONO is not None and data['game_running'] else None
            with LOCK:
                data['recent_exits'] = list(HISTORY)[-10:]
            self.respond(200, data)
        elif url.path == '/api/sftp':
            self.respond(200, sftp_status())
        elif url.path == '/api/logs':
            try:
                count = min(max(int(parse_qs(url.query).get('limit', ['150'])[0]), 1), 500)
            except ValueError:
                self.respond(400, {'error': 'invalid limit'})
                return
            with LOCK:
                lines = list(RECENT)[-count:]
            self.respond(200, {'lines': lines, 'scope': 'supervisor messages only; use docker logs for game console'})
        else:
            self.respond(404, {'error': 'Not found'})

    def read_json(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise ValueError('Invalid Content-Length')
        if not 0 <= size <= 2048:
            raise ValueError('Request is too large')
        if size == 0:
            return {}
        obj = json.loads(self.rfile.read(size))
        if not isinstance(obj, dict):
            raise ValueError('Expected a JSON object')
        return obj

    def do_POST(self):
        if not self._post_allowed():
            return
        url = urlsplit(self.path).path
        try:
            data = self.read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self.respond(400, {'error': str(exc)})
            return
        if url == '/api/login':
            try:
                sid = accounts.login(data.get('username'), data.get('password'))
            except PermissionError:
                self.respond(401, {'error': 'Invalid username or password'})
                return
            self.respond_with_cookie(200, {'username': data['username'], 'administrator': False}, sid)
            return
        identity = self.identity()
        if identity is None:
            self.respond(401, {'error': 'Authentication required'})
            return
        if url == '/api/logout':
            accounts.logout(self._session_id())
            self.respond_with_cookie(200, {'ok': True}, '', clear=True)
            return
        if url == '/api/users':
            if identity['kind'] != 'admin':
                self.respond(403, {'error': 'Administrator token required'})
                return
            try:
                created = accounts.create(data.get('username'), data.get('password'), data.get('sftp_enabled', True))
                log('Administrator created panel/SFTP user ' + created['username'])
                self.respond(201, created)
            except ValueError as exc:
                self.respond(400, {'error': str(exc)})
            except RuntimeError as exc:
                log(f'ERROR user creation: {exc}')
                self.respond(500, {'error': 'User provisioning failed; inspect supervisor logs'})
            return
        if url == '/api/users/modify' or url == '/api/users/delete' or url == '/api/users/password':
            if identity['kind'] != 'admin':
                self.respond(403, {'error': 'Administrator token required'})
                return
            try:
                name = data.get('username')
                if url == '/api/users/modify':
                    result = accounts.modify(name, data.get('enabled'), data.get('sftp_enabled'))
                elif url == '/api/users/delete':
                    accounts.delete(name)
                    result = {'deleted': name}
                else:
                    accounts.change_password(name, data.get('password'))
                    result = {'password_changed': name}
                log(f'Administrator managed panel user {name} ({url.rsplit("/",1)[-1]})')
                self.respond(200, result)
            except ValueError as exc:
                self.respond(400, {'error': str(exc)})
            except RuntimeError as exc:
                log(f'ERROR panel user change: {exc}')
                self.respond(500, {'error': 'Account update failed; inspect supervisor logs'})
            return
        if url == '/api/me/password':
            if identity['kind'] != 'user':
                self.respond(403, {'error': 'Panel user login required'})
                return
            if not accounts.verify(identity['username'], data.get('current_password')):
                self.respond(403, {'error': 'Current password incorrect'})
                return
            try:
                accounts.change_password(identity['username'], data.get('new_password'))
                log('Panel user changed their password: ' + identity['username'])
                self.respond_with_cookie(200, {'password_changed': True, 'login_required': True}, '', clear=True)
            except ValueError as exc:
                self.respond(400, {'error': str(exc)})
            except RuntimeError as exc:
                log(f'ERROR panel password update: {exc}')
                self.respond(500, {'error': 'Password update failed; inspect supervisor logs'})
            return
        if STOP_EVENT.is_set():
            self.respond(409, {'error': 'Container shutdown in progress'})
            return
        action = url.removeprefix('/api/actions/') if url.startswith('/api/actions/') else ''
        try:
            if action in ('start', 'stop', 'restart', 'update'):
                payload = None
            elif url == '/api/sftp/password':
                if identity['kind'] != 'admin':
                    self.respond(403, {'error': 'Administrator token required to rotate the legacy account'})
                    return
                action = 'sftp_password'
                payload = data.get('password')
                if not isinstance(payload, str) or not 16 <= len(payload) <= 128 or any(c in payload for c in ('\n', '\r', '\x00')):
                    raise ValueError('Password must be 16..128 characters without newline/NUL')
            else:
                self.respond(404, {'error': 'Unknown action'})
                return
        except ValueError as exc:
            self.respond(400, {'error': str(exc)})
            return
        item = (action, payload) if payload is not None else action
        try:
            PENDING.put_nowait(item)
        except queue.Full:
            self.respond(409, {'error': 'Another action is pending'})
            return
        log(f'Web/API requested action: {action} by {identity["username"]}')
        self.respond(202, {'accepted': action, 'message': 'Queued; monitor /api/status'})


def serve_manager():
    if len(TOKEN) < 24 or TOKEN.startswith('CHANGE_'):
        raise ValueError('MANAGER_TOKEN must be a unique secret of at least 24 characters')
    port = env_int('WEB_PORT', 8080, 1024, 65535)
    server = ThreadingHTTPServer(('0.0.0.0', port), ManagerHandler)
    threading.Thread(target=server.serve_forever, daemon=True, name='manager-http').start()
    log(f'Management API/Web UI listening in container on {port}; require Bearer token')
    return server


def read_console(master, timeout=0.25):
    try:
        readable, _, _ = select.select([master], [], [], timeout)
        if readable:
            data = os.read(master, 65536)
            if data:
                os.write(sys.stdout.fileno(), data)
                # Mirror the game console to persistent appdata for logs after Compose Down.
                try:
                    with FILE_LOCK, GAME_LOG_FILE.open('ab') as game_log:
                        game_log.write(data)
                except OSError as exc:
                    print(f'[scum-init] WARNING game console log write failed: {exc}', flush=True)
    except (OSError, BrokenPipeError):
        pass


def launch(port, players):
    log('Launching Wine + Xvfb; game readiness is not yet independently verified')
    master, slave = pty.openpty()

    def controlling_tty():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

    args = ['xvfb-run', '-a', 'wine', str(EXE), '-log',
            f'-port={port}', f'-MaxPlayers={players}']
    try:
        game = run_as_scum(args, stdin=slave, stdout=slave, stderr=slave,
                           cwd=str(GAME), preexec_fn=controlling_tty)
    finally:
        os.close(slave)
    global GAME_MONO
    GAME_MONO = time.monotonic()
    set_state(phase='running', game_pid=game.pid, game_running=True,
              started_at=datetime.now(timezone.utc).isoformat(), last_error=None)
    log(f'Launched game wrapper PID {game.pid}; game UDP {port}/{port+1}, connection TCP {port+2}')
    return game, master


def stop_game(game, master, timeout):
    """Ask Wine console to stop. Never assert that the world was saved."""
    if game.poll() is not None:
        return True
    set_state(phase='stopping')
    log('Sending PTY Ctrl+C; character persistence field-tested, complete save integrity unverified')
    try:
        os.write(master, b'\x03')
    except OSError as exc:
        log(f'Ctrl+C could not be written: {exc}')
        set_state(last_error='Ctrl+C signalling failed')
        return False
    deadline = time.monotonic() + timeout
    while game.poll() is None and time.monotonic() < deadline:
        read_console(master, 0.25)
    if game.poll() is None:
        log('ERROR game did not exit within grace period; refusing to claim safe stop')
        set_state(phase='stop_failed', last_error='Game did not exit before timeout')
        return False
    log(f'Game wrapper exited with code {game.returncode}; character persistence must be verified after restart')
    record_exit('requested_stop', game.returncode)
    set_state(phase='stopped', game_running=False, game_pid=None)
    return True


def main():
    port = env_int('GAME_PORT', 7777, 1024, 65533)
    players = env_int('MAX_PLAYERS', 10, 1, 64)
    timeout = env_int('SHUTDOWN_TIMEOUT', 120, 30, 600)
    vmmap = Path('/proc/sys/vm/max_map_count')
    if vmmap.exists():
        maps = int(vmmap.read_text())
        if maps < 1048576:
            log(f'WARNING vm.max_map_count={maps}; recommended >= 1048576')
    load_history()
    sshd = subprocess.Popen(['/usr/sbin/sshd', '-D', '-e'])
    manager = serve_manager()
    game = None
    master = None
    desired_running = True
    pending_action = None
    try:
        install()
        if STOP_EVENT.is_set():
            return 0
        while not STOP_EVENT.is_set():
            if desired_running and game is None:
                game, master = launch(port, players)
            try:
                pending_action = PENDING.get_nowait()
            except queue.Empty:
                pending_action = None
            if pending_action:
                action, payload = pending_action if isinstance(pending_action, tuple) else (pending_action, None)
                set_state(last_action=action, last_error=None)
                if action == 'start':
                    desired_running = True
                elif action in ('stop', 'restart', 'update'):
                    if game is not None:
                        if not stop_game(game, master, timeout):
                            # No automatic force kill or restart: operator must intervene.
                            desired_running = False
                            pending_action = None
                            continue
                        os.close(master)
                        game, master = None, None
                    desired_running = action != 'stop'
                    if action == 'update':
                        try:
                            steamcmd_update()
                        except Exception as exc:
                            log(f'ERROR manual SteamCMD update failed: {exc}')
                            set_state(phase='error', last_error=str(exc))
                            desired_running = False
                elif action == 'sftp_password':
                    try:
                        rotate_sftp_password(payload)
                    except Exception as exc:
                        log(f'ERROR SFTP password rotation failed: {exc}')
                        set_state(last_error='SFTP password rotation failed; inspect supervisor log')
            if game is not None:
                read_console(master)
                if game.poll() is not None:
                    record_exit('unexpected_exit', game.returncode)
                    log(f'Game process exited with code {game.returncode}; manual start needed')
                    set_state(phase='crashed', game_pid=None, game_running=False,
                              last_error=f'Game process exited with code {game.returncode}')
                    os.close(master)
                    game, master = None, None
                    desired_running = False
            else:
                if not desired_running and pending_action != 'update':
                    with LOCK:
                        if STATE['phase'] not in ('crashed', 'error', 'stop_failed'):
                            STATE['phase'] = 'stopped'
                time.sleep(0.25)
        if game is not None and game.poll() is None:
            return 0 if stop_game(game, master, timeout) else 1
        return 0
    finally:
        manager.shutdown()
        if master is not None:
            os.close(master)
        sshd.terminate()
        try:
            sshd.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sshd.kill()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, InterruptedError) as exc:
        log(f'ERROR: {exc}')
        sys.exit(1)
