#!/usr/bin/env bash
set -euo pipefail

# Wrapper to execute the transfer integration suite
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
"$SCRIPT_DIR/scripts/run_transfer_suite.sh" "$@"
