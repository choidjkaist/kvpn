import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kvpn_runtime as r

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.m = r.Manager(Path(self.temp.name) / 'runtime')
        self.state = {'pid': 98765, 'process_started': 'Mon Oct  5 11:00:00 2026',
                      'binary': '/opt/homebrew/bin/openconnect',
                      'expected_command': '/opt/homebrew/bin/openconnect --protocol=nc --background kvpn.kaist.ac.kr',
                      'authenticated_at': time.time() - 60, 'estimate_hours': 10, 'reconnect_timeout': 300}
        self.proc = {'pid': 98765, 'started': self.state['process_started'], 'uid': 0,
                     'command': self.state['expected_command']}

    def test_lock_cross_process(self):
        code = "import kvpn_runtime as r,sys; m=r.Manager(sys.argv[1]);\nwith m.lock(): pass"
        with self.m.lock():
            p = subprocess.run([sys.executable, '-c', code, str(self.m.directory)],
                               cwd=Path(r.__file__).parent, capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('operation is in progress', p.stderr)
        with self.m.lock(): pass

    def test_private_state_and_no_symlink(self):
        self.m.save(self.state)
        self.assertEqual(self.m.state_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.m.directory.stat().st_mode & 0o777, 0o700)
        self.m.state_path.unlink()
        victim = Path(self.temp.name) / 'victim'
        victim.write_text('unchanged')
        self.m.state_path.symlink_to(victim)
        with self.assertRaises(OSError): self.m.load()
        self.assertEqual(victim.read_text(), 'unchanged')

    def test_process_identity_reuse_and_wrong_uid(self):
        with patch.object(r, 'process', return_value=self.proc):
            self.assertIsNotNone(self.m.owned_process(self.state))
        for altered in ({'started': 'other'}, {'uid': 501}, {'command': '/bin/sleep 100'}):
            with patch.object(r, 'process', return_value=dict(self.proc, **altered)):
                self.assertIsNone(self.m.owned_process(self.state))

    def test_disconnect_never_signals_unmanaged(self):
        with patch.object(r, 'openconnect_processes', return_value=[98765]), patch.object(r.subprocess, 'run') as run:
            with self.assertRaisesRegex(r.RuntimeError, 'not managed'): self.m.disconnect()
            run.assert_not_called()

    def test_duplicate_guard(self):
        with patch.object(r, 'openconnect_processes', return_value=[123]):
            with self.assertRaisesRegex(r.RuntimeError, 'No login or OTP'): self.m.assert_idle()

    def test_stop_revalidates_after_sudo(self):
        with patch.object(self.m, 'load', return_value=self.state), patch.object(self.m, 'owned_process', side_effect=[self.proc, None]), patch.object(r.subprocess, 'run') as run:
            with self.assertRaisesRegex(r.RuntimeError, 'identity changed'): self.m.disconnect()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0], ['sudo','-v'])

    def test_shutdown_timeout_retains_state_and_no_kill(self):
        with patch.object(self.m, 'load', return_value=self.state), patch.object(self.m, 'owned_process', return_value=self.proc), patch.object(r.subprocess, 'run') as run, patch.object(r.time, 'sleep'), patch.object(self.m, 'save') as save:
            run.return_value.returncode = 0
            with self.assertRaisesRegex(r.RuntimeError, 'pending'): self.m.disconnect()
            self.assertEqual(run.call_args.args[0], ['sudo','-n','/bin/kill','-TERM','98765'])
            save.assert_not_called()

    def test_unknown_unmanaged_time(self):
        with patch.object(r, 'openconnect_processes', return_value=[123]):
            s = self.m.status()
        self.assertEqual(s['status'], 'unmanaged connection')
        self.assertIsNone(s['server_expiry'])
        self.assertNotIn('estimated_expiry', s)

    def test_estimate_never_promoted_to_server_time(self):
        with patch.object(self.m, 'load', return_value=self.state), patch.object(self.m, 'owned_process', return_value=self.proc), patch.object(r, 'openconnect_processes', return_value=[98765]):
            s = self.m.status()
        self.assertAlmostEqual(s['estimated_remaining_seconds'], 35940, delta=2)
        self.assertIsNone(s['server_remaining_seconds'])

    def test_log_phase_expiry(self):
        s, ip = r.log_phase('Configured as 172.25.1.2, SSL\nESP session established\nServer terminated connection (session expired)')
        self.assertEqual(s, 'authentication expired')
        self.assertEqual(ip, '172.25.1.2')

    def test_redaction_stream_at_rest(self):
        source = 'url https://kvpn.test/cb?code=SECRET&x=TOKEN DSID=COOKIE password=PASSWORD\n'
        p = subprocess.run([sys.executable, str(Path(r.__file__)), '--sanitize'], input=source, text=True, capture_output=True)
        for secret in ('SECRET','TOKEN','COOKIE','PASSWORD'): self.assertNotIn(secret, p.stdout)
        self.assertIn('[redacted]', p.stdout)

    def test_pending_start_recovery(self):
        state = dict(self.state, pid=None, process_started=None, authenticated_at=time.mktime(time.strptime(self.proc['started'], '%a %b %d %H:%M:%S %Y')))
        with patch.object(self.m, 'logs', return_value='Continuing in background; pid 98765'), patch.object(r, 'process', return_value=self.proc):
            self.assertIsNotNone(self.m.owned_process(state))
        state = dict(self.state, pid=None, process_started=None, authenticated_at=time.time()+3600)
        with patch.object(self.m, 'logs', return_value='Continuing in background; pid 98765'), patch.object(r, 'process', return_value=self.proc):
            self.assertIsNone(self.m.owned_process(state))


