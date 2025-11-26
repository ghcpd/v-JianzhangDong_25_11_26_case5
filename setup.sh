#!/bin/bash
set -e
echo "Setting up virtualenv and installing requirements"
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "Setup completed"
