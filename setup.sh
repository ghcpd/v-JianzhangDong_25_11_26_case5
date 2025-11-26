#!/bin/bash
# Environment Setup Script for Fixed_Transfer_Flow_v2
# Prepares development and testing environment

set -e  # Exit on error

echo "================================================================================"
echo "Setup: Fixed_Transfer_Flow_v2 Transfer Module"
echo "================================================================================"
echo ""

# Check Python version
echo "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed."
    echo "Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Found Python $PYTHON_VERSION"

# Check Python version is 3.8+
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo "Error: Python 3.8 or higher is required (found $PYTHON_VERSION)"
    exit 1
fi

echo "✓ Python version OK"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists. Removing..."
    rm -rf venv
fi

python3 -m venv venv
echo "✓ Virtual environment created"
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1
echo "✓ pip upgraded"
echo ""

# Install dependencies
echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✓ Dependencies installed successfully"
else
    echo "✗ Failed to install dependencies"
    exit 1
fi
echo ""

# Create necessary directories
echo "Creating project directories..."
mkdir -p logs
mkdir -p tests/integration
mkdir -p scripts
echo "✓ Directories created"
echo ""

# Verify installation
echo "Verifying installation..."
python3 -c "
import sys
import yaml
import pythonjsonlogger
print('✓ All required packages available')
"

if [ $? -ne 0 ]; then
    echo "✗ Package verification failed"
    exit 1
fi
echo ""

# Set permissions for scripts
echo "Setting script permissions..."
chmod +x scripts/run_transfer_suite.sh
chmod +x run_tests.sh
echo "✓ Script permissions set"
echo ""

# Display completion message
echo "================================================================================"
echo "Setup Complete!"
echo "================================================================================"
echo ""
echo "Environment is ready for development and testing."
echo ""
echo "Quick Start:"
echo "  1. Activate the virtual environment:"
echo "     source venv/bin/activate"
echo ""
echo "  2. Run the test suite:"
echo "     ./run_tests.sh"
echo "     or"
echo "     python3 tests/run_suite.py"
echo ""
echo "  3. Review the documentation:"
echo "     - docs/root_cause_analysis.md"
echo "     - docs/remediation_plan.md"
echo ""
echo "  4. Check test definitions:"
echo "     - tests/integration/transfer_cases.yaml"
echo ""
echo "  5. Review audit log schema:"
echo "     - logs/audit_schema.json"
echo ""
echo "================================================================================"

# Deactivate virtual environment
deactivate

exit 0
