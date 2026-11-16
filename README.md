# KVPN — Automatic KAIST VPN connection on macOS

Connect to KAIST VPN from your Mac and reconnect when the connection drops. KVPN reads verification codes from SMS forwarded to macOS Messages, so you do not have to copy a new code into the terminal each time.

After a one-time setup, start it with:

```sh
kvpn auto
```

Keep that terminal open while you want automatic reconnection. To stop both reconnection and the VPN, run `kvpn disconnect` in another terminal tab.

KVPN is an unofficial command-line tool built around OpenConnect. **Automatic SMS verification works on macOS and requires an iPhone forwarding SMS to the Mac.** Manual Linux connections are experimental; Windows and WSL are not supported. The current download, **0.4.0rc2**, is a prerelease.

## Install on a Mac

You need a KAIST VPN account, an iPhone that receives its verification texts, and permission to run administrator commands on your Mac.

### 1. Install the dependencies

With [Homebrew](https://brew.sh) installed:

```sh
brew install python openconnect
```

KVPN requires Python 3.9 or later.

### 2. Download KVPN

Download both files into the same folder:

- [kvpn-0.4.0rc2.tar.gz](https://github.com/choidjkaist/kvpn/releases/download/v0.4.0rc2/kvpn-0.4.0rc2.tar.gz)
- [kvpn-0.4.0rc2.tar.gz.sha256](https://github.com/choidjkaist/kvpn/releases/download/v0.4.0rc2/kvpn-0.4.0rc2.tar.gz.sha256)

If they are in Downloads, run:

```sh
cd ~/Downloads
shasum -a 256 -c kvpn-0.4.0rc2.tar.gz.sha256
```

Continue only if the result is `kvpn-0.4.0rc2.tar.gz: OK`:

```sh
tar -xzf kvpn-0.4.0rc2.tar.gz
cd kvpn-0.4.0rc2
./install.sh
export PATH="$HOME/.local/bin:$PATH"
kvpn --version
```

Run the installer as your normal user, without `sudo`. It installs KVPN under `~/.local/share/kvpn/releases/` and creates `~/.local/bin/kvpn`. It does not connect to the VPN.

The `export` command applies to the current terminal. To make it permanent in the default macOS shell, add that same line to `~/.zshrc`. If another KVPN installation is already present, see [updates and installation conflicts](docs/troubleshooting.md#updates-and-installation-conflicts).

## Set up automatic SMS verification

1. **Forward SMS to your Mac.** Enable Text Message Forwarding for this Mac in your iPhone's Messages settings. Confirm that KAIST verification texts arrive in the Mac's Messages app.
2. **Allow your terminal to read Messages.** In macOS System Settings → Privacy & Security → Full Disk Access, enable the terminal app you use for KVPN. Fully quit and reopen that app. This is a broad permission; [read what KVPN accesses](SECURITY.md#messages-access).
3. **Connect once manually.** Run `kvpn connect`, enter your KAIST credentials, select your account realm, and choose SMS verification. Enter the code, then answer `y` when asked to save your credentials in macOS Keychain so reconnection can use them later.
4. **Check SMS access.** After receiving a KAIST VPN text, run `kvpn sms-check`. This checks local Messages access and identifies the sender; it does not request another code.
5. **Start automatic reconnection.** Run `kvpn auto`, enter your Mac password if administrator authorization is requested, and leave the terminal open. If KVPN already has a managed connection, it keeps it.

Use `kvpn setup` for setup guidance or `kvpn doctor` to check local prerequisites. If you cannot use SMS forwarding or do not want to grant Messages access, use `kvpn connect` and enter the verification code yourself.

## Everyday use

| What you want to do | Command |
|---|---|
| Connect and reconnect automatically | `kvpn auto` |
| Check the connection | `kvpn status` |
| Stop the VPN and automatic reconnection | `kvpn disconnect` |
| Stop reconnection but leave the VPN connected | `kvpn auto stop` |
| Connect once and enter the code yourself | `kvpn connect` |
| Connect once with automatic SMS verification | `kvpn connect --sms-auto` |
| Check local setup | `kvpn doctor` |
| Read the latest connection log | `kvpn logs` |
| Remove saved credentials | `kvpn forget` |

**In auto mode, Ctrl+C stops reconnection but leaves the VPN connected.** Use `kvpn disconnect` to end both. A successful one-time connection runs in the background, so its terminal can close. `kvpn forget` removes saved credentials without ending an active connection.

## What happens when the connection drops?

OpenConnect first tries to recover the existing connection. If its process exits, KVPN waits for the gateway to become reachable and attempts a fresh login with a new SMS code. Authentication errors stop automatic reconnection, and attempts are limited to avoid repeated login requests.

KVPN does not keep the Mac awake or start itself after a reboot. Sleep can interrupt the VPN, and a fresh connection may interrupt an existing SSH session.

If the same account is connected on another device, automatic login stops rather than replacing that session. See [using more than one device](docs/troubleshooting.md#using-more-than-one-device) if you want to change this behavior.

## More information

- [Troubleshooting, updates, and removal](docs/troubleshooting.md)
- [Security and credential storage](SECURITY.md)
- [How authentication and recovery work](docs/architecture.md)
- [Development and testing](https://github.com/choidjkaist/kvpn/blob/main/docs/development.md)
- [Release history](CHANGELOG.md)

Based on [predict-woo/kaist-openconnect](https://github.com/predict-woo/kaist-openconnect), under the [MIT license](LICENSE). KVPN is not affiliated with KAIST, Ivanti, or AirCUVE.
