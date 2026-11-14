"""Bounded KAIST Pulse preflight and offline renewal-packet construction.

Protocol reference: OpenConnect pulse.c (IF-T/TLS, EAP, vendor AVPs).
The default CLI only performs an unauthenticated preflight. Experimental cookie
submission is available only through an explicit in-process call; no scheduler.
Candidate request flags were derived by static inspection of the local client;
packet construction is NOT evidence that the gateway accepts renewal.
"""
import json
import socket
import ssl
import struct

HOST = 'kvpn.kaist.ac.kr'
TCG = 0x5597
JUNIPER = 0xa4c
VENDOR = 0x583
AUTH_TYPE = (JUNIPER << 8) | 1
MAX_PACKET = 16384


def avp(code, payload):
    size = 12 + len(payload)
    if size > MAX_PACKET:
        raise ValueError('AVP too large')
    return struct.pack('!III', code, 0x80000000 | size, VENDOR) + payload + b'\0' * (-size % 4)


def parse_avps(data):
    result = []
    while data:
        if len(data) < 8:
            raise ValueError('Truncated AVP')
        code, word = struct.unpack('!II', data[:8])
        length = word & 0xffffff
        vendor_present = bool(word & 0x80000000)
        header = 12 if vendor_present else 8
        padded = (length + 3) & ~3
        if length < header or padded > len(data):
            raise ValueError('Invalid AVP length')
        vendor = struct.unpack('!I', data[8:12])[0] if vendor_present else 0
        result.append((vendor, code, data[header:length]))
        data = data[padded:]
    return result


def eap_response(identifier, attributes):
    payload = b'\xfe' + JUNIPER.to_bytes(3, 'big') + struct.pack('!I', 1) + attributes
    return struct.pack('!BBH', 2, identifier, len(payload) + 4) + payload


def candidate_cookie_response(identifier, cookie, extend=False):
    if not cookie or len(cookie) > 4096 or any(c in cookie for c in '\r\n\0'):
        raise ValueError('Invalid cookie')
    # 0x10 is the native client's initial request-flags value; extension ORs 1.
    flags = 0x11 if extend else 0x10
    return eap_response(identifier,
        avp(0xd70, b'OpenConnect VPN Agent') +
        avp(0xd53, cookie.encode('ascii')) +
        avp(0xd6b, struct.pack('!I', flags)))


class Channel:
    def __init__(self, stream):
        self.stream = stream
        self.seq = 0

    def exact(self, length):
        result = b''
        while len(result) < length:
            part = self.stream.recv(length - len(result))
            if not part:
                raise ValueError('Unexpected EOF')
            result += part
        return result

    def send(self, vendor, kind, payload):
        if len(payload) + 16 > MAX_PACKET:
            raise ValueError('Packet too large')
        self.stream.sendall(struct.pack('!IIII', vendor, kind, len(payload)+16, self.seq)+payload)
        self.seq += 1

    def receive(self):
        vendor, kind, length, sequence = struct.unpack('!IIII', self.exact(16))
        if not 16 <= length <= MAX_PACKET:
            raise ValueError('Invalid IF-T length')
        return vendor, kind, self.exact(length - 16)


def decode_challenge(vendor, kind, payload):
    if vendor & 0xffffff != TCG or kind != 5 or len(payload) < 16:
        raise ValueError('Unexpected authentication packet')
    auth_type, = struct.unpack('!I', payload[:4])
    code, identifier, length = struct.unpack('!BBH', payload[4:8])
    if (auth_type != AUTH_TYPE or code != 1 or length != len(payload)-4 or
        payload[8:16] != b'\xfe'+JUNIPER.to_bytes(3,'big')+struct.pack('!I',1)):
        raise ValueError('Invalid expanded EAP challenge')
    return identifier, parse_avps(payload[16:])


