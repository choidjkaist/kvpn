"""Local lifecycle support. No passwords, OTPs or session cookies are persisted."""
from kvpn_ui import row, note, commands
import contextlib
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time

VERSION = '0.4.0rc2'

class RuntimeError(Exception):
    pass


def redact(text):
    # Drop complete credential header values, including multi-word Bearer tokens.
    text = re.sub(r'(?im)(\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*:)\s*[^\r\n]+', r'\1 [redacted]', text)
    # Both absolute and relative redirect URLs may carry OAuth codes.
    text = re.sub(r'([?&][A-Za-z0-9_.%~-]+=)[^\s&#\"\']*', r'\1[redacted]', text)
    text = re.sub(r'(?i)((?:DSID|password(?:#2)?|j_password|otp|token|cookie)\s*[:=]\s*)[^\s,;]+', r'\1[redacted]', text)
    return text


def private_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    s = path.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid():
        raise RuntimeError('Unsafe runtime directory (owner or symlink).')
    path.chmod(0o700)
    return path


def secure_open(path, flags):
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
    s = os.fstat(fd)
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1:
        os.close(fd)
        raise RuntimeError('Unsafe runtime file.')
    os.fchmod(fd, 0o600)
    return fd


def process(pid):
    if not isinstance(pid, int) or pid <= 1:
        return None
    r = subprocess.run(['/bin/ps', '-ww', '-p', str(pid), '-o', 'lstart=', '-o', 'uid=', '-o', 'command='], capture_output=True, text=True, env=dict(os.environ, LC_ALL='C'))
    line = r.stdout.strip()
    if r.returncode or len(line) < 25:
        return None
    fields = line[24:].strip().split(None, 1)
    if len(fields) != 2 or not fields[0].isdigit():
        return None
    return {'pid': pid, 'started': line[:24], 'uid': int(fields[0]), 'command': fields[1]}


def openconnect_processes():
    r = subprocess.run(['/bin/ps', '-ww', '-axo', 'pid=,comm='], capture_output=True, text=True, check=True, env=dict(os.environ, LC_ALL='C'))
    result = []
    for line in r.stdout.splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) == 2 and Path(fields[1]).name == 'openconnect':
            result.append(int(fields[0]))
    return result


def log_phase(text):
    phase = 'starting'
    ip = None
    for line in text.splitlines():
        lower = line.lower()
        match = re.search(r'Configured as ([0-9.]+)', line)
        if match:
            ip = match[1]
            phase = 'tunnel configured'
        if 'esp session established' in lower:
            phase = 'connected'
        if 'reconnect' in lower and any(x in lower for x in ('attempt', 'failed', 'sleep', 'retry')):
            phase = 'reconnecting'
        if any(x in lower for x in ('session expired', 'cookie was rejected', 'cookie is no longer valid')):
            phase = 'authentication expired'
        elif any(x in lower for x in ('user cancelled', 'user canceled')):
            phase = 'disconnected'
    return phase, ip


