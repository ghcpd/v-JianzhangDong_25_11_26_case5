import logging
import time
import uuid
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Transfer lifecycle states
STATE_INIT = 'INIT'
STATE_IN_PROGRESS = 'IN_PROGRESS'
STATE_SUCCESS = 'SUCCESS'
STATE_FAILED = 'FAILED'
STATE_ROLLBACK = 'ROLLBACK'
STATE_ROLLED_BACK = 'ROLLED_BACK'


class TransferManager:
    """Core transfer manager implementing the Fixed_Transfer_Flow_v2 flow.

    Guarantees the UI/API will only receive SUCCESS once both debit and credit operations
    have been committed in the ledger. Uses retries and rollback logic.
    """

    def __init__(self, ledger_adapter, retry_attempts: int = 3, retry_delay_sec: float = 0.5):
        self.ledger = ledger_adapter
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay_sec
        # in-memory store (tx_id -> record); production: persistent DB
        self._store: Dict[str, Dict[str, Any]] = {}

    def _new_tx_id(self) -> str:
        return str(uuid.uuid4())

    def _persist(self, tx_id: str, data: Dict[str, Any]):
        # minimal persist; obviously replace with DB storage in prod
        self._store[tx_id] = data

    def _get(self, tx_id: str) -> Dict[str, Any]:
        return self._store.get(tx_id, {})

    def initiate_transfer(self, from_acct: str, to_acct: str, amount: int, tx_id: str = None) -> Dict[str, Any]:
        tx_id = tx_id or self._new_tx_id()
        logger.info('transfer.initiated', extra={'tx_id': tx_id, 'from': from_acct, 'to': to_acct, 'amount': amount})
        record = {'tx_id': tx_id, 'from': from_acct, 'to': to_acct, 'amount': amount, 'state': STATE_INIT, 'history': []}
        self._persist(tx_id, record)

        try:
            return self._apply_transfer(tx_id)
        except Exception as e:
            logger.exception('Transfer exception', extra={'tx_id': tx_id})
            rec = self._get(tx_id)
            rec['state'] = STATE_FAILED
            rec['error'] = str(e)
            self._persist(tx_id, rec)
            return {'tx_id': tx_id, 'status': 'failed', 'reason': str(e)}

    def get_state(self, tx_id: str) -> Dict[str, Any]:
        return self._get(tx_id)

    def _apply_transfer(self, tx_id: str) -> Dict[str, Any]:
        rec = self._get(tx_id)
        if not rec:
            raise ValueError('unknown tx')
        rec['state'] = STATE_IN_PROGRESS
        rec['history'].append(('state', STATE_IN_PROGRESS, time.time()))
        self._persist(tx_id, rec)

        # Do debit with retry
        for attempt in range(1, self.retry_attempts + 1):
            res = self.ledger.debit(tx_id, rec['from'], rec['amount'])
            if res['status'] == 'committed':
                logger.info('transfer.debit_committed', extra={'tx_id': tx_id, 'phase': 'debit'})
                rec['history'].append(('debit', 'committed', time.time()))
                self._persist(tx_id, rec)
                break
            elif res['status'] == 'transient_failed':
                logger.warning('transfer.debit_transient_failure', extra={'tx_id': tx_id, 'attempt': attempt})
                time.sleep(self.retry_delay)
                continue
            else:  # permanent failure
                logger.error('transfer.debit_failure', extra={'tx_id': tx_id})
                rec['state'] = STATE_FAILED
                rec['history'].append(('debit', 'failed', time.time()))
                self._persist(tx_id, rec)
                return {'tx_id': tx_id, 'status': 'failed', 'phase': 'debit'}

        # Now credit
        for attempt in range(1, self.retry_attempts + 1):
            cres = self.ledger.credit(tx_id, rec['to'], rec['amount'])
            if cres['status'] == 'committed':
                logger.info('transfer.credit_committed', extra={'tx_id': tx_id, 'phase': 'credit'})
                rec['state'] = STATE_SUCCESS
                rec['history'].append(('credit', 'committed', time.time()))
                self._persist(tx_id, rec)
                return {'tx_id': tx_id, 'status': 'success'}
            elif cres['status'] == 'transient_failed':
                logger.warning('transfer.credit_transient_failure', extra={'tx_id': tx_id, 'attempt': attempt})
                time.sleep(self.retry_delay)
                continue
            else:  # permanent failure
                logger.error('transfer.credit_failure', extra={'tx_id': tx_id})
                rec['state'] = STATE_ROLLBACK
                rec['history'].append(('credit', 'failed', time.time()))
                self._persist(tx_id, rec)
                rres = self.ledger.rollback(tx_id)
                rec['history'].append(('rollback', rres.get('status'), time.time()))
                rec['state'] = STATE_FAILED if rres.get('status') == 'rolled_back' else STATE_FAILED
                self._persist(tx_id, rec)
                return {'tx_id': tx_id, 'status': 'failed', 'phase': 'credit', 'rollback': rres}

        # If we're here, we exhausted retries for credit without a permanent fail response
        # That indicates transient failures that didn't resolve. We must rollback to keep consistency.
        logger.error('transfer.credit_unresolved_rollback', extra={'tx_id': tx_id})
        rec['state'] = STATE_ROLLBACK
        rec['history'].append(('credit', 'unresolved', time.time()))
        rres = self.ledger.rollback(tx_id)
        rec['history'].append(('rollback', rres.get('status'), time.time()))
        rec['state'] = STATE_FAILED
        self._persist(tx_id, rec)
        return {'tx_id': tx_id, 'status': 'failed', 'phase': 'credit', 'rollback': rres}
