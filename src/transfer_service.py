import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from .adapters.ledger_adapter import LedgerAdapter

LOG = logging.getLogger("transfer_service")


class TransferState(Enum):
    INITIATED = "initiated"
    DEBIT_POSTED = "debit_posted"
    CREDIT_POSTED = "credit_posted"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Transaction:
    tx_id: str
    from_account: str
    to_account: str
    amount: float
    state: TransferState = TransferState.INITIATED
    failure_reason: Optional[str] = None
    events: list = field(default_factory=list)


class TransferService:
    def __init__(self, ledger: LedgerAdapter, retry_attempts: int = 3, retry_delay: float = 0.5):
        self.ledger = ledger
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.store: Dict[str, Transaction] = {}

    def _log(self, tx: Transaction, message: str, level=logging.INFO):
        LOG.log(level, "%s | tx=%s | state=%s | msg=%s", tx.tx_id, tx.tx_id, tx.state.value, message)

    def initiate_transfer(self, from_account: str, to_account: str, amount: float, wait_for_completion=True, mode_hint: Optional[str] = None):
        tx_id = str(uuid.uuid4())
        tx = Transaction(tx_id=tx_id, from_account=from_account, to_account=to_account, amount=amount)
        self.store[tx_id] = tx
        self._log(tx, f"initiated transfer from {from_account} to {to_account} amount={amount} hint={mode_hint}")

        # Try to post debit first, with retries
        success, reason = self._post_with_retries(tx, 'debit')
        if not success:
            tx.state = TransferState.FAILED
            tx.failure_reason = f"debit_failed:{reason}"
            self._log(tx, "debit failed - rolling back if needed", logging.ERROR)
            # attempt compensating rollback if debit partially applied
            self._attempt_rollback_on_fail(tx)
            return tx

        tx.state = TransferState.DEBIT_POSTED
        self._log(tx, "debit posted")

        success, reason = self._post_with_retries(tx, 'credit')
        if not success:
            tx.state = TransferState.FAILED
            tx.failure_reason = f"credit_failed:{reason}"
            self._log(tx, "credit failed - attempting rollback of debit", logging.ERROR)
            # ensure we attempt to rollback previously posted debit
            self._attempt_rollback_on_fail(tx)
            return tx

        tx.state = TransferState.CREDIT_POSTED
        tx.state = TransferState.COMPLETED
        self._log(tx, "transfer completed successfully")
        return tx

    def _post_with_retries(self, tx: Transaction, kind: str):
        attempt = 0
        last_err = None
        while attempt < self.retry_attempts:
            attempt += 1
            try:
                if kind == 'debit':
                    response = self.ledger.post_debit(tx.tx_id, tx.from_account, tx.amount)
                else:
                    response = self.ledger.post_credit(tx.tx_id, tx.to_account, tx.amount)

                tx.events.append({"tx_id": tx.tx_id, "attempt": attempt, "kind": kind, "response": response})

                if response.get('status') == 'ok':
                    return True, None
                # If ledger says transient, raise to retry
                if response.get('status') == 'retry':
                    last_err = 'transient'
                    self._log(tx, f"{kind} attempt {attempt} transient, will retry", logging.WARNING)
                else:
                    last_err = response.get('error') or 'unknown'
                    break

            except Exception as exc:
                last_err = str(exc)
                self._log(tx, f"{kind} attempt {attempt} raised {last_err}", logging.WARNING)

            time.sleep(self.retry_delay * attempt)

        return False, last_err

    def _attempt_rollback_on_fail(self, tx: Transaction):
        # Make best-effort rollback and record in events
        try:
            rb = self.ledger.attempt_rollback(tx.tx_id)
            tx.events.append({"tx_id": tx.tx_id, "rollback": rb})
            self._log(tx, "rollback attempted")
        except Exception as exc:
            tx.events.append({"tx_id": tx.tx_id, "rollback_error": str(exc)})
            self._log(tx, f"rollback failed: {exc}", logging.ERROR)


def get_transfer_service_for_tests(mock_ledger=None, retry_attempts: int = 3):
    ledger = LedgerAdapter(mock_ledger if mock_ledger is not None else None)
    return TransferService(ledger, retry_attempts=retry_attempts)
