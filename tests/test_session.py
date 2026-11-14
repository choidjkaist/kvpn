import unittest
from kvpn_session import Structure,safe_path,snippets

class SessionDiscoveryTests(unittest.TestCase):
 def test_origin_and_query_scope(self):
  self.assertEqual(safe_path('/dana/a.js?token=secret','https://kvpn.kaist.ac.kr/'),'/dana/a.js')
  self.assertIsNone(safe_path('https://other.test/a.js','https://kvpn.kaist.ac.kr/'))
  self.assertIsNone(safe_path('//other.test/a.js','https://kvpn.kaist.ac.kr/'))
 def test_hidden_and_script_values_not_visible_text(self):
  p=Structure();p.feed('<input type="hidden" value="SECRET"><script>SECRET</script><p>Session time remaining: 9h</p>')
  self.assertNotIn('SECRET',''.join(p.text))
  self.assertIn('9h',''.join(p.text))
 def test_timing_only_bounded(self):
  self.assertEqual(snippets('ordinary page'),[])
  self.assertLessEqual(len(snippets('\n'.join('timeout'+str(n) for n in range(100)))),40)

class SessionChannelTests(unittest.TestCase):
 def test_cross_origin_and_unverified_action_refused(self):
  from kvpn_session_channel import fetch
  for path,method in [('https://other.test/x','GET'),('//other.test/x','GET'),('/api/v1/session','POST')]:
   with self.assertRaises((ValueError,FileNotFoundError)):
    fetch('SYNTHETIC',{'path':path,'method':method})
 def test_large_static_bundle_and_cookie_not_returned(self):
  from kvpn_session_channel import fetch
  from unittest.mock import Mock,patch
  response=Mock();response.url='https://kvpn.kaist.ac.kr/dana-cached/a.js';response.status=200;response.read.return_value='a'.encode()*2000000
  context=Mock();context.__enter__=Mock(return_value=response);context.__exit__=Mock(return_value=False)
  opener=Mock();opener.open.return_value=context
  with patch('urllib.request.build_opener',return_value=opener):
   r=fetch('SYNTHETIC',{'path':'/dana-cached/a.js'})
  self.assertEqual(len(r['body']),2000000)
  self.assertNotIn('SYNTHETIC',str(r))
