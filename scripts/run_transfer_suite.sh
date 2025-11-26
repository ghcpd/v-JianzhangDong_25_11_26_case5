#!/usr/bin/env bash
set -euo pipefail

# Single-command runner for the transfer integration suite.
# Usage: bash scripts/run_transfer_suite.sh
# Output: Rich table with case id, outcome, state, expected, pass/fail.

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}

cd "$ROOT_DIR"

# Run the integration suite
"$PYTHON_BIN" -m tests.run_suite "$@"
