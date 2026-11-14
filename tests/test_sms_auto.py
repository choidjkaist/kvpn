import importlib.machinery
import importlib.util
import json
import io
from contextlib import redirect_stdout, closing
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kvpn_sms import SMSReader, SMSError, extract_code, APPLE_EPOCH
import kvpn_auto as auto
from kvpn_runtime import Manager

loader=importlib.machinery.SourceFileLoader('kvpn_cli',str(Path(__file__).resolve().parents[1]/'kvpn'))
spec=importlib.util.spec_from_loader(loader.name,loader)
cli=importlib.util.module_from_spec(spec); loader.exec_module(cli)

class SMSTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'chat.db'
        self.db=sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.executescript('CREATE TABLE handle (id TEXT); CREATE TABLE message (guid TEXT,date INTEGER,text TEXT,attributedBody BLOB,handle_id INTEGER,is_from_me INTEGER); INSERT INTO handle VALUES ("KAIST-SENDER"),("OTHER");')
        self.reader=SMSReader(self.path)
    def add(self,text='KAIST 인증번호 [123456]',sender=1,date=None,outgoing=0,blob=None):
        self.db.execute('INSERT INTO message VALUES (?,?,?,?,?,?)',('id',int(((date or time.time())-APPLE_EPOCH)*1e9),text,blob,sender,outgoing));self.db.commit()
    def test_complete_sms_authentication_flow(self):
        self.add(date=time.time()-60)
        manager=Mock()
        manager.session_replacement_allowed.return_value = True
        manager.launch.return_value=0
        portal=Mock()
        portal.send_code.side_effect=lambda *_: self.add('KAIST 인증번호 [654321]')
        portal.verify.return_value='synthetic-second-factor'
        ivanti=Mock()
        ivanti.begin.return_value='https://example.test/'
        ivanti.finish.return_value='synthetic-cookie'
        args=SimpleNamespace(sms_auto=True,sms_sender='KAIST-SENDER',
            inspect_session=False,foreground=False,reconnect_timeout=300,estimate_hours=10)
        output=io.StringIO()
        with patch.object(cli,'load_credentials',return_value=('user','synthetic-password','realm')), \
             patch.object(cli,'SMSReader',return_value=self.reader), \
             patch.object(cli,'Portal',return_value=portal), \
             patch.object(cli,'Ivanti',return_value=ivanti), \
             patch('kvpn_timing.observe'), patch('builtins.input') as prompt, redirect_stdout(output):
            self.assertEqual(cli.authenticate_and_connect(manager,args),0)
        prompt.assert_not_called()
        portal.send_code.assert_called_once_with('user','sms')
        portal.verify.assert_called_once_with('user','654321')
        ivanti.finish.assert_called_once_with('user','synthetic-password','realm','synthetic-second-factor',unattended=True,replace_existing=True)
        self.assertTrue(manager.launch.call_args.kwargs['unattended'])
        self.assertEqual(manager.launch.call_args.args[0],'synthetic-cookie')
        for secret in ('654321','synthetic-password','synthetic-second-factor','synthetic-cookie'):
            self.assertNotIn(secret,output.getvalue())

    def test_context_and_ambiguity(self):
        self.assertEqual(extract_code('KAIST 인증번호 [123456]'),'123456')
        for text in ['Google 인증번호 123456','KAIST 전화 123456','KAIST 인증 123456 654321','KAIST 인증번호 1234567']:
            self.assertIsNone(extract_code(text))
    def test_archive_fallback(self):
        baseline=self.reader.baseline();self.add(text=None,blob=b'\xff'+ 'KAIST 인증번호 [123456]'.encode()+b'\x00')
        self.assertEqual(self.reader.wait('KAIST-SENDER',baseline,timeout=.1),'123456')
    def test_fresh_sender_bound_code(self):
        self.add(date=time.time()-10)
        baseline=self.reader.baseline()
        self.add('KAIST 인증 654321',sender=2)
        self.add('KAIST 인증 222222',outgoing=1)
        self.add('KAIST 인증 999999',date=time.time()-100)
        self.add()
        self.assertEqual(self.reader.wait('KAIST-SENDER',baseline,timeout=.1),'123456')
    def test_old_code_not_reused(self):
        self.add();baseline=self.reader.baseline()
        with patch('kvpn_sms.time.sleep'),patch('kvpn_sms.time.monotonic',side_effect=[0,0,2]):
            with self.assertRaisesRegex(SMSError,'No fresh'):self.reader.wait('KAIST-SENDER',baseline,timeout=1)
    def test_sender_discovery_ambiguous(self):
        self.add('KVPN OTP number : [123456]');self.assertEqual(self.reader.discover_sender(),'KAIST-SENDER')
        self.add('KVPN OTP number : [654321]',sender=2)
        with self.assertRaisesRegex(SMSError,'unique'):self.reader.discover_sender()
    def test_discovery_excludes_general_kaist_login(self):
        self.add('KVPN OTP number : [123456]')
        self.add('KAIST 인증번호는 654321 입니다.',sender=2)
        self.assertEqual(self.reader.discover_sender(),'KAIST-SENDER')

    def test_two_fresh_codes_fail_closed(self):
        baseline=self.reader.baseline();self.add();self.add('KAIST 인증 654321')
        with self.assertRaisesRegex(SMSError,'Multiple'):self.reader.wait('KAIST-SENDER',baseline)
    def test_cancel_before_read(self):
        with self.assertRaisesRegex(SMSError,'stopped'):self.reader.wait('KAIST-SENDER',(0,time.time()),cancelled=lambda:True)
    def test_missing_database_no_creation(self):
        missing=Path(self.tmp.name)/'missing'
        with self.assertRaises(SMSError): SMSReader(missing).baseline()
        self.assertFalse(missing.exists())
    def test_query_only(self):
        with closing(self.reader.connect()) as db:
            with self.assertRaises(sqlite3.OperationalError): db.execute('DELETE FROM message')

    def test_schema_failure_is_not_misreported_as_permission(self):
        self.db.execute('DROP TABLE message');self.db.commit()
        with self.assertRaisesRegex(SMSError,'file is readable, but SQLite failed'):
            self.reader.baseline()
    def test_permission_error_names_actual_terminal(self):
        with patch.dict('os.environ', {'TERM_PROGRAM':'ghostty'}), patch('kvpn_sms.os.open',side_effect=PermissionError(1,'Operation not permitted')):
            with self.assertRaisesRegex(SMSError,'Full Disk Access for Ghostty'):
                self.reader.baseline()

    def test_file_permission_error_distinguished(self):
        with patch('kvpn_sms.os.open',side_effect=PermissionError(1,'Operation not permitted')):
            with self.assertRaisesRegex(SMSError,'direct file access'):
                self.reader.baseline()

