# Security and privacy

KVPN signs in with your KAIST account and a fresh SMS or email verification code. It does not bypass multifactor authentication. OpenConnect runs with administrator privileges to create the VPN tunnel.

## Messages access

Automatic SMS verification reads the local Messages database on your Mac. The terminal running KVPN needs Full Disk Access, which grants broader access than just KAIST messages.

KVPN opens the database read-only and looks for a new verification text from the expected sender. It submits the selected code to the KAIST authentication service. It does not upload the Messages database or use the clipboard or simulated keystrokes. Messages itself retains incoming texts independently of KVPN.

If you prefer not to grant this permission, use `kvpn connect` and enter the code manually.

## Saved credentials and sessions

When you choose to save credentials on macOS, KVPN uses Keychain for the password and a local configuration file for the account name and realm. Without Keychain, opting to save credentials stores the password as plaintext in a file readable only by your user. Use `kvpn forget` to remove saved credentials; this does not disconnect an active VPN.

Session cookies are passed to OpenConnect through standard input, not command-line arguments. Logs are redacted before being written, but account names and network addresses may still identify you. Review logs before sharing them.

Automatic reconnection periodically refreshes an existing administrator authorization while it runs. It stores no Mac password and installs no passwordless sudo rule.

By default, a manual login asks before replacing another device's session, and an automatic login refuses to replace it. Setting `kvpn config --session-replacement allow` permits replacement and may disconnect the other device.

## Downloads and installation

The release archive contains an explicit list of application files. It excludes personal configuration, credentials, Messages data, runtime logs, and Git history. The installer uses the downloaded files without fetching additional code. There is no automatic updater.

The SHA-256 file checks that the archive matches the published checksum. It is not a digital signature and does not independently authenticate the publisher.

## Reporting a security issue

Do not post passwords, verification codes, session cookies, Messages databases, or raw HTTP captures in public issues. If you find a vulnerability, arrange a private reporting channel with the maintainer before sending sensitive details. The project does not currently list a dedicated security contact.
