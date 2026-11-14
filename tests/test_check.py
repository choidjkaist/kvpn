import unittest
from unittest.mock import Mock, patch
import kvpn_check
from kvpn_sms import SMSError

class CheckTests(unittest.TestCase):
    def test_disconnected_is_not_failure(self):
        manager=Mock()
        manager.status.return_value={'status':'disconnected'}
        with patch.object(kvpn_check.shutil,'which',return_value='/test/openconnect'), patch.object(kvpn_check,'auto_status',return_value={'running':False}), patch.object(kvpn_check,'SMSReader') as reader:
            results=kvpn_check.check(manager)
            self.assertFalse(any(r['status']=='error' for r in results))
            reader.return_value.baseline.assert_called_once()
            reader.return_value.wait.assert_not_called()
            manager.launch.assert_not_called()
            manager.disconnect.assert_not_called()

    def test_missing_install_and_permission_are_both_reported(self):
        manager=Mock()
        manager.status.return_value={'status':'connected'}
        with patch.object(kvpn_check.shutil,'which',return_value=None), patch.object(kvpn_check,'auto_status',return_value={'running':False}), patch.object(kvpn_check,'SMSReader') as reader:
            reader.return_value.baseline.side_effect=SMSError('Permission denied')
            results=kvpn_check.check(manager)
            self.assertEqual([r['name'] for r in results if r['status']=='error'],['OpenConnect','Messages'])
