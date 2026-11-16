# How KVPN works

KVPN handles KAIST authentication and starts OpenConnect to carry VPN traffic. In automatic mode, a foreground supervisor watches the managed OpenConnect process and signs in again if that process exits.

## Connection sequence

1. Establish an Ivanti sign-in session and open the AirCUVE authentication flow.
2. Request SMS or email verification and submit the code.
3. Exchange the authentication result for an Ivanti session cookie (DSID).
4. Pass the cookie to OpenConnect through standard input using its NC protocol.

Manual mode asks for the code in the terminal. Automatic mode uses saved credentials and reads SMS forwarded to the Mac's Messages app.

## Selecting an SMS code

KVPN opens `~/Library/Messages/chat.db` in SQLite read-only/query-only mode. A code must come from a new message row, meet the request-time cutoff, match the exact sender and KAIST authentication context, and contain one unambiguous six-digit code.

Sender discovery examines up to 200 recent incoming messages within 30 days. It requires KVPN-specific context. An explicit `--sms-sender` can supply an independently verified sender when discovery is ambiguous. Code delivery and database compatibility depend on Apple's Messages implementation.

## Reconnection

OpenConnect first retries the transport using the existing session. Its default reconnection window is 300 seconds, adjustable with `--reconnect-timeout`.

After the managed OpenConnect process exits, the supervisor waits for gateway TCP availability, then waits 10 seconds before attempting a fresh login. That check establishes TCP reachability, not whether the login page is working. KVPN waits up to 120 seconds for a new SMS code. Authentication failures stop supervision.

The supervisor permits at most three login attempts in a rolling hour. This counter is held in memory and resets when the supervisor restarts. Automatic reconnection does not extend a gateway session indefinitely.

The tunnel runs in the background; the supervisor remains attached to its terminal. While running, it refreshes existing sudo authorization every 60 seconds. KVPN installs no login item and changes no power settings.

## Process control

Operation and supervisor locks prevent conflicting actions. Before signaling a tunnel process, the runtime checks its PID, start time, root UID, and exact command. It does not terminate unmanaged OpenConnect processes.

If disconnect is requested during authentication, KVPN requests cancellation. The command may report a busy operation until the current authentication step returns; disconnect can then be retried.

Connection status reports process and interface evidence. It does not prove that a particular internal host is reachable. Session expiry values are estimates, not authoritative server deadlines.

## Storage

| Data | Location or behavior |
|---|---|
| KAIST password on macOS | Opt-in Keychain entry under service `kvpn` |
| Account name and realm | `${XDG_CONFIG_HOME:-~/.config}/kvpn/config.json` |
| Password without Keychain | The same configuration file, in plaintext after opt-in |
| Runtime files | `~/Library/Application Support/kvpn/`; directory mode 0700, managed file mode 0600 |
| Session replacement setting | Runtime `preferences.json`; `replace_existing_session` defaults to false |
| Connection log | Redacted before writing; each connection replaces the previous log |

The optional `--inspect-session` diagnostic keeps the DSID in process memory behind an owner-only UNIX socket for up to 20 minutes. It does not renew the session.

## Source layout

The Python entrypoint and modules live together. Runtime code uses the Python standard library; OpenConnect is a separate executable.

| File | Purpose |
|---|---|
| `kvpn` | Commands, authentication, and credential storage |
| `kvpn_sms.py` | Messages access and verification-code matching |
| `kvpn_auto.py` | Supervision, network waiting, and retry limits |
| `kvpn_runtime.py` | Managed processes, locks, logs, and session policy |
| `kvpn_check.py`, `kvpn_setup.py` | Local checks and setup guidance |
| `kvpn_timing.py`, `kvpn_session*.py` | Session timing and optional inspection |
| `kvpn_ui.py` | Terminal output |
| `scripts/` | Installation and release packaging |

Automatic Messages verification is macOS-only. Manual Linux connections remain experimental and have not been live-validated for this release.
