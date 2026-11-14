"""Terminal presentation with always-on ANSI colors, as requested by the owner."""

def color(text, code):
    return f'\033[{code}m{text}\033[0m'


def title():
    print('\n  ' + color('KVPN', '1;36') + '  ' + color('KAIST VPN', '2') + '\n')

def row(label, value, tone=None):
    print(f'  {label:<15} {color(value, tone) if tone else value}')

def note(text):
    print('  ' + color(text, '2'), flush=True)


COMMANDS = (
    ('kvpn setup', 'First-use guide (no login)'),
    ('kvpn', 'Connect with automatic recovery (macOS)'),
    ('kvpn connect', 'Connect once; enter verification code'),
    ('kvpn auto stop', 'Stop recovery; keep the current VPN'),
    ('kvpn disconnect', 'Stop recovery and disconnect VPN'),
    ('kvpn status', 'Show connection and recovery state'),
    ('kvpn doctor', 'Check local prerequisites'),
    ('kvpn logs', 'Show sanitized connection log'),
    ('kvpn config', 'Show session replacement policy'),
    ('kvpn help', 'Show help'),
)


def command_help():
    return '\n'.join('  ' + color(f'{command:<19}', '36') + color(description, '2')
                     for command, description in COMMANDS)


def commands():
    print(command_help())
