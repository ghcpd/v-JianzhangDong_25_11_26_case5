#!/bin/bash
set -euo pipefail
PYTHON=${PYTHON:-python}
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "Running transfer suite from ${ROOT_DIR}"
${PYTHON} -m tests.run_suite
