#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH=.

echo "=== Running Supervisor Gate (pre-push) ==="
python3 scripts/supervisor_gate.py --mode=dev

echo "=== Gate Passed ==="
