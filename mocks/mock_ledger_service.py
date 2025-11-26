import time
import threading
import logging

logger = logging.getLogger(__name__)


class MockLedgerService:
    """A configurable in-memory ledger simulator.

    It keeps balances per account and allows configuring per-tx behaviors: succeed/fail sequences.
    For idempotency, operations use tx_id to avoid double-debit/credit.
    """

    def __init__(self, initial_balances=None, behavior=None, delay=0):
        # balances: account -> float
        self.balances = dict(initial_balances or {})
        self.behavior = behavior or {}  # tx_id -> {"debit": [True, False], "credit": [True, False]}
        self.delay = delay
        self.lock = threading.Lock()
        self.operations = {}  # tx_id -> list of ops done to ensure idempotency
        self.attempts = {}

    def post_debit(self, tx_id, account, amount):
        time.sleep(self.delay)
        cfg = self.behavior.get(tx_id, {})
        seq = cfg.get("debit", [])
        self.attempts.setdefault(tx_id, {})
        self.attempts[tx_id].setdefault("debit", 0)
        self.attempts[tx_id]["debit"] += 1
        attempt = self.attempts[tx_id]["debit"]
        # default succeed if no config
        if seq and attempt <= len(seq) and not seq[attempt - 1]:
            logger.debug("MockLedger.post_debit configured fail for tx=%s attempt=%s", tx_id, attempt)
            return False

        with self.lock:
            if tx_id in self.operations and any(op[0] == "debit" for op in self.operations[tx_id]):
                # idempotent: already debited
                logger.debug("MockLedger.post_debit idempotent noop tx=%s", tx_id)
                return True
            if self.balances.get(account, 0) < amount:
                logger.debug("MockLedger.post_debit insufficient funds tx=%s", tx_id)
                return False
            self.balances[account] = self.balances.get(account, 0) - amount
            self.operations.setdefault(tx_id, []).append(("debit", account, amount))
            logger.info("MockLedger: debited %s from %s for tx=%s", amount, account, tx_id)
            return True

    def post_credit(self, tx_id, account, amount):
        time.sleep(self.delay)
        cfg = self.behavior.get(tx_id, {})
        seq = cfg.get("credit", [])
        self.attempts.setdefault(tx_id, {})
        self.attempts[tx_id].setdefault("credit", 0)
        self.attempts[tx_id]["credit"] += 1
        attempt = self.attempts[tx_id]["credit"]
        if seq and attempt <= len(seq) and not seq[attempt - 1]:
            logger.debug("MockLedger.post_credit configured fail for tx=%s attempt=%s", tx_id, attempt)
            return False

        with self.lock:
            if tx_id in self.operations and any(op[0] == "credit" for op in self.operations[tx_id]):
                logger.debug("MockLedger.post_credit idempotent noop tx=%s", tx_id)
                return True
            self.balances[account] = self.balances.get(account, 0) + amount
            self.operations.setdefault(tx_id, []).append(("credit", account, amount))
            logger.info("MockLedger: credited %s to %s for tx=%s", amount, account, tx_id)
            return True

    def reverse_tx(self, tx_id):
        time.sleep(self.delay)
        with self.lock:
            ops = self.operations.get(tx_id, [])
            if not ops:
                logger.debug("MockLedger.reverse_tx no ops found tx=%s", tx_id)
                return True
            # undo in reverse order
            for op in reversed(ops):
                typ, account, amount = op
                if typ == "debit":
                    self.balances[account] = self.balances.get(account, 0) + amount
                    logger.info("MockLedger: reversed debit %s to %s for tx=%s", amount, account, tx_id)
                elif typ == "credit":
                    self.balances[account] = self.balances.get(account, 0) - amount
                    logger.info("MockLedger: reversed credit %s from %s for tx=%s", amount, account, tx_id)
            self.operations.pop(tx_id, None)
            return True
