import logging
from typing import Optional

LOG = logging.getLogger("ledger_adapter")


class LedgerAdapter:
    """Adapter that delegates to a provided mock ledger service when running in tests.

    The adapter implements an interface similar to a real core ledger client but in tests uses
    the mock service to deterministically simulate success, transient retryable errors, or permanent failures.
    """

    def __init__(self, mock_service: Optional[object] = None):
        self.mock_service = mock_service

    def post_debit(self, tx_id: str, from_account: str, amount: float) -> dict:
        LOG.debug("post_debit tx=%s %s -> amount=%s", tx_id, from_account, amount)
        if self.mock_service:
            return self.mock_service.post_debit(tx_id, from_account, amount)
        # In a real adapter, here you'd call the real ledger.
        return {"status": "ok"}

    def post_credit(self, tx_id: str, to_account: str, amount: float) -> dict:
        LOG.debug("post_credit tx=%s %s -> amount=%s", tx_id, to_account, amount)
        if self.mock_service:
            return self.mock_service.post_credit(tx_id, to_account, amount)
        return {"status": "ok"}

    def attempt_rollback(self, tx_id: str) -> dict:
        LOG.debug("attempt_rollback tx=%s", tx_id)
        if self.mock_service:
            return self.mock_service.attempt_rollback(tx_id)
        return {"status": "ok"}
