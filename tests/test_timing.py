import unittest
from kvpn_timing import parse_limits

class TimingTests(unittest.TestCase):
 def test_fixed_limit_not_expiry(self):
  a=parse_limits({'DSmaxTimeout':36000,'DSgwtime':1791168600},1791168500,1791168600)
  b=parse_limits({'DSmaxTimeout':36000,'DSgwtime':1791168660},1791168500,1791168660)
  self.assertEqual(a['server_max_session_seconds'],b['server_max_session_seconds'])
  self.assertIsNone(a['server_expiry'])
  self.assertNotIn('server_remaining_seconds',a)
 def test_reject_bad_limit(self):
  for limit in (0,-1,'36000',True,float('nan')):
   with self.assertRaises(ValueError):parse_limits({'DSmaxTimeout':limit,'DSgwtime':1791168600},1791168500)
 def test_only_allowlisted_values_persist(self):
  data=parse_limits({'DSmaxTimeout':36000,'DSgwtime':1791168600,'xsauth':'SECRET','username':'PRIVATE'},1791168500)
  self.assertNotIn('SECRET',str(data));self.assertNotIn('PRIVATE',str(data))
