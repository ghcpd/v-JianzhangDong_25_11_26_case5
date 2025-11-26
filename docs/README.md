# Fixed_Transfer_Flow_v2 — Analysis and Tests

To execute the test suite:

1. Run `./setup.sh` to create a virtual environment and install requirements (on UNIX-like systems). On Windows, create a venv and pip install -r requirements.txt.
2. Run `./scripts/run_transfer_suite.sh` to run the YAML-defined cases.
3. Or run `pytest` to run the wrapper test that validates the entire suite.

Files of interest:
- `src/transfer_service.py` - core service and state machine
- `mocks/mock_ledger_service.py` - ledger simulator with configurable failure sequences
- `tests/integration/transfer_cases.yaml` - the five repeatable integration test cases
- `tests/run_suite.py` - the harness that executes the YAML cases
