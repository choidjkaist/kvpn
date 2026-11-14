# Troubleshooting

Start with `kvpn doctor`, `kvpn status`, and `kvpn logs`. These do not submit a login or request a new SMS. Doctor checks local prerequisites and Messages file/schema access, not credential validity, actual SMS delivery, or destination reachability. `kvpn setup` explains the first-use sequence without connecting.

| Symptom | Action |
|---|---|
| Messages permission denied | Grant Full Disk Access to the actual terminal host, fully quit and reopen it. Do not reset unrelated permissions. |
| SQLite/schema error | File access already worked; inspect the database error rather than assuming Full Disk Access is missing. |
| No unique sender | Receive a normal KVPN SMS, then retry sms-check. Optionally pass an independently verified --sms-sender. |
| No fresh SMS within 120 seconds | Confirm iPhone forwarding and arrival in Mac Messages. Supervision stops; fix the cause before restarting auto. |
| Multiple fresh codes | Wait for old attempts to finish; do not repeatedly request codes. Ambiguous messages are rejected. |
| Gateway login form missing | A notice, portal change or maintenance may be involved. Do not repeatedly reset credentials; inspect the redacted terminal error. |
| Administrator authorization unavailable | Restart auto in an interactive terminal and authorize sudo. There is no passwordless privileged service. |
| Another gateway session | Use the other device to disconnect, or deliberately allow replacement with kvpn config --session-replacement allow. |
| Unmanaged VPN | Stop it through the client/terminal that created it. KVPN does not kill another client's process. |
| Disconnect reports operation in progress | Stop request has been sent; wait for the current bounded authentication operation to cancel and retry disconnect. |
| Auto off but VPN connected | Expected after auto stop or Ctrl+C. Run disconnect to end the tunnel too. |
| Different kvpn version after install | Use which -a kvpn and inspect PATH precedence. Installer does not rewrite shell configuration. |

Use `kvpn connect --sms-auto` for one automatic SMS login without supervision. You may close its terminal after successful background startup. For supervised `kvpn auto`, keep the terminal open. No process in this tool keeps the Mac awake or auto-starts it after reboot.

## Updates and removal

Stop supervision with `kvpn auto stop` before switching release versions; wait until status shows it stopped. An existing tunnel may remain connected. Install a new version and explicitly use `--replace` to switch the selected bin link. Start auto again when ready. Keep the previous release for rollback; switch back by running its install.sh with the same bin directory and --replace. Different contents under the same version are rejected.

For removal, first disconnect deliberately. Use `kvpn forget` only if you want saved credentials removed. Remove only the symlink and version directory created by this installer; it does not manage an older source checkout. Runtime diagnostics and account configuration are retained unless the owner deliberately removes them. Never share those directories in a bug report. Review even redacted logs before sharing, since network addresses and account names can still be identifying.
