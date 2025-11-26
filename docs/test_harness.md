# Transfer Test Harness

This harness runs the five integration scenarios for `Fixed_Transfer_Flow_v2` and reports pass/fail for each case.

Run with:

```bash
bash scripts/setup.sh
bash scripts/run_transfer_suite.sh
```

Expected output:

- Prints PASS/FAIL per test case e.g. "normal_success: PASS" followed by a final summary and exit code.
- Exit code of the script is 0 if all pass, non-zero otherwise.

Metrics captured:

- Final ledger balances for `from` and `to` accounts per case
- Transaction `state` including `history` final state
- Audit logs captured to confirm presence of critical events like `transfer.debit_committed` and `transfer.credit_committed`

Logs are emitted in JSON format to stdout using `python-json-logger` formatting. Real systems should route those lines to a central log aggregation system.
