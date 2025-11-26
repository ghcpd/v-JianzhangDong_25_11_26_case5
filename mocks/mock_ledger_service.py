import time
import logging

LOG = logging.getLogger("mock_ledger")


class MockLedgerService:
    def __init__(self, scenario_map=None):
        """scenario_map: dict mapping tx_id -> dict({"debit": mode, "credit": mode})

        mode can be: 'ok', 'fail', 'retry_once', 'timeout' etc.
        if tx_id is not present, default to 'ok'.
        """
        self.scenario_map = scenario_map or {}
        # track internal state for retry_once
        self._attempts = {}

    def _get_mode(self, tx_id, kind):
        # allow wildcard '*' to apply default behavior to all tx_ids
        conf = self.scenario_map.get(tx_id, {})
        if not conf and '*' in self.scenario_map:
            conf = self.scenario_map.get('*', {})
        return conf.get(kind, 'ok')

    def post_debit(self, tx_id, from_account, amount):
        mode = self._get_mode(tx_id, 'debit')
        LOG.debug("mock post_debit tx=%s mode=%s", tx_id, mode)
        if mode == 'ok':
            return {'status': 'ok'}
        if mode == 'fail':
            return {'status': 'error', 'error': 'debit_rejected'}
        if mode == 'retry_once':
            attempts = self._attempts.get((tx_id, 'debit'), 0)
            self._attempts[(tx_id, 'debit')] = attempts + 1
            if attempts == 0:
                return {'status': 'retry'}
            return {'status': 'ok'}
        if mode == 'timeout':
            time.sleep(2)
            return {'status': 'error', 'error': 'timeout'}

        return {'status': 'error', 'error': 'unknown_mode'}

    def post_credit(self, tx_id, to_account, amount):
        mode = self._get_mode(tx_id, 'credit')
        LOG.debug("mock post_credit tx=%s mode=%s", tx_id, mode)
        if mode == 'ok':
            return {'status': 'ok'}
        if mode == 'fail':
            return {'status': 'error', 'error': 'credit_rejected'}
        if mode == 'retry_once':
            attempts = self._attempts.get((tx_id, 'credit'), 0)
            self._attempts[(tx_id, 'credit')] = attempts + 1
            if attempts == 0:
                return {'status': 'retry'}
            return {'status': 'ok'}
        if mode == 'timeout':
            time.sleep(2)
            return {'status': 'error', 'error': 'timeout'}

        return {'status': 'error', 'error': 'unknown_mode'}

    def attempt_rollback(self, tx_id):
        LOG.debug("mock attempt_rollback tx=%s", tx_id)
        # For the scope of testing, rollback is always attempted and returns ok.
        return {'status': 'ok'}
