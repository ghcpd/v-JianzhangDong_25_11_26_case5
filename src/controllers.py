import logging
from .transfer_service import get_transfer_service_for_tests

LOG = logging.getLogger("controllers")


class TransferController:
    def __init__(self, mock_ledger=None):
        # build a service that uses the provided mock
        self.service = get_transfer_service_for_tests(mock_ledger)

    def submit(self, from_account, to_account, amount, wait=True, mode_hint=None):
        tx = self.service.initiate_transfer(from_account, to_account, amount, wait_for_completion=wait, mode_hint=mode_hint)
        LOG.info("controller submit tx=%s state=%s", tx.tx_id, tx.state.value)
        return {
            'tx_id': tx.tx_id,
            'state': tx.state.value,
            'failure_reason': tx.failure_reason,
            'events': tx.events,
        }
