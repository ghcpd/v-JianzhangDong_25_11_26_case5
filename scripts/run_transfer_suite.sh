#!/bin/bash
# Transfer Test Suite Runner
# Single-command execution of all transfer integration tests

set -e  # Exit on error

echo "================================================================================"
echo "Transfer Test Suite - Fixed_Transfer_Flow_v2"
echo "================================================================================"
echo ""

# Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

echo "Python version:"
python3 --version
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found. Please run setup.sh first."
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Verify dependencies
echo "Verifying dependencies..."
python3 -c "import yaml; import pythonjsonlogger" 2>/dev/null || {
    echo "Error: Dependencies not installed. Please run setup.sh first."
    exit 1
}

# Set Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

echo "================================================================================"
echo "Running Integration Tests"
echo "================================================================================"
echo ""

# Run test suite
python3 tests/run_suite.py

TEST_EXIT_CODE=$?

echo ""
echo "================================================================================"
echo "Test Execution Complete"
echo "================================================================================"
echo ""

# Check results
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✓ All tests passed!"
    echo ""
    echo "Reports generated:"
    echo "  - test_results.json (JSON format)"
    echo ""
    echo "Next steps:"
    echo "  - Review test results in test_results.json"
    echo "  - Check logs/ directory for audit logs"
    echo "  - Verify all test cases meet success criteria"
else
    echo "✗ Some tests failed"
    echo ""
    echo "Troubleshooting:"
    echo "  - Review test_results.json for failure details"
    echo "  - Check individual test error messages above"
    echo "  - Verify mock ledger configuration"
    echo ""
    exit 1
fi

# Deactivate virtual environment
deactivate

exit 0
