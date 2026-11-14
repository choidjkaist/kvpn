#!/usr/bin/env python3
"""Install an immutable, per-user release without changing VPN state."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from release_manifest import RELEASE_FILES


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(source, prefix, bin_dir, replace=False):
    # Resolve before changing anything; fail for incomplete or linked bundles.
    for name in RELEASE_FILES:
        p = source / name
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(source.resolve()):
            raise ValueError('Missing or unsafe release file: ' + name)
    version = subprocess.check_output([sys.executable, str(source / 'kvpn'), '--version'], text=True).strip()
    if not version or any(c not in '0123456789abcdefghijklmnopqrstuvwxyz.-' for c in version):
        raise ValueError('Invalid release version')
    target = prefix / version
    link = bin_dir / 'kvpn'
    if link.exists() or link.is_symlink():
        if not link.is_symlink():
            raise ValueError('Refusing to replace a regular file: ' + str(link))
        if link.resolve() != (target / 'kvpn').resolve() and not replace:
            raise ValueError('Existing kvpn symlink retained. Use --replace to explicitly switch this link.')
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_dir():
            raise ValueError('Unsafe release destination')
        if any((target / n).is_symlink() or not (target / n).is_file() or digest(target / n) != digest(source / n) for n in RELEASE_FILES):
            raise ValueError('This version already has different files. Use a new version or another --prefix; nothing overwritten.')
    else:
        prefix.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='.kvpn-', dir=prefix))
        try:
            for name in RELEASE_FILES:
                dest = staging / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / name, dest)
            (staging / 'kvpn').chmod(0o755)
            (staging / 'install.sh').chmod(0o755)
            # Verify imports from the copied bundle before activation.
            subprocess.run([sys.executable, str(staging / 'kvpn'), '--version'], check=True, stdout=subprocess.DEVNULL)
            staging.rename(target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    bin_dir.mkdir(parents=True, exist_ok=True)
    # Reserve a unique sibling path and atomically publish the link.
    with tempfile.TemporaryDirectory(prefix='.kvpn-link-', dir=bin_dir) as tmp:
        temp_link = Path(tmp) / 'kvpn'
        temp_link.symlink_to(target / 'kvpn')
        os.replace(temp_link, link)
    return link


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=Path.home() / '.local/share/kvpn/releases')
    parser.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin')
    parser.add_argument('--replace', action='store_true', help='Explicitly switch an existing symlink; never replaces a regular file')
    args = parser.parse_args()
    if sys.version_info < (3, 9):
        parser.error('Python 3.9+ is required')
    if sys.platform not in ('darwin', 'linux'):
        parser.error('This release supports macOS and experimental manual Linux use only')
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        parser.error('Run this installer as your normal user, without sudo')
    source = Path(__file__).resolve().parents[1]
    try:
        link = install(source, args.prefix.expanduser().absolute(), args.bin_dir.expanduser().absolute(), args.replace)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, 'Install failed: ' + str(error) + '\n')
    print('Installed:', link)
    if not shutil.which('openconnect'):
        print('OpenConnect is missing. On macOS: brew install openconnect')
    resolved = shutil.which('kvpn')
    if resolved is None or Path(resolved).resolve() != link.resolve():
        print('PATH does not select this installation. Put', link.parent, 'before other kvpn locations in your shell PATH.')
    print('Next: run', str(link), 'setup')
    print('No VPN, credentials, login items, shell profiles or power settings were changed.')


if __name__ == '__main__':
    main()
