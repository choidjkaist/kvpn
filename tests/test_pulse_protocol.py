import struct
import unittest
from experiments.pulse_protocol import (avp, parse_avps, candidate_cookie_response,
    Channel, TCG, VENDOR, AUTH_TYPE, eap_response, authenticate_candidate)


class FakeChannel:
    def __init__(self, packets):
        self.packets = iter(packets)
        self.sent = []
    def send(self, *args): self.sent.append(args)
    def receive(self): return next(self.packets)


def challenge(attrs):
    eap = bytearray(eap_response(7, attrs)); eap[0] = 1
    return TCG, 5, struct.pack('!I', AUTH_TYPE) + eap


class ProtocolTests(unittest.TestCase):
    def test_extension_changes_only_request_flag(self):
        before = parse_avps(candidate_cookie_response(7, 'dummy', False)[12:])
        after = parse_avps(candidate_cookie_response(7, 'dummy', True)[12:])
        self.assertEqual(before[:-1], after[:-1])
        self.assertEqual(after[-1], (VENDOR, 0xd6b, struct.pack('!I', 0x11)))
        self.assertEqual(before[-1][2], struct.pack('!I', 0x10))

    def test_malformed_avps_rejected(self):
        for data in [b'x', struct.pack('!II', 1, 7), struct.pack('!III',1,0x8000000d,VENDOR)]:
            with self.assertRaises(ValueError): parse_avps(data)

    def test_secret_not_in_result_and_success_not_renewal_proof(self):
        attrs = avp(0xd53,b'new-dummy')+avp(0xd5c,struct.pack('!I',36000))
        final = (TCG,7,struct.pack('!I',AUTH_TYPE)+b'\x03\x07\x00\x04')
        ch = FakeChannel([challenge(attrs),final]); session={'cookie':'dummy'}
        result=authenticate_candidate(ch,7,session,True)
        self.assertEqual(session['cookie'],'new-dummy')
        self.assertEqual(result['reported_lifetime_seconds'],36000)
        self.assertFalse(result['renewal_verified'])
        self.assertNotIn('dummy',repr(result))

    def test_prompt_does_not_trigger_password_or_second_request(self):
        ch=FakeChannel([challenge(avp(0xd81,b'Password:'))])
        with self.assertRaises(ValueError):authenticate_candidate(ch,7,{'cookie':'dummy'},True)
        self.assertEqual(len(ch.sent),1)

    def test_missing_final_success_is_failure(self):
        attrs=avp(0xd53,b'new-dummy')+avp(0xd5c,struct.pack('!I',36000))
        ch=FakeChannel([challenge(attrs),(TCG,7,b'invalid')])
        with self.assertRaises(ValueError):authenticate_candidate(ch,7,{'cookie':'dummy'},True)

    def test_oversized_frame_rejected_before_payload(self):
        class Stream:
            def recv(self,n):return struct.pack('!IIII',TCG,5,20000,0)
        with self.assertRaises(ValueError):Channel(Stream()).receive()

if __name__=='__main__':unittest.main()
