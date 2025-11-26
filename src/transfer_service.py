import threading
import queue
import uuid
import time
import logging
from .state_machine import TransferRecord, TransferState

logger = logging.getLogger(__name__)


class TransferService:
    """Service that manages transfers and ensures the API only reports success
    after ledger operations are confirmed. Uses an in-memory DB and an event queue
    to simulate async behavior.
    """

    def __init__(self, ledger_adapter, max_retries=3, backoff=0.5):
        self.ledger = ledger_adapter
        self.db = {}  # tx_id -> TransferRecord
        self.queue = queue.Queue()
        self.max_retries = max_retries
        self.backoff = backoff
        self.audit_log = []
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def initiate_transfer(self, from_account, to_account, amount, sync=False, tx_id=None):
        tx_id = tx_id or str(uuid.uuid4())
        record = TransferRecord(tx_id=tx_id, from_account=from_account, to_account=to_account, amount=amount)
        self.db[tx_id] = record
        logger.info("transfer.initiated", extra={"tx_id": tx_id, "from": self._mask(from_account), "to": self._mask(to_account), "amount": amount})
        self.audit_log.append({"tx_id": tx_id, "event": "transfer.initiated", "state": record.state.value, "from": self._mask(from_account), "to": self._mask(to_account), "amount": amount})
        # enqueue event for processing
        self.queue.put(tx_id)

        # If sync is requested, block until processing finishes (for demo/testing only)
        if sync:
            # Wait for record to reach final state or timeout
            start = time.time()
            timeout = 10
            while time.time() - start < timeout:
                st = self.get_transfer_status(tx_id)
                if st in (TransferState.SUCCEEDED.value, TransferState.FAILED.value, TransferState.ROLLEDBACK.value):
                    break
                time.sleep(0.05)
        return tx_id

    def get_transfer(self, tx_id):
        return self.db.get(tx_id)

    def get_transfer_status(self, tx_id):
        rec = self.get_transfer(tx_id)
        return rec.state.value if rec else None

    def _worker_loop(self):
        while True:
            try:
                tx_id = self.queue.get()
                self._process_transfer(tx_id)
            except Exception as exc:
                logger.exception("worker.loop.exception: %s", exc)

    def _process_transfer(self, tx_id):
        rec = self.get_transfer(tx_id)
        if not rec:
            logger.warning("_process_transfer: missing record for %s", tx_id)
            return
        if rec.state != TransferState.INITIATED:
            logger.info("_process_transfer: skipping non-initiated tx %s", tx_id)
            return
        rec.state = TransferState.IN_PROGRESS
        rec.updated_at = time.time()
        logger.info("transfer.processing", extra={"tx_id": tx_id})

        # perform idempotent debit + credit via ledger adapter with retries
        debit_ok = self._attempt_with_retries(lambda: self.ledger.post_debit(tx_id, rec.from_account, rec.amount), tx_id)
        if not debit_ok:
            logger.error("transfer.debit.failed", extra={"tx_id": tx_id})
            self.audit_log.append({"tx_id": tx_id, "event": "transfer.debit.failed", "state": rec.state.value, "from": self._mask(rec.from_account), "to": self._mask(rec.to_account), "amount": rec.amount})
            rec.state = TransferState.FAILED
            rec.updated_at = time.time()
            # ensure rollback attempts are made (idempotent no-op if none)
            self.ledger.reverse_tx(tx_id)
            return

        credit_ok = self._attempt_with_retries(lambda: self.ledger.post_credit(tx_id, rec.to_account, rec.amount), tx_id)
        if not credit_ok:
            logger.error("transfer.credit.failed", extra={"tx_id": tx_id})
            self.audit_log.append({"tx_id": tx_id, "event": "transfer.credit.failed", "state": rec.state.value, "from": self._mask(rec.from_account), "to": self._mask(rec.to_account), "amount": rec.amount})
            # Attempt rollback of debit
            rb_ok = self.ledger.reverse_tx(tx_id)
            rec.state = TransferState.ROLLEDBACK if rb_ok else TransferState.FAILED
            rec.updated_at = time.time()
            self.audit_log.append({"tx_id": tx_id, "event": "transfer.rolledback" if rec.state == TransferState.ROLLEDBACK else "transfer.failed", "state": rec.state.value, "from": self._mask(rec.from_account), "to": self._mask(rec.to_account), "amount": rec.amount})
            return

        # both succeeded
        rec.state = TransferState.SUCCEEDED
        rec.updated_at = time.time()
        logger.info("transfer.succeeded", extra={"tx_id": tx_id})
        self.audit_log.append({"tx_id": tx_id, "event": "transfer.succeeded", "state": rec.state.value, "from": self._mask(rec.from_account), "to": self._mask(rec.to_account), "amount": rec.amount})

    def _mask(self, account):
        # Mask account identifiers to avoid exposing full account numbers.
        if not account:
            return "**"
        if len(account) == 1:
            return account[0] + "***"
        elif len(account) == 2:
            return account[0] + "***" + account[1]
        return account[0] + "***" + account[-1]

    def _attempt_with_retries(self, func, tx_id):
        # Attempt exactly max_retries times (attempt count 1..max_retries)
        for attempt in range(1, self.max_retries + 1):
            try:
                success = func()
                if success:
                    return True
            except Exception as exc:
                logger.warning("attempt failed tx=%s attempt=%s exc=%s", tx_id, attempt, exc)
            # exponential backoff
            wait = self.backoff * (2 ** (attempt - 1))
            time.sleep(wait)
        return False
