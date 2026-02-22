#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POC_DIR="$ROOT_DIR/poc/agent-skill-router"

cd "$POC_DIR"
python3 -m pip install -r requirements.txt >/dev/null
exec python3 demo.py "$@"
