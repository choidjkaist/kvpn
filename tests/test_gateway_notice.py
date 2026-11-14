import importlib.machinery
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('kvpn_notice_cli', str(Path(__file__).resolve().parents[1] / 'kvpn'))
spec = importlib.util.spec_from_loader(loader.name, loader)
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)

URL = cli.IVANTI + '/dana-na/auth/url_test/welcome.cgi'
LOGIN = '<form action="login.cgi" method="POST"></form>'
NOTICE = '''<form action="welcome.cgi" method="POST">
<input type="hidden" name="state" value="synthetic&amp;value">
<input type="submit" name="sn-preauth-proceed" value="Proceed">
<input type="submit" name="sn-preauth-decline" value="Decline"></form>'''


class GatewayNoticeTests(unittest.TestCase):
    def run_begin(self, first, second=LOGIN):
        self.gateway = cli.Ivanti()
        self.output = io.StringIO()
        with patch.object(cli, 'http_get', return_value=(URL, first)), \
             patch.object(cli, 'http_post', return_value=(URL, second)) as post, \
             redirect_stdout(self.output):
            result = self.gateway.begin()
        return result, post

    def test_direct_login_needs_no_acknowledgement(self):
        result, post = self.run_begin(LOGIN)
        self.assertEqual(result, URL)
        post.assert_not_called()

    def test_notice_preserves_session_hidden_fields_and_only_proceeds(self):
        result, post = self.run_begin(NOTICE, LOGIN.replace('"', "'"))
        self.assertEqual(result, URL)
        post.assert_called_once_with(self.gateway.opener, URL,
            {'state': 'synthetic&value', 'sn-preauth-proceed': 'Proceed'}, referer=URL)
        self.assertEqual(self.gateway.login_url, URL.replace('welcome.cgi', 'login.cgi'))
        self.assertNotIn('synthetic&value', self.output.getvalue())

    def test_unknown_page_does_not_submit(self):
        with patch.object(cli, 'http_get', return_value=(URL, '<h1>Maintenance</h1>')), \
             patch.object(cli, 'http_post') as post:
            with self.assertRaisesRegex(cli.KvpnError, 'no SMS requested'):
                cli.Ivanti().begin()
            post.assert_not_called()

    def test_repeated_notice_stops_after_one_post(self):
        with patch.object(cli, 'http_get', return_value=(URL, NOTICE)), \
             patch.object(cli, 'http_post', return_value=(URL, NOTICE)) as post, \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(cli.KvpnError, 'after the pre-sign-in'):
                cli.Ivanti().begin()
            self.assertEqual(post.call_count, 1)

    def test_unsafe_notice_destination_is_not_submitted(self):
        for action in ('https://other.test/welcome.cgi', '/logout.cgi'):
            with self.subTest(action=action), \
                 patch.object(cli, 'http_get', return_value=(URL, NOTICE.replace('action="welcome.cgi"', 'action="' + action + '"'))), \
                 patch.object(cli, 'http_post') as post:
                with self.assertRaisesRegex(cli.KvpnError, 'destination'):
                    cli.Ivanti().begin()
                post.assert_not_called()

    def test_cross_origin_login_is_rejected(self):
        with self.assertRaisesRegex(cli.KvpnError, 'login destination'):
            self.run_begin('<form action="https://other.test/login.cgi">')


if __name__ == '__main__':
    unittest.main()
