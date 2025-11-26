@echo off
REM Wrapper script for running the transfer test suite (Windows)
REM Calls scripts\run_transfer_suite.bat

echo Transfer Test Suite Wrapper
echo.

REM Check if setup has been run
if not exist venv (
    echo Environment not set up. Running setup.bat...
    call setup.bat
    if errorlevel 1 (
        echo Setup failed. Exiting.
        exit /b 1
    )
    echo.
)

REM Execute the main test suite
call scripts\run_transfer_suite.bat

exit /b %ERRORLEVEL%
