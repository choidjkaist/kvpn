# Development

Use Python 3.9 or later on macOS. The entrypoint imports `kvpn_*.py` from the same directory; keep these files together when running from source.

## Run the tests

From the repository root:

```sh
python3 -m unittest discover -s tests -v
sh -n install.sh
```

Tests cover authentication with synthetic responses, SMS matching, process identity, locks, tunnel detachment, cookie redaction, gateway notices, installation, and reproducible archives. Privileged and network operations use test doubles. These tests do not need real credentials, verification texts, sudo authorization, or VPN routes.

The GitHub Actions workflow runs the test suite on macOS. A passing unit test does not establish that a live gateway login, sleep/wake recovery, or another user's setup works.

## Build a release archive

```sh
python3 scripts/build_release.py --output /tmp/kvpn-release
```

The output contains a versioned `.tar.gz` archive and its SHA-256 file. `scripts/release_manifest.py` lists the files included in the archive. Tests, experiments, Git metadata, cached bytecode, and personal runtime files are excluded.

Build into an empty output directory when checking reproducibility. The builder refuses to replace an existing archive with different bytes. The installer also rejects different files under an already installed version. Publish changed bundles under a new version; do not replace an existing release asset with a rebuilt archive.

## Check installation in isolation

Extract the archive to a temporary directory and run its installer with disposable destinations:

```sh
./install.sh --prefix /tmp/kvpn-install-test/releases --bin-dir /tmp/kvpn-install-test/bin
/tmp/kvpn-install-test/bin/kvpn --version
/tmp/kvpn-install-test/bin/kvpn --help
```

Use unused paths for each check. Verify that the installed command still works after removing the extraction directory, and remove the temporary test directories afterward. Do not change a working user's executable link or connection for an installer test.

## Live testing

A live test uses a real KAIST account and may send verification texts or replace a session if the account policy permits it. Record the OS, KVPN version, forwarding setup, and observed result without credentials or codes. Test manual login, automatic SMS login, and recovery separately.

For 0.4.0rc2, 80 tests passed locally on Python 3.9 for the public source snapshot. Earlier rc1 testing also passed on Python 3.14. The maintainer has used automatic reconnection on a Mac, but the release has not been live-validated on another user's machine. Manual Linux support remains experimental.
