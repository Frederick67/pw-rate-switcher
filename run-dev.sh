#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PW_RATE_SWITCHER_DEV=1
export PW_RATE_SWITCHER_DISABLE_TRAY=1

cd "$SCRIPT_DIR"
exec python3 pw-rate-switcher.py "$@"