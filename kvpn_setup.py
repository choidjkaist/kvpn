"""First-use guidance without requesting credentials, SMS or VPN changes."""
import sys
from kvpn_check import check, display
from kvpn_ui import note


def guide(manager):
    display(check(manager))
    if sys.platform == 'darwin':
        steps = [
            '1. Install Python 3.9+ and OpenConnect: brew install python openconnect',
            '2. Run kvpn connect; authenticate with your own KAIST account and choose to save credentials in Keychain.',
            '3. Enable iPhone SMS forwarding to this Mac and verify KAIST SMS arrives in Messages.',
            '4. Grant Full Disk Access to the terminal app you actually use, then fully quit and reopen it.',
            '5. Run kvpn sms-check after receiving a normal KVPN code. It sends no SMS.',
            '6. Run kvpn auto and keep that terminal open. An existing managed connection is preserved.',
            '7. Use kvpn disconnect to stop both, or kvpn auto stop to stop recovery only.',
        ]
    else:
        steps = [
            'Linux manual connection is experimental; automatic Messages verification is unavailable.',
            'Install Python 3.9+, OpenConnect, its vpnc-script and sudo using your package manager.',
            'Run kvpn connect --foreground and enter the SMS/email code yourself; Ctrl+C ends this foreground connection.',
            'Without Keychain, opting to save credentials stores the password in a user-only plaintext config file.',
        ]
    print()
    for step in steps:
        note(step)
    note('Setup only displays guidance and local diagnostics. No login, SMS or credential lookup occurred.')
