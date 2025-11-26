import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class LedgerAdapter:
    """Adapter that handles interaction with a ledger micro-service.

    Interfaces with `mock_ledger_service` during local testing and can be
    replaced with real HTTP/gRPC adapters in production.
    """

    def __init__(self, ledger_client):
        self.client = ledger_client

    def debit(self, tx_id: str, account_id: str, amount: int) -> Dict[str, Any]:
        logger.info('ledger.debit', extra={
            'tx_id': tx_id, 'phase': 'debit', 'account': account_id, 'amount': amount
        })
        return self.client.debit(tx_id, account_id, amount)

    def credit(self, tx_id: str, account_id: str, amount: int) -> Dict[str, Any]:
        logger.info('ledger.credit', extra={
            'tx_id': tx_id, 'phase': 'credit', 'account': account_id, 'amount': amount
        })
        return self.client.credit(tx_id, account_id, amount)

    def rollback(self, tx_id: str) -> Dict[str, Any]:
        logger.info('ledger.rollback', extra={'tx_id': tx_id, 'phase': 'rollback'})
        return self.client.rollback(tx_id)

    def status(self, tx_id: str) -> Dict[str, Any]:
        return self.client.status(tx_id)
