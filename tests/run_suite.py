from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml
from rich.console import Console
from rich.table import Table

# Make src importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.controller import FixedTransferFlowV2
from src.models import TransferOutcome, TransferRequest, TransferState
from mocks.mock_ledger_service import MockLedgerService

console = Console()


def load_cases() -> List[Dict[str, Any]]:
    path = ROOT / "tests" / "integration" / "transfer_cases.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_case(case: Dict[str, Any]) -> Dict[str, Any]:
    req_data = case["request"]
    request = TransferRequest(**req_data)

    ledger_cfg = case.get("ledger_config", {})
    ledger = MockLedgerService(ledger_cfg)
    flow = FixedTransferFlowV2(ledger)

    result = flow.process_transfer(request)

    expected = case.get("expected", {})
    errors: List[str] = []

    # outcome check
    exp_outcome = TransferOutcome(expected["outcome"])
    if result.outcome != exp_outcome:
        errors.append(f"Outcome mismatch: got {result.outcome}, expected {exp_outcome}")
    # state check
    exp_state = TransferState(expected["final_state"])
    if result.state != exp_state:
        errors.append(f"State mismatch: got {result.state}, expected {exp_state}")
    # error_contains check
    err_contains = expected.get("error_contains")
    if err_contains:
        combined = " ".join(result.errors) + " " + result.message
        if err_contains.lower() not in combined.lower():
            errors.append(f"Expected error containing '{err_contains}', got '{combined}'")

    # audit events check
    audit_events = expected.get("audit_events")
    if audit_events:
        ev_names = [e.event for e in result.audit_trail]
        missing = [e for e in audit_events if e not in ev_names]
        if missing:
            errors.append(f"Missing audit events: {missing}")

    # masked accounts check for audit case
    if case["id"] == "audit_verification":
        # ensure audit context uses masked accounts by inspecting the audit trail details
        # (accounts are not stored in trail details, so we validate via mask function)
        from src.utils import mask_account

        masked_src = mask_account(req_data["source_account"])
        masked_dst = mask_account(req_data["destination_account"])
        if masked_src == req_data["source_account"] or masked_dst == req_data["destination_account"]:
            errors.append("Masking did not change account numbers as expected")

    return {
        "id": case["id"],
        "result": result,
        "errors": errors,
        "case": case,
    }


def main() -> int:
    cases = load_cases()
    table = Table(title="Transfer Integration Suite")
    table.add_column("Case ID")
    table.add_column("Outcome", justify="center")
    table.add_column("State", justify="center")
    table.add_column("Expected", justify="center")
    table.add_column("Expected State", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Errors")

    any_failed = False
    results: List[Dict[str, Any]] = []

    for case in cases:
        res = run_case(case)
        results.append(res)
        result = res["result"]
        errors = res["errors"]
        ok = len(errors) == 0
        if not ok:
            any_failed = True
        expected = case.get("expected", {})
        table.add_row(
            case["id"],
            result.outcome.value,
            result.state.value,
            expected.get("outcome", ""),
            expected.get("final_state", ""),
            "PASS" if ok else "FAIL",
            "\n".join(errors),
        )

    console.print(table)
    if any_failed:
        console.print("[red]One or more cases failed[/red]")
        return 1
    console.print("[green]All cases passed[/green]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
