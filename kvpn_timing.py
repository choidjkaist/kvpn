"""Verified gateway limits, explicitly separate from authentication expiry."""
import json, math, os, time
from kvpn_runtime import Manager,secure_open

ENDPOINT='https://kvpn.kaist.ac.kr/api/v1/enduser/landing-page'

def parse_limits(data,authenticated_at,sampled_at=None):
    limit=data.get('DSmaxTimeout')
    server_time=data.get('DSgwtime')
    if type(limit) is not int or not 0 < limit <= 366*86400:
        raise ValueError('Invalid gateway session limit')
    if type(server_time) is not int or server_time <= 0:
        raise ValueError('Invalid gateway clock')
    if not math.isfinite(authenticated_at):raise ValueError('Invalid authentication time')
    return {'authenticated_at':authenticated_at,'sampled_at':sampled_at or time.time(),
            'server_max_session_seconds':limit,'server_time':server_time,
            'source':ENDPOINT,'server_expiry':None,
            'meaning':'Maximum session duration, not remaining time or confirmed renewal.'}

def save_limits(data):
    dest=Manager().directory/'server-limits.json'
    fd=secure_open(dest,os.O_WRONLY|os.O_CREAT|os.O_TRUNC)
    with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2)

def observe(opener,authenticated_at):
    with opener.open(ENDPOINT,timeout=8) as response:
        if response.url!=ENDPOINT:raise ValueError('Unexpected gateway redirect')
        data=json.loads(response.read(1000000))
    save_limits(parse_limits(data,authenticated_at))
