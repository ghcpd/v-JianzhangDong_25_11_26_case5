"""
A simple idempotent mock ledger service used for testing seamless transfer flows.
This service keeps per-tx state and account balances. It simulates transient/network
failures and permanent failures with controlled flags.
"""
import threading
from typing import Dict, Any

_lock = threading.Lock()
_accounts: Dict[str, int] = {}
_tx_states: Dict[str, Dict[str, Any]] = {}

# Behavior hooks that the test harness can set
BEHAVIOR = {
    # tx_id => string or list: 'success', 'transient_failure', 'permanent_failure'
    'debit': {},
    'credit': {},
}


def init_account(account_id: str, balance: int):
    with _lock:
        _accounts[account_id] = balance


def get_balance(account_id: str) -> int:
    with _lock:
        return _accounts.get(account_id, 0)


def reset():
    with _lock:
        _accounts.clear()
        _tx_states.clear()
        BEHAVIOR['debit'].clear()
        BEHAVIOR['credit'].clear()


def _record_tx(tx_id: str, op: str, status: str, meta=None):
    with _lock:
        state = _tx_states.setdefault(tx_id, {'ops': {}})
        state['ops'][op] = {'status': status, 'meta': meta or {}}


def _pop_behavior(op: str, tx_id: str):
    v = BEHAVIOR[op].get(tx_id, 'success')
    if isinstance(v, list):
        # behave like a queue of responses
        res = v.pop(0)
        # if queue empties, default to success
        if not v:
            BEHAVIOR[op][tx_id] = 'success'
        else:
            BEHAVIOR[op][tx_id] = v
        return res
    return v


def debit(tx_id: str, account_id: str, amount: int) -> Dict[str, Any]:
    behavior = _pop_behavior('debit', tx_id)
    with _lock:
        if tx_id in _tx_states and _tx_states[tx_id].get('debit') == 'committed':
            return {'status': 'committed'}

        if behavior == 'permanent_failure':
            _record_tx(tx_id, 'debit', 'failed')
            return {'status': 'failed', 'reason': 'perm'}
        if behavior == 'transient_failure':
            _record_tx(tx_id, 'debit', 'transient_failed')
            return {'status': 'transient_failed', 'reason': 'network'}

        # success
        _accounts[account_id] = _accounts.get(account_id, 0) - amount
        _record_tx(tx_id, 'debit', 'committed', {'account': account_id, 'amount': amount})
        return {'status': 'committed'}


def credit(tx_id: str, account_id: str, amount: int) -> Dict[str, Any]:
    behavior = _pop_behavior('credit', tx_id)
    with _lock:
        if tx_id in _tx_states and _tx_states[tx_id].get('credit') == 'committed':
            return {'status': 'committed'}

        if behavior == 'permanent_failure':
            _record_tx(tx_id, 'credit', 'failed')
            return {'status': 'failed', 'reason': 'perm'}
        if behavior == 'transient_failure':
            _record_tx(tx_id, 'credit', 'transient_failed')
            return {'status': 'transient_failed', 'reason': 'network'}

        # success
        _accounts[account_id] = _accounts.get(account_id, 0) + amount
        _record_tx(tx_id, 'credit', 'committed', {'account': account_id, 'amount': amount})
        return {'status': 'committed'}


def rollback(tx_id: str) -> Dict[str, Any]:
    """Rollback will reverse any successful debit or credit that is already committed."""
    with _lock:
        state = _tx_states.get(tx_id)
        if not state:
            return {'status': 'no-op'}
        ops = state.get('ops', {})
        if 'credit' in ops and ops['credit']['status'] == 'committed':
            meta = ops['credit']['meta']
            acc = meta['account']
            amt = meta['amount']
            _accounts[acc] = _accounts.get(acc, 0) - amt
            _record_tx(tx_id, 'credit', 'rolled_back')
        if 'debit' in ops and ops['debit']['status'] == 'committed':
            meta = ops['debit']['meta']
            acc = meta['account']
            amt = meta['amount']
            _accounts[acc] = _accounts.get(acc, 0) + amt
            _record_tx(tx_id, 'debit', 'rolled_back')
        state['rolled_back'] = True
        return {'status': 'rolled_back'}


def status(tx_id: str) -> Dict[str, Any]:
    with _lock:
        return _tx_states.get(tx_id, {})
