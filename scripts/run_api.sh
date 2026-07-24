#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:$PYTHONPATH"
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
