import time
import uuid
import logging

logger = logging.getLogger(__name__)


class LedgerAdapter:
    """Adapter that interfaces with a ledger service; here it's a pluggable interface.
    For testing we rely on mocks/mock_ledger_service.py which implements the same API.
    """

    def __init__(self, ledger_client):
        # ledger_client should implement: post_debit, post_credit, reverse_tx
        self.ledger = ledger_client

    def post_debit(self, tx_id, account, amount):
        logger.debug("LedgerAdapter.post_debit tx=%s acc=%s amt=%s", tx_id, account, amount)
        return self.ledger.post_debit(tx_id, account, amount)

    def post_credit(self, tx_id, account, amount):
        logger.debug("LedgerAdapter.post_credit tx=%s acc=%s amt=%s", tx_id, account, amount)
        return self.ledger.post_credit(tx_id, account, amount)

    def reverse_tx(self, tx_id):
        logger.debug("LedgerAdapter.reverse_tx tx=%s", tx_id)
        return self.ledger.reverse_tx(tx_id)
