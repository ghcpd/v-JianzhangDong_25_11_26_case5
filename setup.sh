#!/usr/bin/env bash
set -euo pipefail
echo "Creating virtualenv venv (if missing) and installing dependencies..."
python -m venv .venv || true
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Setup complete. Activate with: source .venv/bin/activate"
