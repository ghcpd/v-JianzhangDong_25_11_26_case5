import argparse
import yaml
import logging
import time
import os
import sys

# Ensure top-level package importability when running tests from workspace
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(ROOT, '..')))

from mocks import mock_ledger_service
from src.adapters.ledger_adapter import LedgerAdapter
from src.transfer_manager import TransferManager
from src.logging_config import configure_logging

logger = logging.getLogger('transfer_test')


def load_yaml(spec_path):
    with open(spec_path, 'r') as f:
        return yaml.safe_load(f)


class IntegrationRunner:
    def __init__(self, ledger_client=None):
        self.ledger = ledger_client or mock_ledger_service
        self.adapter = LedgerAdapter(self.ledger)
        self.manager = TransferManager(self.adapter)

    def run_case(self, case_spec):
        # Reset ledger state and behavior hooks
        mock_ledger_service.reset()
        for acct, bal in case_spec.get('initial_balances', {}).items():
            mock_ledger_service.init_account(acct, bal)
        # set behaviors
        for op in ('debit', 'credit'):
            for txid, behavior in case_spec.get('behaviors', {}).get(op, {}).items():
                mock_ledger_service.BEHAVIOR[op][txid] = behavior

        # Initiate transfer
        tx_id = case_spec.get('tx_id')
        # attach a capture log handler per case to assert audit events
        import io
        sf = io.StringIO()
        lh = logging.StreamHandler(sf)
        logging.getLogger().addHandler(lh)
        logging.getLogger().setLevel(logging.INFO)

        res = self.manager.initiate_transfer(case_spec['from'], case_spec['to'], case_spec['amount'], tx_id=tx_id)
        # Allow small wait for eventual consistency
        time.sleep(0.1)
        final_state = self.manager.get_state(res['tx_id'])
        # read logs and tear down capture handler
        lh.flush()
        log_data = sf.getvalue()
        logging.getLogger().removeHandler(lh)

        # Compose result
        actual = {
            'status': res['status'] if 'status' in res else 'unknown',
            'ledger': {
                'from': mock_ledger_service.get_balance(case_spec['from']),
                'to': mock_ledger_service.get_balance(case_spec['to'])
            },
            'final_state': final_state,
            'logs': log_data
        }
        return actual

    def run_suite(self, spec_path):
        suite = load_yaml(spec_path)
        results = []
        for case in suite['cases']:
            name = case['name']
            res = self.run_case(case)
            expected = case['expected']
            pass_fail = res['status'] == expected['status'] and res['ledger'] == expected['ledger']
            # audit assertions
            for assert_item in case.get('audit_asserts', []):
                if assert_item not in res['logs']:
                    pass_fail = False
            logger.info('Case %s: %s', name, 'PASS' if pass_fail else 'FAIL')
            results.append({'name': name, 'actual': res, 'expected': expected, 'pass': pass_fail})
        return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', help='Path to YAML spec', default='tests/integration/transfer_cases.yaml')
    args = parser.parse_args()

    configure_logging()
    runner = IntegrationRunner()
    results = runner.run_suite(args.spec)
    for r in results:
        print(f"{r['name']}: {'PASS' if r['pass'] else 'FAIL'}")
    all_pass = all(r['pass'] for r in results)
    if not all_pass:
        raise SystemExit(1)
    print('All cases passed')
