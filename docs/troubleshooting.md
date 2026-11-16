# Troubleshooting

Start with:

```sh
kvpn doctor
kvpn status
kvpn logs
```

These commands do not sign in or request a verification text. `doctor` checks local prerequisites and Messages access. It cannot confirm your password, SMS delivery, or access to a remote host.

## Automatic SMS verification

**Messages access is denied.** Enable Full Disk Access for the terminal app that actually runs KVPN, then fully quit and reopen that app. Permission granted to one terminal app does not apply to another.

**No unique sender is found.** Complete an SMS login with `kvpn connect`, confirm the text appears in Mac Messages, and retry `kvpn sms-check`. If discovery is still ambiguous, use `kvpn sms-check --sms-sender 'VERIFIED_SENDER'`, replacing the placeholder with the exact sender you verified in Messages. This option is not saved. If discovery remains ambiguous, pass it on every automatic connection, for example `kvpn auto --sms-sender 'VERIFIED_SENDER'` or `kvpn connect --sms-auto --sms-sender 'VERIFIED_SENDER'`.

**No fresh code arrives within 120 seconds.** Check iPhone SMS forwarding and whether the new text appears on the Mac. Automatic reconnection stops after this failure. Fix delivery before restarting `kvpn auto`.

**Several fresh codes are found.** Let previous login attempts finish before starting another. KVPN rejects ambiguous messages rather than guessing which code to submit.

**A database or schema error appears.** If the error concerns SQLite or the database schema, file access may already be working. Check the reported error before changing permissions.

**The Messages database is missing.** Open Messages on this Mac and complete its setup. Confirm that a forwarded KAIST verification text arrives, then retry `kvpn sms-check`.

## Connecting and reconnecting

**“Could not find the Ivanti login form.”** The gateway may be unavailable, showing a notice, or using a changed login page. Check the terminal error and whether the KAIST VPN sign-in page is reachable in your browser. Repeatedly deleting saved credentials will not repair a changed or unavailable page.

**Your KAIST password has changed.** Run `kvpn disconnect`, then `kvpn forget`, then `kvpn connect` and save the new credentials when prompted. Start `kvpn auto` again afterward. The disconnect step interrupts your current VPN connection.

**OpenConnect fails to start.** Run `kvpn doctor` to check the executable and `kvpn logs` for the connection error. Resolve the reported cause before restarting `kvpn auto`; startup failures stop automatic reconnection.

**Administrator authorization is unavailable.** Start `kvpn auto` in an interactive terminal and authorize sudo when prompted. KVPN does not install a passwordless service.

**Auto is stopped, but the VPN is connected.** This is expected after Ctrl+C or `kvpn auto stop`. Run `kvpn disconnect` to end the connection too.

**Disconnect reports an operation in progress.** KVPN has requested cancellation. Wait for the current authentication step to return, then retry `kvpn disconnect`.

**An unmanaged OpenConnect process is detected.** Stop it in the client or terminal that created it. KVPN does not terminate that process. This check does not detect every other VPN application.

**The Mac slept or restarted.** KVPN does not prevent sleep or start at login. Sleep can interrupt networking; after a reboot, start `kvpn auto` again. A new VPN connection may not preserve an existing SSH session.

For one automatic SMS login without ongoing reconnection, use `kvpn connect --sms-auto`. Its terminal can close after successful background startup. For `kvpn auto`, keep the terminal open.

## Using more than one device

By default, manual login asks before replacing another gateway session, and automatic login stops. You can disconnect the other device first.

If you want this Mac to replace the other session automatically:

```sh
kvpn config --session-replacement allow
```

This may disconnect the other device. Restore the default with:

```sh
kvpn config --session-replacement ask
```

## Updates and installation conflicts

**`kvpn` is not found.** Add `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc` if you use the default macOS shell, then open a new terminal. To check the installation directly, run `~/.local/bin/kvpn --version`.

**The version is not the one you installed.** Run `which -a kvpn` to see which executable your shell selects. Put `~/.local/bin` before other KVPN locations in PATH. The installer does not edit shell settings.

**An existing link prevents installation.** The installer preserves existing links unless you pass `./install.sh --replace`. It never overwrites a regular file. Confirm which installation the link points to before replacing it.

To update, run `kvpn auto stop` and wait until `kvpn status` reports that automatic reconnection has stopped. The VPN may remain connected. Download and extract the new release, verify its checksum, then run `./install.sh --replace` from the extracted folder. Start `kvpn auto` again when ready.

Keep the previous release if you want to roll back. Run its `install.sh --replace` with the same bin directory to select it again. For custom locations, use `--prefix PATH --bin-dir PATH` consistently. Different files cannot be installed over an existing version; use an unchanged published archive or a separate prefix.

## Remove KVPN

1. Run `kvpn disconnect` to stop the connection and automatic reconnection.
2. Run `kvpn forget` if you also want saved credentials removed.
3. Remove the installer-created `~/.local/bin/kvpn` symlink and the KVPN version directories you no longer need under `~/.local/share/kvpn/releases/`. If you used custom locations, remove those instead.

Account configuration and runtime diagnostics are separate from the installed application. Their locations are listed in [How KVPN works](architecture.md#storage). They are retained unless you remove them. Do not include these directories in a bug report; review even redacted logs before sharing them.
