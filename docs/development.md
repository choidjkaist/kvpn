# Development and release validation

Use Python 3.9+ on macOS. Runtime modules stay beside the entrypoint to retain existing symlink and in-memory process compatibility. Do not refactor authentication protocols while changing packaging.

Run `python3 -m unittest discover -s tests -v`. Existing tests cover synthetic authentication, fresh SMS matching, process identity, locks, native fork/detachment with fake privileged executables, cookie redaction and gateway notice parsing. Release tests add installation isolation, aliases, platform rejection and archive reproducibility. No real OTP, saved credentials, sudo authorization or VPN routes are needed.

Build with `python3 scripts/build_release.py --output PATH`. The explicit manifest excludes experiments, personal routing diagnostics, local history, Git metadata, cached bytecode and runtime data. Runtime archives contain operational documentation and installer code; development tests and CI remain in the source checkout. A same-version archive with different bytes is rejected.

Before publishing, verify both the release archive and checksum, install into a disposable prefix/bin directory and execute version/help there. Do not replace an owner's current executable link merely to smoke-test installation. A live test requires a separate, deliberate authentication on a suitable account; record OS, version, forwarding prerequisites and observed outcome without secrets.

CI definitions run mocked tests on macOS, not live VPN connections. A workflow file is configuration, not evidence that GitHub CI has run. Linux support remains experimental. Do not ship current account configuration or enable session replacement by default.
