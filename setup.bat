@echo off
REM Environment Setup Script for Fixed_Transfer_Flow_v2 (Windows)
REM Prepares development and testing environment

echo ================================================================================
echo Setup: Fixed_Transfer_Flow_v2 Transfer Module
echo ================================================================================
echo.

REM Check Python installation
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python 3.8 or higher from https://www.python.org/
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Found Python %PYTHON_VERSION%
echo � Python version OK
echo.

REM Create virtual environment
echo Creating virtual environment...
if exist venv (
    echo Virtual environment already exists. Removing...
    rmdir /s /q venv
)

python -m venv venv
if errorlevel 1 (
    echo Error: Failed to create virtual environment
    exit /b 1
)
echo � Virtual environment created
echo.

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1
echo � pip upgraded
echo.

REM Install dependencies
echo Installing dependencies from requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo � Failed to install dependencies
    exit /b 1
)
echo � Dependencies installed successfully
echo.

REM Create necessary directories
echo Creating project directories...
if not exist logs mkdir logs
if not exist tests\integration mkdir tests\integration
if not exist scripts mkdir scripts
echo � Directories created
echo.

REM Verify installation
echo Verifying installation...
python -c "import yaml; import pythonjsonlogger; print('� All required packages available')"
if errorlevel 1 (
    echo � Package verification failed
    exit /b 1
)
echo.

REM Display completion message
echo ================================================================================
echo Setup Complete!
echo ================================================================================
echo.
echo Environment is ready for development and testing.
echo.
echo Quick Start:
echo   1. Activate the virtual environment:
echo      venv\Scripts\activate.bat
echo.
echo   2. Run the test suite:
echo      run_tests.bat
echo      or
echo      python tests\run_suite.py
echo.
echo   3. Review the documentation:
echo      - docs\root_cause_analysis.md
echo      - docs\remediation_plan.md
echo.
echo   4. Check test definitions:
echo      - tests\integration\transfer_cases.yaml
echo.
echo   5. Review audit log schema:
echo      - logs\audit_schema.json
echo.
echo ================================================================================

REM Deactivate virtual environment
call venv\Scripts\deactivate.bat

exit /b 0
