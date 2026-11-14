#!/usr/bin/env python3
"""Build a deterministic allowlisted release archive and SHA-256 checksum."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tarfile
from release_manifest import RELEASE_FILES


def build(source, output):
    version = subprocess.check_output([sys.executable, str(source / 'kvpn'), '--version'], text=True).strip()
    if not version or any(c not in '0123456789abcdefghijklmnopqrstuvwxyz.-' for c in version):
        raise ValueError('Invalid version')
    root = 'kvpn-' + version
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (root + '.tar.gz')
    content = io.BytesIO()
    with gzip.GzipFile(fileobj=content, mode='wb', filename='', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w') as tar:
            for name in sorted(RELEASE_FILES):
                path = source / name
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source.resolve()):
                    raise ValueError('Unsafe or missing release file: ' + name)
                payload = path.read_bytes()
                info = tarfile.TarInfo(root + '/' + name)
                info.size = len(payload)
                info.mode = 0o755 if name in ('kvpn', 'install.sh') else 0o644
                info.mtime = 0
                tar.addfile(info, io.BytesIO(payload))
    data = content.getvalue()
    if archive.exists() and archive.read_bytes() != data:
        raise ValueError('Different archive already exists; choose a new version or output directory')
    archive.write_bytes(data)
    checksum = hashlib.sha256(data).hexdigest()
    (output / (archive.name + '.sha256')).write_text(checksum + '  ' + archive.name + '\n')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(Path(__file__).resolve().parents[1], args.output))
