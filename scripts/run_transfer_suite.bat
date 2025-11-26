@echo off
REM Transfer Test Suite Runner (Windows)
REM Single-command execution of all transfer integration tests

setlocal EnableDelayedExpansion

echo ================================================================================
echo Transfer Test Suite - Fixed_Transfer_Flow_v2
echo ================================================================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed
    exit /b 1
)

echo Python version:
python --version
echo.

REM Check if virtual environment exists
if not exist venv (
    echo Error: Virtual environment not found. Please run setup.bat first.
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Verify dependencies
echo Verifying dependencies...
python -c "import yaml; import pythonjsonlogger" >nul 2>&1
if errorlevel 1 (
    echo Error: Dependencies not installed. Please run setup.bat first.
    exit /b 1
)

REM Set Python path
set PYTHONPATH=%PYTHONPATH%;%CD%

echo ================================================================================
echo Running Integration Tests
echo ================================================================================
echo.

REM Run test suite
python tests\run_suite.py

set TEST_EXIT_CODE=%ERRORLEVEL%

echo.
echo ================================================================================
echo Test Execution Complete
echo ================================================================================
echo.

REM Check results
if %TEST_EXIT_CODE% EQU 0 (
    echo � All tests passed!
    echo.
    echo Reports generated:
    echo   - test_results.json ^(JSON format^)
    echo.
    echo Next steps:
    echo   - Review test results in test_results.json
    echo   - Check logs\ directory for audit logs
    echo   - Verify all test cases meet success criteria
) else (
    echo � Some tests failed
    echo.
    echo Troubleshooting:
    echo   - Review test_results.json for failure details
    echo   - Check individual test error messages above
    echo   - Verify mock ledger configuration
    echo.
    call venv\Scripts\deactivate.bat
    exit /b 1
)

REM Deactivate virtual environment
call venv\Scripts\deactivate.bat

exit /b 0
