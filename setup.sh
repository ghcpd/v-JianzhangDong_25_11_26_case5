#!/usr/bin/env bash
set -euo pipefail

# Bootstrap Python env and install dependencies
VENV_DIR=".venv"
PYTHON_BIN=${PYTHON_BIN:-python3}

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "Virtualenv ready at $VENV_DIR"
