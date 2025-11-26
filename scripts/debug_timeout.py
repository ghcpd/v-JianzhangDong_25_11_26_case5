import logging
import uuid
from mocks.mock_ledger_service import MockLedgerService
from src.adapters.ledger_adapter import LedgerAdapter
from src.transfer_service import TransferService

logging.basicConfig(level=logging.DEBUG)

beh = {"debit":[True], "credit":[False, False, False]}
ledger = MockLedgerService({"A":1000, "B":0}, {})
tx_id = str(uuid.uuid4())
ledger.behavior[tx_id] = beh
adapter = LedgerAdapter(ledger)
svc = TransferService(adapter)
svc.initiate_transfer('A', 'B', 500, sync=True, tx_id=tx_id)
print('balances', ledger.balances)
print('attempts', ledger.attempts)
print('audit', svc.audit_log)
