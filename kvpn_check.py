"""Local readiness checks without login, OTP requests or connection changes."""
import shutil
import sys
from kvpn_auto import auto_status
from kvpn_sms import SMSReader, SMSError
from kvpn_runtime import RuntimeError as LifecycleError
from kvpn_ui import title, row, note


def check(manager):
    results = []
    def add(name, status, detail):
        results.append(dict(name=name, status=status, detail=detail))
    add('OpenConnect', 'ok' if shutil.which('openconnect') else 'error',
        'Installed' if shutil.which('openconnect') else 'Missing — brew install openconnect')
    try:
        value = manager.status()
        state = value['status']
        add('VPN', 'ok' if state == 'connected' else 'info', state.capitalize())
        if value.get('unmanaged_pids'):
            add('Other VPN', 'warning', 'Unmanaged connection detected')
    except (LifecycleError, OSError, ValueError) as error:
        add('VPN', 'error', str(error))
    try:
        auto = auto_status(manager)
        add('Auto recovery', 'ok' if auto['running'] else 'info',
            auto.get('phase', 'Running') if auto['running'] else 'Off')
    except (OSError, ValueError, TypeError) as error:
        add('Auto recovery', 'error', str(error))
    if sys.platform != 'darwin':
        add('Messages', 'info', 'Automatic SMS verification is macOS-only; use manual connect on Linux')
        return results
    try:
        SMSReader().baseline()  # Metadata only: no message body or OTP is read.
        add('Messages', 'ok', 'Readable by this app')
    except (SMSError, OSError) as error:
        add('Messages', 'error', str(error))
    return results


def display(results):
    title()
    tones = {'ok': '32', 'info': '36', 'warning': '33', 'error': '31'}
    for result in results:
        detail = result['detail']
        if len(detail) > 85:
            row(result['name'], 'Needs attention', tones[result['status']])
            import textwrap
            for line in textwrap.wrap(detail, width=76):
                note('  ' + line)
        else:
            row(result['name'], detail, tones[result['status']])
    print()
    note('Local checks only. No sign-in or SMS requested.')
    note('SMS delivery and server access are not tested.')
