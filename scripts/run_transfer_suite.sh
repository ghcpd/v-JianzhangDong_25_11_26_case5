#!/usr/bin/env bash
set -euo pipefail
echo "Running transfer integration suite..."
python -u tests/run_suite.py

echo "Suite finished. See printed results above. Exit code 0=all passed, 2=failures."
