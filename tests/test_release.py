import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import install
import build_release
from release_manifest import RELEASE_FILES
from kvpn_runtime import Manager
import kvpn_auto

loader = importlib.machinery.SourceFileLoader('release_cli', str(ROOT / 'kvpn'))
spec = importlib.util.spec_from_loader(loader.name, loader)
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)


class ReleaseTests(unittest.TestCase):
    def test_auto_stop_retains_connection_and_never_reads_credentials(self):
        for command in (['auto', 'stop'], ['auto-stop']):
            with patch.object(cli, 'Manager') as manager, patch.object(kvpn_auto, 'request_stop') as stop, patch.object(cli, 'load_credentials') as credentials, patch.object(cli, 'SMSReader') as sms:
                cli.main(command)
                stop.assert_called_once_with(manager.return_value)
                manager.return_value.disconnect.assert_not_called()
                credentials.assert_not_called()
                sms.assert_not_called()

    def test_auto_status_json_and_legacy_aliases(self):
        for command in (['auto', 'status', '--json'], ['status', '--json']):
            with patch.object(cli, 'Manager') as manager, patch.object(kvpn_auto, 'auto_status', return_value={'running': False}), contextlib.redirect_stdout(io.StringIO()) as output:
                manager.return_value.status.return_value = {'status': 'disconnected'}
                cli.main(command)
                self.assertEqual(json.loads(output.getvalue())['status'], 'disconnected')
        for command in ('doctor', 'check'):
            with patch.object(cli, 'Manager'), patch('kvpn_check.check', return_value=[]), contextlib.redirect_stdout(io.StringIO()) as output:
                cli.main([command, '--json'])
                self.assertEqual(json.loads(output.getvalue()), [])

    def test_wrong_subcommands_do_not_touch_state(self):
        for args in (['connect', 'stop'], ['auto', 'stpo'], ['connect', '--session-replacement', 'allow'], ['auto', '--json']):
            with patch.object(cli, 'Manager') as manager, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    cli.main(args)
                self.assertEqual(result.exception.code, 2)
                manager.assert_not_called()

    def test_nonmac_sms_rejected_before_state_or_credentials(self):
        for args in ([], ['auto'], ['connect', '--sms-auto'], ['sms-check']):
            with patch.object(cli.sys, 'platform', 'linux'), patch.object(cli, 'Manager') as manager, patch.object(cli, 'load_credentials') as credentials:
                with self.assertRaisesRegex(cli.KvpnError, 'requires macOS'):
                    cli.main(args)
                manager.assert_not_called()
                credentials.assert_not_called()

    def test_setup_does_not_authenticate(self):
        with patch.object(cli, 'Manager'), patch('kvpn_setup.check', return_value=[]), patch.object(cli, 'load_credentials') as credentials, patch.object(cli, 'authenticate_and_connect') as auth, contextlib.redirect_stdout(io.StringIO()) as output:
            cli.main(['setup'])
            auth.assert_not_called()
            credentials.assert_not_called()
            self.assertIn('No login', output.getvalue())

    def test_policy_preserves_other_preferences_and_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = Manager(Path(tmp) / 'state')
            self.assertFalse(manager.session_replacement_allowed())
            p = manager.directory / 'preferences.json'
            p.write_text(json.dumps({'other': 'retained'}))
            manager.set_session_replacement(True)
            self.assertTrue(manager.session_replacement_allowed())
            manager.set_session_replacement(False)
            self.assertFalse(manager.session_replacement_allowed())
            self.assertEqual(json.loads(p.read_text())['other'], 'retained')
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            p.write_text('[]')
            with self.assertRaises(Exception):
                manager.set_session_replacement(True)
            self.assertEqual(p.read_text(), '[]')

    def test_archive_reproducible_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            archive = build_release.build(ROOT, output)
            first = archive.read_bytes()
            self.assertEqual(build_release.build(ROOT, output).read_bytes(), first)
            with tarfile.open(archive) as tar:
                names = tar.getnames()
                self.assertEqual(len(names), len(RELEASE_FILES))
                self.assertEqual({n.split('/', 1)[1] for n in names}, set(RELEASE_FILES))
                self.assertTrue(all(m.isfile() and not m.issym() for m in tar))
                tar.extractall(output / 'extract')  # own generated allowlisted archive
            source = output / 'extract' / names[0].split('/')[0]
            link = install.install(source, output / 'releases', output / 'bin')
            version = subprocess.check_output([str(link), '--version'], text=True).strip()
            self.assertEqual(version, '0.4.0rc2')
            help_text = subprocess.check_output([str(link), 'help'], text=True)
            self.assertIn('kvpn auto stop', help_text)
            # A copied release remains usable after removing its extraction source.
            import shutil
            shutil.rmtree(source)
            self.assertEqual(subprocess.check_output([str(link), '--version'], text=True).strip(), version)

    def test_install_idempotent_and_requires_explicit_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prefix, bin_dir = root / 'releases', root / 'bin'
            link = install.install(ROOT, prefix, bin_dir)
            self.assertEqual(install.install(ROOT, prefix, bin_dir), link)
            link.unlink()
            link.symlink_to(root / 'previous-kvpn')
            with self.assertRaisesRegex(ValueError, 'Existing kvpn symlink'):
                install.install(ROOT, prefix, bin_dir)
            self.assertEqual(os.readlink(link), str(root / 'previous-kvpn'))
            install.install(ROOT, prefix, bin_dir, replace=True)
            installed_source = link.resolve().parent
            (installed_source / 'kvpn_sms.py').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'different files'):
                install.install(ROOT, prefix, bin_dir, replace=True)
            link.unlink()
            link.write_text('owned regular file')
            with self.assertRaisesRegex(ValueError, 'regular file'):
                install.install(ROOT, prefix, bin_dir, replace=True)
            self.assertEqual(link.read_text(), 'owned regular file')

    def test_symlink_payload_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            import shutil
            root = Path(tmp)
            source = root / 'source'
            for name in RELEASE_FILES:
                dest = source / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, dest)
            victim = source / 'kvpn_sms.py'
            victim.unlink()
            victim.symlink_to(ROOT / 'kvpn_sms.py')
            with self.assertRaisesRegex(ValueError, 'unsafe'):
                install.install(source, root / 'releases', root / 'bin')
            self.assertFalse((root / 'bin').exists())

    def test_failure_reason_persisted_without_exception_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = Manager(Path(tmp) / 'state')
            with patch.object(kvpn_auto, 'process', return_value=None), patch.object(kvpn_auto.subprocess, 'run', side_effect=OSError('SECRET-DO-NOT-LOG')):
                with self.assertRaises(OSError):
                    kvpn_auto.supervise(manager, Mock(), Mock())
            value = (manager.directory / 'auto.json').read_text()
            self.assertNotIn('SECRET', value)
            state = json.loads(value)
            self.assertEqual(state['phase'], 'stopped')
            self.assertIn('Recovery failed', state['stop_reason'])

if __name__ == '__main__':
    unittest.main()
