# Changelog

## 0.4.0rc2 — 2026-11-14

- Use English for all maintained documentation, comments and user-facing CLI text.
- Make README.md the canonical English guide; retain README.en.md as a compatibility link.
- Preserve Korean SMS matching literals and synthetic message fixtures as required input data.
- No authentication, connection or account-setting behavior changed.

## 0.4.0rc1 — 2026-11-14

- Preserve bare kvpn/auto behavior, on/off/check/log aliases, account storage and session replacement preferences.
- Add setup guidance, doctor alias, auto start/stop/status and explicit config for session replacement.
- Reject automatic Messages authentication on non-macOS before credential access or login.
- Distinguish supervised recovery from a one-shot automatic SMS connection in terminal-close guidance.
- Preserve a nonsecret supervisor stop reason and state the limits of connection-status evidence.
- Remove personal routing snapshots from ordinary disconnect; they are not required for VPN lifecycle control.
- Replace the upstream-downloading installer with offline, versioned per-user installation and explicit symlink replacement.
- Add allowlisted deterministic archives, checksums, installation/release tests and CI definition.
- Replace mixed historical README instructions with current documentation (English-only starting with rc2).

This is a release candidate. Mocked tests do not establish a new live gateway login, sleep/wake recovery, Linux interoperability or another user's first installation success. The existing owner's successful automatic use is prior operational evidence, not a new release test.

## Earlier local versions

Local additions to upstream e52efaea3de7 included managed background OpenConnect, process identity validation, session timing diagnostics, fresh SMS recognition, foreground recovery supervision and gateway notice handling. Original MIT attribution is retained in LICENSE.
