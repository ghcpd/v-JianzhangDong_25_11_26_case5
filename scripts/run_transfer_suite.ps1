param([string]$Spec = "tests/integration/transfer_cases.yaml")
python -u tests/run_suite.py --spec $Spec
