#!/bin/sh
# Install only the adjacent reviewed release. Never fetch or update upstream.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
    echo 'Python 3.9+ is required. On macOS: brew install python openconnect' >&2
    exit 1
fi
exec python3 "$script_dir/scripts/install.py" "$@"