def authenticate_candidate(channel, identifier, session, extend):
    # Explicit opt-in caller owns the session. It may be rotated by the gateway.
    channel.send(TCG, 6, struct.pack('!I', AUTH_TYPE) +
                 candidate_cookie_response(identifier, session['cookie'], extend))
    identifier, attributes = decode_challenge(*channel.receive())
    cookies = [v for vendor, code, v in attributes if vendor == VENDOR and code == 0xd53]
    lifetime = [v for vendor, code, v in attributes if vendor == VENDOR and code == 0xd5c]
    if len(cookies) != 1 or not cookies[0] or len(lifetime) != 1 or len(lifetime[0]) != 4:
        # Never answer password/OTP prompts or terminate another session.
        raise ValueError('Gateway did not return cookie and lifetime; no further authentication attempted')
    session['cookie'] = cookies[0].decode('ascii')
    channel.send(TCG, 6, struct.pack('!I', AUTH_TYPE) + eap_response(identifier, b''))
    vendor, kind, payload = channel.receive()
    if (vendor & 0xffffff != TCG or kind != 7 or len(payload) != 8 or
        payload[:4] != struct.pack('!I', AUTH_TYPE) or payload[4] != 3 or
        payload[5] != identifier or payload[6:] != b'\0\4'):
        raise ValueError('Missing final authentication success')
    return {'authentication_accepted': True, 'extension_requested': extend,
            'reported_lifetime_seconds': struct.unpack('!I', lifetime[0])[0],
            'renewal_verified': False}


def preflight(session=None, extend=False):
    if session is not None:
        raise ValueError('Live cookie trial disabled: parallel Pulse authentication invalidated the NC session')
    # Default: no credentials. No tunnel/configuration is requested in either mode.
    if extend and session is None:
        raise ValueError('Extension requires an explicitly supplied in-memory session')
    with socket.create_connection((HOST, 443), timeout=8) as tcp:
        with ssl.create_default_context().wrap_socket(tcp, server_hostname=HOST) as tls:
            tls.settimeout(8)
            tls.sendall(('GET / HTTP/1.1\r\nHost: '+HOST+'\r\n'
                         'User-Agent: OpenConnect VPN Agent\r\nContent-Type: EAP\r\n'
                         'Upgrade: IF-T/TLS 1.0\r\nContent-Length: 0\r\n\r\n').encode())
            headers = b''
            while not headers.endswith(b'\r\n\r\n'):
                piece = tls.recv(1)
                if not piece or len(headers) >= 16384:
                    raise ValueError('Invalid HTTP response')
                headers += piece
            status = headers.split(b'\r\n', 1)[0].split()[1]
            if status != b'101':
                return {'http_status': int(status), 'pulse_ready': False}
            channel = Channel(tls)
            channel.send(TCG, 1, struct.pack('!I', 0x00010202))
            vendor, kind, payload = channel.receive()
            if vendor & 0xffffff != TCG or kind != 2 or len(payload) != 4:
                raise ValueError('Invalid version response')
            version = payload[-1]
            client_ip = tls.getsockname()[0]
            channel.send(JUNIPER, 0x88, ('clientHostName=kvpn-preflight clientIp='+client_ip+'\n\0').encode('ascii'))
            vendor, kind, payload = channel.receive()
            if vendor & 0xffffff != TCG or kind != 5 or payload != struct.pack('!I', AUTH_TYPE):
                raise ValueError('Unexpected authentication challenge')
            identity = struct.pack('!BBH', 2, 1, 14) + b'\x01anonymous'
            channel.send(TCG, 6, struct.pack('!I', AUTH_TYPE) + identity)
            vendor, kind, payload = channel.receive()
            if vendor & 0xffffff != TCG or kind != 5 or len(payload) < 9:
                raise ValueError('Unexpected identity response')
            auth_type, = struct.unpack('!I', payload[:4])
            code, identifier, length = struct.unpack('!BBH', payload[4:8])
            if auth_type != AUTH_TYPE or code != 1 or length != len(payload)-4:
                raise ValueError('Invalid EAP response')
            eap_type = payload[8]
            result = {'http_status': 101, 'ift_version': version, 'eap_type': eap_type,
                      'pulse_ready': False, 'credentials_sent': False, 'tunnel_opened': False}
            if eap_type == 254:
                if len(payload) < 16 or payload[9:12] != JUNIPER.to_bytes(3,'big') or payload[12:16] != struct.pack('!I',1):
                    raise ValueError('Unsupported expanded EAP')
                attrs = parse_avps(payload[16:])
                result['attribute_codes'] = ['%x/%x' % (v,c) for v,c,_ in attrs]
                result['pulse_ready'] = True
                if session is not None:
                    result.update(authenticate_candidate(channel, identifier, session, extend))
                    result['credentials_sent'] = True
            return result


if __name__ == '__main__':
    try:
        print(json.dumps(preflight(), sort_keys=True))
    except (OSError, ValueError) as error:
        # Never print raw peer payloads or authentication data.
        print(json.dumps({'preflight_error': type(error).__name__}))
        raise SystemExit(1)