class ExtraTests(unittest.TestCase):
    setUp = RuntimeTests.setUp
    def test_relative_url_and_bearer_redacted(self):
        for value in ('/vpn/client?code=SECRET_CODE&token=SECRET_TOKEN', 'Authorization: Bearer SECRET_BEARER', 'Cookie: DSID=SECRET_COOKIE; token=OTHER_SECRET'):
            out = r.redact(value)
            self.assertNotIn('SECRET', out)

    def test_invalid_state_schema(self):
        for value in ([], 'bad', 123, {'pid': '123'}):
            self.m.state_path.write_text(json.dumps(value))
            with self.assertRaisesRegex(r.RuntimeError, 'Invalid state'): self.m.load()

    def test_interrupt_anywhere_after_spawn_reports_pending(self):
        def interrupted(*args, **kwargs):
            self.m._launch_started = True
            raise KeyboardInterrupt
        with patch.object(self.m, '_launch', side_effect=interrupted):
            with self.assertRaisesRegex(r.RuntimeError, 'detached tunnel'):
                self.m.launch('SYNTHETIC')

    def test_disappearing_startup_pid_does_not_abort_stop(self):
        vanished = [self.proc, self.proc, self.proc] + [None] * 5
        with patch.object(self.m, 'load', return_value=self.state), patch.object(self.m, 'owned_process', side_effect=vanished), patch.object(r, 'process', return_value=None), patch.object(r.subprocess, 'run') as run, patch.object(r.time, 'sleep'):
            run.return_value.returncode = 1
            run.return_value.stderr = 'No such process'
            self.m.disconnect()
            self.assertIn('disconnected_at', self.m.load())

    def test_sudo_failure_precedes_session_state(self):
        with patch.object(self.m, 'assert_idle'), patch.object(r.shutil, 'which', return_value='/opt/homebrew/bin/openconnect'), patch.object(r.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['sudo','-v'])):
            with self.assertRaises(subprocess.CalledProcessError): self.m.launch('SYNTHETIC')
        self.assertFalse(self.m.state_path.exists())

    def test_no_marker_never_adopts_lookalike(self):
        state = dict(self.state, pid=None, process_started=None, startup_pending=True, launch_started_at=time.time()-86400)
        with patch.object(self.m, 'logs', return_value=''), patch.object(r, 'openconnect_processes', return_value=[98765]), patch.object(r,'process',return_value=self.proc):
            self.assertIsNone(self.m.owned_process(state))
        state = dict(self.state, disconnected_at=time.time())
        with patch.object(r,'process',return_value=self.proc):
            self.assertIsNone(self.m.owned_process(state))

    def test_native_background_integration(self):
        # Fake only the privileged/network boundary; exercise real fork, pipes,
        # session detachment, sanitizer, state capture and graceful stop.
        base = Path(self.temp.name)
        fake = base / 'openconnect'
        fake.write_text('''#!/usr/bin/env python3
import os,sys,time,signal
cookie=sys.stdin.readline()
if not cookie.startswith('DSID='): sys.exit(4)
pid=os.fork()
if pid:
 print('Continuing in background; pid %d' % pid,flush=True)
 sys.exit(0)
signal.signal(signal.SIGTERM,lambda *_: sys.exit(0))
print('Configured as 172.25.1.2, SSL connected',flush=True)
print('ESP session established with server',flush=True)
print('Authorization: Bearer SYNTHETIC_SECRET',flush=True)
time.sleep(20)
''')
        fake.chmod(0o700)
        sudo = base / 'sudo'
        sudo.write_text('''#!/usr/bin/env python3
import os,sys
args=sys.argv[1:]
if args==['-v']: sys.exit(0)
if args and args[0]=='-n': args=args[1:]
os.execvp(args[0],args)
''')
        sudo.chmod(0o700)
        original_process = r.process
        def identity(pid):
            p = original_process(pid)
            if p and str(fake) in p['command']:
                p['command'] = p['command'][p['command'].index(str(fake)):]
                p['uid'] = 0  # simulated privilege boundary only
            return p
        def active():
            state = self.m.load()
            pid = state.get('pid')
            return [pid] if pid and identity(pid) else []
        pid = None
        with patch.dict(os.environ, {'PATH':str(base)+os.pathsep+os.environ['PATH']}), patch.object(r.shutil,'which',return_value=str(fake)), patch.object(r,'process',side_effect=identity), patch.object(r,'openconnect_processes',side_effect=active):
            try:
                self.assertEqual(self.m.launch('SYNTHETIC_COOKIE'),0)
                state = self.m.load()
                pid = state['pid']
                self.assertNotEqual(os.getsid(pid), os.getsid(0))
                self.assertIsNotNone(identity(pid))
                time.sleep(.1)
                self.assertNotIn('SYNTHETIC_SECRET', self.m.log_path.read_text())
                self.assertNotIn('SYNTHETIC_COOKIE', self.m.log_path.read_text())
                with self.assertRaises(r.RuntimeError): self.m.assert_idle()
                self.m.disconnect()
                self.assertIsNone(identity(pid))
            finally:
                if pid and original_process(pid):
                    os.kill(pid, 15)

if __name__ == '__main__': unittest.main()