class AutoTests(unittest.TestCase):
    def test_rate_limit(self):
        self.assertFalse(auto.retry_allowed([1,2,3],4))
        self.assertTrue(auto.retry_allowed([1,2,3],3604))
    def test_live_tunnel_no_auth_and_manual_stop(self):
        with tempfile.TemporaryDirectory() as d:
            manager=Manager(Path(d)/'state');manager.load=Mock(return_value={})
            manager.status=Mock(return_value={'managed':True,'unmanaged_pids':[]})
            login=Mock()
            with patch.object(auto.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout="",stderr="")),patch.object(auto.time,'sleep',side_effect=lambda _:auto.request_stop(manager)):
                auto.supervise(manager,SimpleNamespace(),login)
            login.assert_not_called()
    def test_failed_login_only_one_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            manager=Manager(Path(d)/'state');manager.load=Mock(return_value={})
            manager.status=Mock(return_value={'managed':False,'unmanaged_pids':[]});manager.assert_idle=Mock()
            login=Mock(side_effect=SMSError('timeout'))
            with patch.object(auto.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout="",stderr="")),patch.object(auto.time,'sleep'),patch.object(auto,'gateway_available',return_value=True):
                with self.assertRaises(SMSError):auto.supervise(manager,SimpleNamespace(),login)
            self.assertEqual(login.call_count,1)
    def test_sudo_unavailable_no_login(self):
        with tempfile.TemporaryDirectory() as d:
            manager=Manager(Path(d)/'state');login=Mock()
            with patch.object(auto.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout="",stderr="")):
                with self.assertRaisesRegex(auto.RuntimeError,'authorization'):auto.supervise(manager,SimpleNamespace(),login)
            login.assert_not_called()
    def test_active_session_not_replaced(self):
        iv=cli.Ivanti();iv.login_url='https://example.test/login';iv.welcome_url='https://example.test/'
        with patch.object(cli,'http_post',return_value=('https://example.test/?p=user-confirm','')),patch('builtins.input') as inp:
            with self.assertRaisesRegex(cli.KvpnError,'retained'):iv.finish('u','p','r','otp',unattended=True)
            inp.assert_not_called()
    def test_authorized_session_replacement_uses_same_login_once(self):
        iv = cli.Ivanti()
        iv.login_url = 'https://example.test/login.cgi'
        iv.welcome_url = 'https://example.test/'
        with patch.object(cli, 'http_post', return_value=('https://example.test/?p=user-confirm', '')), \
             patch.object(iv, '_confirm_continue', return_value=('https://example.test/home', '')) as confirm, \
             patch.object(cli, 'cookie_value', return_value='test-session'), patch('builtins.input') as inp:
            self.assertEqual(iv.finish('u', 'p', 'r', 'otp', unattended=True, replace_existing=True), 'test-session')
            confirm.assert_called_once()
            inp.assert_not_called()

    def test_replacement_rejected_does_not_retry(self):
        iv = cli.Ivanti()
        iv.login_url = 'https://example.test/login.cgi'
        iv.welcome_url = 'https://example.test/'
        page = ('https://example.test/?p=user-confirm', '')
        with patch.object(cli, 'http_post', return_value=page), \
             patch.object(iv, '_confirm_continue', return_value=page) as confirm:
            with self.assertRaisesRegex(cli.ExistingSessionError, 'did not accept'):
                iv.finish('u', 'p', 'r', 'otp', unattended=True, replace_existing=True)
            confirm.assert_called_once()

    def test_takeover_policy_requires_explicit_boolean(self):
        with tempfile.TemporaryDirectory() as d:
            manager = Manager(Path(d)/'state')
            self.assertFalse(manager.session_replacement_allowed())
            path = manager.directory/'preferences.json'
            for value, expected in [(False, False), ('true', False), (True, True)]:
                path.write_text(json.dumps({'replace_existing_session': value}))
                self.assertEqual(manager.session_replacement_allowed(), expected)

    def test_auto_permission_failure_before_credentials_or_sms(self):
        with patch.object(cli.shutil,'which',return_value='/fake/openconnect'),patch.object(cli,'Manager'),patch.object(cli.SMSReader,'baseline',side_effect=SMSError('permission')),patch.object(cli,'load_credentials') as creds,patch.object(cli.Portal,'send_code') as send:
            with self.assertRaises(SMSError):cli.main(['auto'])
            creds.assert_not_called();send.assert_not_called()

    def test_offline_waits_without_sms(self):
        with tempfile.TemporaryDirectory() as d:
            manager=Manager(Path(d)/'state');manager.load=Mock(return_value={})
            manager.status=Mock(return_value={'managed':False,'unmanaged_pids':[]})
            login=Mock()
            with patch.object(auto.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='',stderr='')),patch.object(auto,'gateway_available',return_value=False),patch.object(auto.time,'sleep',side_effect=lambda _:auto.request_stop(manager)):
                auto.supervise(manager,SimpleNamespace(),login)
            login.assert_not_called()

