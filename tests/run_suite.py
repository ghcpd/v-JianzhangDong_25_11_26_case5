import os
import yaml
import logging
from pathlib import Path
from mocks.mock_ledger_service import MockLedgerService
from src.adapters.ledger_adapter import LedgerAdapter
from src.transfer_service import TransferService

logger = logging.getLogger(__name__)


def run_suite(cases_file: str):
    with open(cases_file, "r", encoding="utf-8") as fh:
        cases = yaml.safe_load(fh)

    results = []
    for case in cases:
        cid = case["id"]
        print(f"Running: {cid} - {case.get('description')}")
        initial_balances = case.get("initial_balances", {})
        behavior = case.get("behavior", {})
        from_acc = case["from"]
        to_acc = case["to"]
        amount = case["amount"]
        expected = case["expected"]

        ledger = MockLedgerService(initial_balances, {})
        adapter = LedgerAdapter(ledger)
        svc = TransferService(adapter)
        # We generate the tx_id and attach behavior to ledger before initiating to ensure per-tx config
        import uuid as _uuid
        tx_id = str(_uuid.uuid4())
        if behavior:
            ledger.behavior[tx_id] = behavior
        tx_id = svc.initiate_transfer(from_acc, to_acc, amount, sync=True, tx_id=tx_id)

        final_state = svc.get_transfer_status(tx_id)
        balances = ledger.balances
        passed = final_state == expected.get("final_state") and all(float(balances.get(a, 0)) == float(v) for a, v in expected.get("balances", {}).items())
        results.append({"id": cid, "passed": passed, "state": final_state, "balances": balances})
        # attach audit info
        results[-1]["audit_log"] = svc.audit_log
        print("  Result:", "PASS" if passed else "FAIL", "state=", final_state, "balances=", balances)
    # summary
    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"\nSummary: {passed_count}/{total} passed")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    repo_root = Path(__file__).parents[1]
    cases_file = os.path.join(repo_root, "tests", "integration", "transfer_cases.yaml")
    run_suite(cases_file)
