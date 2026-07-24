#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:$PYTHONPATH"
python3 scripts/seed.py
