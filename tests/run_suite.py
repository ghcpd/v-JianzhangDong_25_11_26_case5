import yaml
import os
import sys

# Ensure repo root is on sys.path so 'mocks' and 'src' can be imported when running directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import logging
import sys
import time

from mocks.mock_ledger_service import MockLedgerService
from src.transfer_service import get_transfer_service_for_tests

LOG = logging.getLogger("test_runner")
logging.basicConfig(level=logging.INFO)


def run_case(case_def):
    name = case_def['name']
    scenario = case_def.get('scenario', {})
    expected = case_def.get('expect', {})

    LOG.info("Running case: %s scenario=%s", name, scenario)

    mock = MockLedgerService(scenario_map={'*': scenario})
    service = get_transfer_service_for_tests(mock)

    # Use fixed account names and deterministic behavior
    tx = service.initiate_transfer('acct-A', 'acct-B', 100.0)

    final_state = tx.state.value
    ok = True
    reasons = []

    if final_state != expected.get('final_state'):
        ok = False
        reasons.append(f"expected final_state {expected.get('final_state')} got {final_state}")

    if 'failure_contains' in expected and (tx.failure_reason or ''):
        if expected['failure_contains'] not in tx.failure_reason:
            ok = False
            reasons.append(f"failure reason does not contain expected token '{expected['failure_contains']}' actual='{tx.failure_reason}'")

    verify_audit = expected.get('verify_audit', False)
    if verify_audit:
        # audit can be part of events; ensure tx_id present in events and in logs
        found = any(str(tx.tx_id) in str(ev) for ev in tx.events)
        if not found:
            ok = False
            reasons.append('audit missing tx_id in events')

    return ok, reasons, tx


def main():
    with open('tests/integration/transfer_cases.yaml', 'r') as fh:
        cases = yaml.safe_load(fh)

    results = []
    for c in cases:
        ok, reasons, tx = run_case(c)
        results.append({'name': c['name'], 'ok': ok, 'reasons': reasons, 'tx_id': tx.tx_id, 'state': tx.state.value})

    # Print a compact report and exit code
    all_ok = all(r['ok'] for r in results)
    print('\n--- Transfer Suite Results ---')
    for r in results:
        status = 'PASS' if r['ok'] else 'FAIL'
        print(f"{status}: {r['name']} tx={r['tx_id']} state={r['state']} reasons={r['reasons']}")

    print('--- metrics ---')
    print(f"total={len(results)} passed={sum(1 for r in results if r['ok'])} failed={sum(1 for r in results if not r['ok'])}")

    sys.exit(0 if all_ok else 2)


if __name__ == '__main__':
    main()
