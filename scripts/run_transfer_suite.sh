#!/usr/bin/env bash
set -euo pipefail
python -u tests/run_suite.py --spec tests/integration/transfer_cases.yaml
