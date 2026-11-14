"""Foreground supervisor; native transport retry finishes before fresh SMS login."""
from kvpn_ui import row, note
import fcntl
import json
import os
import subprocess
import socket
import time
from collections import deque
from kvpn_runtime import secure_open, process, RuntimeError


def retry_allowed(attempts, now):
    # Cap even successful-but-short-lived reconnect loops, not just auth failures.
    return sum(now-t < 3600 for t in attempts) < 3


def gateway_available():
    try:
        with socket.create_connection(('kvpn.kaist.ac.kr',443),timeout=5):
            return True
    except OSError:
        return False


def write_status(manager, phase, stop_reason=None):
    value = {'phase': phase, 'pid': os.getpid(), 'identity': process(os.getpid()),
             'updated_at': time.time(), 'stop_reason': stop_reason}
    temp = manager.directory / 'auto.new'
    fd = secure_open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f)
    os.replace(temp, manager.directory / 'auto.json')


def auto_status(manager):
    try:
        fd=secure_open(manager.directory/'auto.json',os.O_RDONLY)
        with os.fdopen(fd) as f: value=json.load(f)
        identity=process(value.get('pid'))
        value['running']=bool(value.get('phase') != 'stopped' and identity and identity == value.get('identity'))
        return value
    except (OSError,ValueError,AttributeError):
        return {'running':False,'phase':'off'}


def request_stop(manager):
    fd=secure_open(manager.directory/'auto.stop',os.O_WRONLY|os.O_CREAT|os.O_TRUNC)
    os.close(fd)


def supervise(manager,args,login):
    fd=secure_open(manager.directory/'auto.lock',os.O_RDWR|os.O_CREAT)
    acquired=False
    reason='Stop requested'
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Automatic reconnect is already running.') from None
        acquired=True
        stop=manager.directory/'auto.stop'
        stop.unlink(missing_ok=True)
        args.cancelled=stop.exists
        attempts=deque(maxlen=10)
        last_privilege=float("-inf")
        row('Auto recovery', 'On · SMS', '32')
        note('Keep this terminal open. Use kvpn off in another tab to stop.')
        note('Ctrl+C stops auto reconnect only; the VPN stays connected.')
        while not stop.exists():
            # No privileged password prompts or OTP requests after authorization expires.
            if time.monotonic()-last_privilege>=60:
                r=subprocess.run(['sudo','-n','-v'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                if r.returncode: raise RuntimeError('Administrator authorization unavailable; automatic reconnect stopped before requesting SMS.')
                last_privilege=time.monotonic()
            state=manager.load()
            if state.get('disconnected_at') and attempts:
                break
            status=manager.status()
            if status['unmanaged_pids']:
                raise RuntimeError('Unmanaged VPN detected; no automatic login attempted.')
            if status['managed']:
                write_status(manager,'watching connection')
            else:
                if not gateway_available():
                    write_status(manager,'waiting for network')
                    for _ in range(30):
                        if stop.exists(): return
                        time.sleep(1)
                    continue
                if not retry_allowed(attempts,time.time()):
                    raise RuntimeError('Three login attempts within an hour; stopped to prevent an SMS/reconnect loop.')
                write_status(manager,'waiting before reconnect')
                # Allow old process/route cleanup and stop requests to settle.
                for _ in range(10):
                    if stop.exists(): return
                    time.sleep(1)
                with manager.lock():
                    if stop.exists(): return
                    manager.assert_idle()
                    attempts.append(time.time())
                    write_status(manager,'authenticating with SMS')
                    # Any auth/startup failure stops; do not spam OTPs.
                    login(manager,args)
                write_status(manager,'watching connection')
            for _ in range(5):
                if stop.exists(): return
                time.sleep(1)
    except KeyboardInterrupt:
        reason='Interrupted; existing tunnel retained'
        raise
    except Exception:
        # Do not persist exception text: it could contain authentication details.
        reason='Recovery failed; run kvpn doctor and review the terminal error before restarting'
        raise
    finally:
        try:
            if acquired: write_status(manager,'stopped',reason)
        finally:
            os.close(fd)
