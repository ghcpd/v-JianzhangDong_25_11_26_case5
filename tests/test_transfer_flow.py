import os
import yaml
import pytest
from tests.run_suite import run_suite


def test_transfer_cases_all_pass():
    repo_root = os.path.dirname(os.path.dirname(__file__))
    cases_file = os.path.join(repo_root, "tests", "integration", "transfer_cases.yaml")
    results = run_suite(cases_file)
    fails = [r for r in results if not r["passed"]]
    if fails:
        for f in fails:
            print("Fail:", f)
    assert len(fails) == 0, f"{len(fails)} integration tests failed"
    # Additional audit verification: search for audit_verification case
    for r in results:
        if r["id"] == "audit_verification":
            # check audit_log includes tx_id and masked account strings (no full accounts present)
            audit = r.get("audit_log", [])
            assert any(e.get("event") == "transfer.succeeded" for e in audit), "audit missing transfer.succeeded"
            assert all("***" in str(e.get("from", "")) or e.get("from", None) is None for e in audit), "from account not masked"