class Manager:
    def __init__(self, directory=None):
        self.directory = private_dir(directory or Path.home() / 'Library/Application Support/kvpn')
        self.state_path = self.directory / 'state.json'
        self.log_path = self.directory / 'connection.log'

    def session_replacement_allowed(self):
        """Explicit local owner policy; absence never authorizes takeover."""
        try:
            fd = secure_open(self.directory / 'preferences.json', os.O_RDONLY)
            with os.fdopen(fd) as f:
                value = json.load(f)
            return isinstance(value, dict) and value.get('replace_existing_session') is True
        except FileNotFoundError:
            return False
        except (ValueError, TypeError):
            raise RuntimeError('Invalid KVPN preferences; session replacement not authorized.') from None

    def set_session_replacement(self, allowed):
        with self.lock():
            path = self.directory / 'preferences.json'
            try:
                fd = secure_open(path, os.O_RDONLY)
                with os.fdopen(fd) as f:
                    value = json.load(f)
                if not isinstance(value, dict):
                    raise ValueError('not an object')
            except FileNotFoundError:
                value = {}
            except (ValueError, TypeError):
                raise RuntimeError('Invalid preferences; no settings changed.') from None
            value['replace_existing_session'] = bool(allowed)
            temp = self.directory / 'preferences.new'
            fd = secure_open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
            with os.fdopen(fd, 'w') as f:
                json.dump(value, f, indent=2)
                f.write('\n')
            os.replace(temp, path)

    @contextlib.contextmanager
    def lock(self):
        fd = secure_open(self.directory / 'operation.lock', os.O_RDWR | os.O_CREAT)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Another kvpn operation is in progress.') from None
            yield
        finally:
            os.close(fd)

    def load(self):
        try:
            fd = secure_open(self.state_path, os.O_RDONLY)
            with os.fdopen(fd) as f:
                value = json.load(f)
            if not isinstance(value, dict):
                raise ValueError('state must be an object')
            if value:
                if not isinstance(value.get('binary'), str) or not isinstance(value.get('expected_command'), str):
                    raise ValueError('missing process command')
                if value.get('pid') is not None and (type(value['pid']) is not int or value['pid'] <= 1):
                    raise ValueError('invalid PID')
                if not isinstance(value.get('authenticated_at'), (int, float)):
                    raise ValueError('invalid authentication time')
                if type(value.get('estimate_hours')) is not int or not 1 <= value['estimate_hours'] <= 24:
                    raise ValueError('invalid estimate')
            return value
        except FileNotFoundError:
            return {}
        except (ValueError, TypeError):
            raise RuntimeError('Invalid state file; refusing to control a process.') from None

    def save(self, value):
        temp = self.directory / 'state.new'
        fd = secure_open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, indent=2)
            f.write('\n')
        os.replace(temp, self.state_path)

    def owned_process(self, state):
        if state.get('disconnected_at'):
            return None
        if state and (state.get('pid') is None or state.get('startup_pending')):
            matches = re.findall(r'Continuing in background; pid (\d+)', self.logs())
            candidate = process(int(matches[-1])) if matches else None
            if candidate:
                state['startup_pending'] = False
            if not candidate:
                initial = re.findall(r'KVPN startup pid (\d+)', self.logs())
                candidate = process(int(initial[-1])) if initial else None
            if candidate:
                try:
                    started = time.mktime(time.strptime(candidate['started'], '%a %b %d %H:%M:%S %Y'))
                except ValueError:
                    return None
                launch_time = state.get('launch_started_at', state.get('authenticated_at', float('inf')))
                if launch_time - 2 <= started <= launch_time + 120:
                    state.update(pid=candidate['pid'], process_started=candidate['started'])
        p = process(state.get('pid'))
        if not p or p['started'] != state.get('process_started'):
            return None
        command = p['command']
        binary = state.get('binary', '')
        if not binary or not command.startswith(binary + ' '):
            return None
        if p['uid'] != 0 or command != state.get('expected_command'):
            return None
        return p

    def assert_idle(self):
        if openconnect_processes():
            raise RuntimeError('An OpenConnect tunnel is already running. No login or OTP was requested. Use kvpn status; stop the existing connection before connecting again.')

    def logs(self):
        try:
            fd = secure_open(self.log_path, os.O_RDONLY)
            with os.fdopen(fd, 'rb') as f:
                f.seek(max(0, os.fstat(f.fileno()).st_size - 100000))
                return redact(f.read().decode('utf-8', 'replace'))
        except FileNotFoundError:
            return ''

    def status(self):
        state = self.load()
        p = self.owned_process(state)
        others = [pid for pid in openconnect_processes() if not p or pid != p['pid']]
        phase, ip = log_phase(self.logs())
        result = {'version': VERSION, 'managed': bool(p), 'pid': p['pid'] if p else None,
                  'unmanaged_pids': others, 'status': phase if p else ('unmanaged connection' if others else 'disconnected'),
                  'server_expiry': None, 'server_remaining_seconds': None}
        if state and not p and not others and phase == 'authentication expired':
            result['status'] = phase
        if p:
            if ip:
                r = subprocess.run(['/sbin/ifconfig'], capture_output=True, text=True, env=dict(os.environ, LC_ALL='C'))
                result['interface_present'] = bool(re.search(r'\binet ' + re.escape(ip) + r'\b', r.stdout))
                result['vpn_ip'] = ip
                if not result['interface_present'] and phase in ('connected', 'tunnel configured'):
                    result['status'] = 'process running; tunnel not confirmed'
            auth = state.get('authenticated_at')
            if auth:
                result['authenticated_at'] = auth
                result['elapsed_seconds'] = max(0, int(time.time() - auth))
                result['estimated_expiry'] = auth + state.get('estimate_hours', 10) * 3600
                result['estimated_remaining_seconds'] = max(0, int(result['estimated_expiry'] - time.time()))
            result['reconnect_timeout_seconds'] = state.get('reconnect_timeout')
            try:
                fd = secure_open(self.directory / 'server-limits.json', os.O_RDONLY)
                with os.fdopen(fd) as f: limits = json.load(f)
                maximum = limits.get('server_max_session_seconds')
                if limits.get('authenticated_at') == auth and type(maximum) is int and 0 < maximum <= 366*86400:
                    result['server_max_session_seconds'] = maximum
                    result['server_limit_sampled_at'] = limits.get('sampled_at')
                    result['estimated_expiry'] = auth + maximum
                    result['estimated_remaining_seconds'] = max(0, int(auth + maximum - time.time()))
            except (OSError, ValueError, AttributeError):
                pass
        return result

    def launch(self, dsid, **options):
        self._launch_started = False
        try:
            return self._launch(dsid, **options)
        except KeyboardInterrupt:
            if self._launch_started:
                raise RuntimeError('Startup interrupted; a detached tunnel may still be starting. Use kvpn status and kvpn disconnect; no forced kill was sent.') from None
            raise
        except subprocess.SubprocessError as error:
            if self._launch_started:
                raise RuntimeError('Startup did not complete cleanly; state retained. Check kvpn status and kvpn log before retrying.') from None
            raise

    def _launch(self, dsid, *, authenticated_at=None, foreground=False, reconnect_timeout=300, estimate_hours=10, unattended=False, supervised=False):
        self.assert_idle()
        binary = shutil.which('openconnect')
        if not binary:
            raise RuntimeError('OpenConnect is not installed.')
        subprocess.run(['sudo', '-n', '-v'] if unattended else ['sudo', '-v'], check=True)
        # Refresh privilege on the original tty after any OTP/keychain delay.
        # Cookie is ephemeral stdin, never argv, state, or a log message.
        base = [binary, '--protocol=nc', '--cookie-on-stdin', '--non-inter',
                '--reconnect-timeout=' + str(reconnect_timeout)]
        if foreground:
            proc = subprocess.Popen(['sudo', '-n'] + base + ['kvpn.kaist.ac.kr'], stdin=subprocess.PIPE)
            try:
                proc.communicate(('DSID=' + dsid + '\n').encode())
            except KeyboardInterrupt:
                # SIGINT reaches the foreground process group, including sudo/OpenConnect.
                proc.wait()
            return proc.returncode
        fd = secure_open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        command = base + ['--background', '--timestamp', 'kvpn.kaist.ac.kr']
        state = {'expected_command': ' '.join(command), 'binary': binary, 'authenticated_at': authenticated_at or time.time(), 'launch_started_at': time.time(), 'estimate_hours': estimate_hours,
                 'reconnect_timeout': reconnect_timeout, 'startup_pending': True, 'pid': None, 'process_started': None}
        self.save(state)
        with os.fdopen(fd, 'wb') as log:
            # sudo stays on the original tty for its cached authorization. A fixed,
            # isolated Python wrapper detaches only OpenConnect (no sudoers changes).
            detach = 'import subprocess,sys,signal; signal.signal(signal.SIGINT,signal.SIG_IGN); signal.signal(signal.SIGHUP,signal.SIG_IGN); p=subprocess.Popen(sys.argv[1:],start_new_session=True); print("KVPN startup pid",p.pid,flush=True); raise SystemExit(p.wait())'
            proc = subprocess.Popen(['sudo', '-n', sys.executable, '-I', '-c', detach] + command,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=dict(os.environ, LC_ALL='C'))
            self._launch_started = True
            # A detached unprivileged filter owns the pipe; no raw output is stored.
            sanitizer = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '--sanitize-daemon'],
                                         stdin=proc.stdout, stdout=log, stderr=subprocess.DEVNULL,
                                         start_new_session=True)
            sanitizer.wait(timeout=5)
            if sanitizer.returncode:
                raise RuntimeError('Log sanitizer could not start. Inspect kvpn status before retrying.')
            proc.stdout.close()
            proc.stdout = None
            try:
                proc.communicate(('DSID=' + dsid + '\n').encode(), timeout=90)
            except KeyboardInterrupt:
                raise RuntimeError('Startup interrupted; a detached tunnel may still be starting. Use kvpn status and kvpn disconnect; no forced kill was sent.') from None
            except subprocess.TimeoutExpired:
                raise RuntimeError('Startup is still pending after 90 seconds. State retained; inspect kvpn status/logs before retrying.') from None
        if proc.returncode:
            raise RuntimeError('OpenConnect failed to start. Run kvpn log for redacted diagnostics.')
        for _ in range(20):
            try:
                matches = re.findall(r'Continuing in background; pid (\d+)', self.logs())
                pid = int(matches[-1]) if matches else None
            except (FileNotFoundError, ValueError):
                pid = None
            p = process(pid)
            if p:
                state.update(pid=pid, process_started=p['started'], startup_pending=False)
                if self.owned_process(state):
                    self.save(state)
                    row('VPN', 'Connected', '32')
                    note('Keep this terminal open for automatic recovery.' if supervised else 'Connected in background. You may close this terminal.')
                    commands()
                    return 0
            time.sleep(.1)
        raise RuntimeError('Startup was not confirmed. Run kvpn status and kvpn log; do not launch another tunnel.')

    def disconnect(self):
        state = self.load()
        p = self.owned_process(state)
        if not p:
            if openconnect_processes():
                raise RuntimeError('The running connection is not managed by this version. Stop it with Ctrl+C in its original terminal.')
            print('No managed VPN is running.')
            return
        subprocess.run(['sudo', '-v'], check=True)
        # Revalidate after user interaction; never signal a stale/reused PID.
        p = self.owned_process(state)
        if not p:
            raise RuntimeError('Process identity changed; no signal sent.')
        signaled = set()
        absent = 0
        for _ in range(100):
            current = self.owned_process(state)
            if current:
                absent = 0
                if current['pid'] not in signaled:
                    result = subprocess.run(['sudo', '-n', '/bin/kill', '-TERM', str(current['pid'])], capture_output=True, text=True)
                    if result.returncode:
                        identity = process(current['pid'])
                        if identity and identity['started'] == current['started']:
                            raise RuntimeError('Could not terminate the VPN: ' + redact(result.stderr.strip()))
                        # Original startup process vanished; follow its daemon transition.
                    else:
                        signaled.add(current['pid'])
            else:
                absent += 1
                # Allow a pending startup-to-daemon transition to announce itself.
                if absent >= 5:
                    state['disconnected_at'] = time.time()
                    state['startup_pending'] = False
                    self.save(state)
                    print('VPN process stopped normally. OpenConnect handles route/DNS cleanup.')
                    return
            time.sleep(.1)
        raise RuntimeError('Shutdown is still pending. No forced kill was sent; check kvpn status and kvpn log.')


