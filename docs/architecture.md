# Architecture

The `kvpn` entrypoint remains next to its `kvpn_*.py` modules to preserve existing symlink installations. Python standard library only; OpenConnect is an external executable.

| Component | Responsibility |
|---|---|
| `kvpn` | CLI dispatch, Ivanti/AirCUVE HTTPS authentication, opt-in credentials |
| `kvpn_sms.py` | Read-only local Messages access, fresh sender-bound OTP matching |
| `kvpn_auto.py` | Foreground supervisor, network waiting, retry budget, stop requests |
| `kvpn_runtime.py` | Process identity, locks, detached tunnel, sanitized logs, policy |
| `kvpn_check.py`, `kvpn_setup.py` | Non-authenticating local checks and first-use guidance |
| `kvpn_timing.py`, `kvpn_session*.py` | Allowlisted session timing and optional read-only inspection |
| `kvpn_ui.py` | Terminal presentation |
| `scripts/` | Offline installation and deterministic release packaging |

## Authentication and recovery

The client obtains an Ivanti sign-in session, prepares the AirCUVE portal, requests SMS/email verification, submits the OTP, and exchanges the portal result for an Ivanti DSID. OpenConnect receives this cookie through standard input using the NC protocol. No cookie is put in process arguments.

The automatic path uses saved account credentials and reads new incoming messages from `~/Library/Messages/chat.db` in SQLite read-only/query-only mode. It requires a new row ID, a request-time cutoff, an exact sender, authentication context, and one unambiguous six-digit code. Sender discovery considers up to 200 recent incoming messages within 30 days and requires KVPN-specific context. SMS delivery and the database schema depend on Apple's Messages implementation.

The tunnel and supervisor have different lifetimes. The tunnel detaches; the supervisor stays attached to its terminal. Transport retries belong to OpenConnect. Only process exit triggers fresh authentication, after a 10-second delay and a gateway TCP availability check. The check proves TCP reachability only, not portal health. Authentication errors stop instead of repeatedly sending SMS. A three-attempt rolling-hour limit exists in supervisor memory; it is not persistent across restarts.

Operation and supervisor locks serialize control. Before signaling a process, the runtime checks PID, start time, root UID and exact command. Unmanaged OpenConnect instances are never terminated. Disconnect during an ongoing authentication operation can report a busy lock; cancellation is requested first and the user can retry after the bounded operation returns.

## Storage

- macOS password: opt-in Keychain service `kvpn`.
- ID/realm: `${XDG_CONFIG_HOME:-~/.config}/kvpn/config.json`.
- Without Keychain: opting into credential storage keeps the password in that user-only plaintext file; do not describe this as encrypted storage.
- Runtime: `~/Library/Application Support/kvpn/`, mode 0700; managed files mode 0600. Existing path retained for compatibility.
- Session policy: runtime `preferences.json`, boolean `replace_existing_session`; absent/false means no unattended takeover.
- Logs are sanitized before disk writes. The latest connection replaces the previous log. Passwords, OTPs and DSID are not deliberately persisted by runtime logging; Messages itself retains incoming SMS independently.
- Optional `--inspect-session` keeps DSID in process memory behind an owner-only UNIX socket for up to 20 minutes. It is a diagnostic, not a renewal service.

No launch agent, GUI automation, clipboard dependency or power policy is installed. Linux manual connection remains experimental; the macOS lifecycle and Messages integration must not be advertised as portable without testing.
