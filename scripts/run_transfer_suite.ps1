Param([string]$Python = "python")
Write-Output "Running transfer suite via $Python"
& $Python -m tests.run_suite
