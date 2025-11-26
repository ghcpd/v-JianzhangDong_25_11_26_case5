import logging
from src.transfer_manager import TransferManager
from src.adapters.ledger_adapter import LedgerAdapter
from mocks import mock_ledger_service

logger = logging.getLogger(__name__)

# Build a controller that provides a simple 'API' function for UI to call

_ledger_adapter = LedgerAdapter(mock_ledger_service)
_transfer_manager = TransferManager(_ledger_adapter)


def transfer_request(from_acct: str, to_acct: str, amount: int, tx_id: str = None) -> dict:
    # API wrapper that returns success only after the manager confirms the ledger commit
    res = _transfer_manager.initiate_transfer(from_acct, to_acct, amount, tx_id=tx_id)
    if res.get('status') == 'success':
        # in a real HTTP API we'd return 200
        return {'status': 'success', 'tx_id': res['tx_id']}
    else:
        # return 400 or 500 accordingly
        return {'status': 'failed', 'tx_id': res['tx_id'], 'details': res}


def get_transfer_status(tx_id: str) -> dict:
    return _transfer_manager.get_state(tx_id)
