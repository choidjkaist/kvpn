# KVPN

An unofficial KAIST VPN CLI, with automatic SMS verification and recovery on macOS. Version **0.4.0rc2** is a release candidate of the existing local implementation, not an official KAIST client.

## Platform scope

macOS is the primary environment. Automatic verification reads SMS forwarded from an iPhone to local macOS Messages; it never uses clipboard or simulated keystrokes. Linux manual SMS/email login is experimental and has not undergone live gateway validation for this release. Windows/WSL is not supported.

Requirements: Python 3.9+, OpenConnect and sudo authorization. On macOS with Homebrew installed:

```sh
brew install python openconnect
shasum -a 256 -c kvpn-0.4.0rc2.tar.gz.sha256
tar -xzf kvpn-0.4.0rc2.tar.gz
cd kvpn-0.4.0rc2
./install.sh
```

The installer copies only bundled files into `~/.local/share/kvpn/releases/0.4.0rc2` and links `~/.local/bin/kvpn`. It never downloads upstream, pulls Git, changes credentials, starts VPN, or installs login items. Add `~/.local/bin` ahead of other kvpn locations in PATH if required. `which -a kvpn` diagnoses shadowed installations. Use `--prefix PATH --bin-dir PATH` for custom locations. Existing symlinks require `--replace` to switch; regular files and differing same-version payloads are never overwritten. Checksums detect changed bytes, not publisher identity.

## First use

1. Run `kvpn setup` for local checks and guidance; it does not log in or request SMS.
2. Run `kvpn connect`, authenticate with your own account and choose Keychain storage if using automation.
3. Enable iPhone SMS forwarding and verify KVPN messages arrive on this Mac.
4. Grant Full Disk Access to the actual terminal app, then fully quit and reopen it. Authorization does not transfer between terminal apps.
5. After a normal KVPN SMS login, run `kvpn sms-check`. It checks local access and sender discovery without sending SMS. If discovery is ambiguous, pass an independently verified `--sms-sender`.
6. Run `kvpn auto`, authorize sudo if needed and keep that terminal open. An already managed tunnel is preserved.

Never distribute account configuration, Messages databases, runtime state or credentials to another user.

## Commands

| Command | Behavior |
|---|---|
| `kvpn`, `kvpn auto`, `kvpn auto start` | SMS verification and automatic recovery |
| `kvpn connect` | One connection with manual OTP |
| `kvpn connect --sms-auto` | One connection with automatic SMS, no supervision |
| `kvpn auto stop` | Stop supervision; retain VPN |
| `kvpn disconnect` | Stop supervision and managed VPN |
| `kvpn status`, `kvpn auto status` | Connection and recovery evidence |
| `kvpn doctor` | Local prerequisite checks, no login or network probe |
| `kvpn logs` | Sanitized latest connection log |
| `kvpn config` | Session replacement policy |
| `kvpn forget` | Delete saved credentials, not the current tunnel |
| `kvpn --help-all` | Advanced options |

Legacy aliases remain: `on`, `off`, `check`, `log`, `auto-stop`, `--forget`. JSON output is available for status, doctor/check and config. Ordinary connect detaches the tunnel; its terminal can close after success. `connect --foreground` ends the VPN with Ctrl+C. In auto mode Ctrl+C stops supervision only; use disconnect to end both.

By default a manual login asks before replacing another device's gateway session; automatic login stops instead. To explicitly allow takeover: `kvpn config --session-replacement allow`. Restore the default with `kvpn config --session-replacement ask`. Existing preferences are preserved.

## Recovery limits

OpenConnect first retries the transport using the existing session (300 seconds by default, adjustable with `--reconnect-timeout`). After process exit the supervisor waits 10 seconds and performs fresh SMS authentication. This does not extend a session indefinitely. New message row/time, exact sender, KAIST authentication context and a unique six-digit code must match. SMS wait is 120 seconds; authentication failures stop supervision. At most three login attempts per hour are allowed within one supervisor run; restarting resets this in-memory counter.

The foreground supervisor refreshes existing sudo authorization every 60 seconds. It stores no Mac password and installs no NOPASSWD rule. It does not run at login or survive reboot automatically. Sleep can interrupt networking; fresh login can interrupt SSH. Process/interface status is not a destination reachability test. Expiry is estimated, not an absolute server expiry.

See [architecture](docs/architecture.md), [troubleshooting](docs/troubleshooting.md), [security](SECURITY.md), and [changes](CHANGELOG.md). From the development checkout, run `python3 -m unittest discover -s tests -v` and `python3 scripts/build_release.py --output PATH`. Automated tests use synthetic credentials and fake privileged/network boundaries, not real authentication. The runtime bundle intentionally excludes development experiments, test fixtures, Git metadata and personal runtime/configuration files.

Based on [predict-woo/kaist-openconnect](https://github.com/predict-woo/kaist-openconnect), upstream revision `e52efaea3de7`. Do not update this modified distribution with the upstream installer. OpenConnect handles the actual tunnel. Not affiliated with KAIST, Ivanti or AirCUVE. Use your own account under your institution's terms. Original MIT license and copyright are retained.