class SimpleCommandTests(unittest.TestCase):
    def test_default_enters_auto_supervisor(self):
        with patch.object(cli.shutil, 'which', return_value='/fake/openconnect'), patch.object(cli, 'Manager') as manager, patch.object(cli, 'SMSReader') as reader, patch.object(cli, 'load_credentials', return_value=('test','secret','realm')), patch.object(cli.sys.stdin, 'isatty', return_value=True), patch.object(cli.subprocess, 'run'), patch.object(auto, 'supervise') as supervise:
            manager.return_value.status.return_value={'unmanaged_pids':[]}
            cli.main([])
            self.assertTrue(supervise.call_args.args[1].sms_auto)
            self.assertEqual(supervise.call_args.args[1].command,'auto')

    def test_off_stops_supervisor_then_disconnects(self):
        events=[]
        with patch.object(cli, 'Manager') as manager, patch.object(auto, 'request_stop', side_effect=lambda m: events.append('stop')):
            manager.return_value.disconnect.side_effect=lambda: events.append('disconnect')
            cli.main(['off'])
            self.assertEqual(events,['stop','disconnect'])

class CommandPresentationTests(unittest.TestCase):
    def test_already_running_does_not_access_sms_or_sudo(self):
        with patch.object(cli, 'Manager'), patch.object(auto, 'auto_status', return_value={'running':True}), patch.object(cli, 'SMSReader') as sms, patch.object(cli.subprocess, 'run') as run:
            cli.main([])
            sms.assert_not_called()
            run.assert_not_called()

    def test_typos_never_connect(self):
        from contextlib import redirect_stderr
        for typo in ['satus', 'statsu', 'of', 'unknown']:
            output=io.StringIO()
            with redirect_stderr(output), patch.object(cli, 'Manager') as manager:
                with self.assertRaises(SystemExit) as error:
                    cli.main([typo])
                self.assertEqual(error.exception.code,2)
                manager.assert_not_called()
            self.assertIn('\x1b[31m',output.getvalue())
            self.assertNotIn('choose from',output.getvalue())

    def test_json_remains_machine_readable(self):
        with patch.object(cli, 'Manager') as manager, patch.object(auto, 'auto_status', return_value={'running':False}), redirect_stdout(io.StringIO()) as output:
            manager.return_value.status.return_value={'status':'disconnected'}
            cli.main(['status','--json'])
        self.assertEqual(json.loads(output.getvalue())['status'],'disconnected')
