#!/bin/bash
# Wrapper script for running the transfer test suite
# Calls scripts/run_transfer_suite.sh

set -e

echo "Transfer Test Suite Wrapper"
echo ""

# Check if setup has been run
if [ ! -d "venv" ]; then
    echo "Environment not set up. Running setup.sh..."
    ./setup.sh
    echo ""
fi

# Execute the main test suite
./scripts/run_transfer_suite.sh

exit $?
