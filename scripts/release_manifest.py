"""Explicit public distribution allowlist; no home files or Git metadata."""
RUNTIME_FILES = (
    'kvpn', 'kvpn_auto.py', 'kvpn_check.py', 'kvpn_runtime.py',
    'kvpn_session.py', 'kvpn_session_channel.py', 'kvpn_sms.py',
    'kvpn_timing.py', 'kvpn_ui.py', 'kvpn_setup.py',
)
RELEASE_FILES = RUNTIME_FILES + (
    'install.sh', 'scripts/install.py', 'scripts/release_manifest.py',
    'README.md', 'README.en.md', 'LICENSE', 'CHANGELOG.md', 'SECURITY.md',
    'docs/architecture.md', 'docs/troubleshooting.md',
)
