import os
import sys
import yaml
import logging
import pytest

# Ensure we can import project packages
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)

from tests.run_suite import IntegrationRunner

logger = logging.getLogger(__name__)


def load_cases():
    with open(os.path.join(ROOT, 'tests', 'integration', 'transfer_cases.yaml'), 'r') as f:
        suite = yaml.safe_load(f)
    return suite['cases']


CASES = load_cases()


@pytest.mark.parametrize('case_spec', CASES, ids=[c['name'] for c in CASES])
def test_transfer_case(case_spec):
    # Configure logging to capture JSON logs if needed
    logging.basicConfig(level=logging.INFO)
    runner = IntegrationRunner()
    res = runner.run_case(case_spec)

    expected = case_spec['expected']

    assert res['status'] == expected['status'], f"status mismatch for {case_spec['name']}: {res['status']} != {expected['status']}"
    assert res['ledger'] == expected['ledger'], f"ledger mismatch for {case_spec['name']}: {res['ledger']} != {expected['ledger']}"

    # If audit assertions are present, check for each event string in captured logs
    for audit_assert in case_spec.get('audit_asserts', []):
        assert audit_assert in res['logs'], f"audit_assert {audit_assert} not found in logs for {case_spec['name']}"