def duration(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds // 3600}h {(seconds % 3600) // 60}m'


def display_status(value):
    from kvpn_ui import title, row, note
    title()
    status = value['status']
    row('VPN', status.capitalize(), '32' if status == 'connected' else '33')
    auto = value.get('automatic_reconnect', {})
    row('Auto recovery', auto.get('phase', 'On') if auto.get('running') else 'Off')
    if auto.get('stop_reason'):
        row('Last stop', auto['stop_reason'])
    note('Process and interface evidence only; destination reachability is not tested.')
    if value.get('unmanaged_pids'):
        row('Other VPN PIDs', ', '.join(map(str, value['unmanaged_pids'])))
    if value.get('authenticated_at'):
        fmt = lambda t: datetime.datetime.fromtimestamp(t).astimezone().strftime('%b %d  %H:%M:%S %Z')
        row('Signed in', fmt(value['authenticated_at']))
        row('Connected for', duration(value['elapsed_seconds']))
        row('Time left', duration(value['estimated_remaining_seconds']) + ' (estimated)')
        row('Expires around', fmt(value['estimated_expiry']))
        print()
        note('Time left is estimated; server expiry is not available.')
    print()
    commands()


if __name__ == '__main__' and sys.argv[1:] in (['--sanitize'], ['--sanitize-daemon']):
    if sys.argv[1] == '--sanitize-daemon':
        if os.fork():
            sys.exit(0)
        os.setsid()
        if os.fork():
            os._exit(0)
    for line in sys.stdin:
        print(redact(line), end='', flush=True)
