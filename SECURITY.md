# Security and privacy

KVPN uses the user's normal KAIST password and a fresh SMS/email verification code; it does not bypass multifactor authentication. Treat the Mac account, Keychain, terminal Full Disk Access and local Messages database as sensitive.

Full Disk Access is a broad macOS permission, not permission limited to KAIST messages. KVPN queries incoming message metadata/text to identify verification codes; it does not upload the message database. Only the selected OTP is submitted to the KAIST authentication flow. No clipboard or simulated keystrokes are used.

Passwords stored without macOS Keychain are plaintext in a user-only file after explicit opt-in. Runtime logs are redacted, and session cookies are passed through stdin rather than argv. No NOPASSWD policy is installed. Automatic recovery refreshes an existing terminal sudo authorization while running.

Session replacement defaults to confirmation in manual mode and refusal in automatic mode. An explicit allow policy can disconnect another device using the same account. Never transfer that personal decision, saved credentials or runtime files in a distribution bundle.

The release archive is built from an explicit file allowlist and ships no personal config, Messages database, runtime state, logs or Git history. SHA-256 checksums detect corruption; they are not a signed release identity. There is no auto-updater or remote install script execution.

Do not post passwords, OTPs, cookies, raw HTTP captures, message databases or unreviewed logs in public issues. No dedicated security reporting address has been established for this local release candidate; arrange a private channel with the distributor before sharing security details.
