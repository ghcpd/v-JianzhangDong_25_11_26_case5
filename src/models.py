"""
Transfer module models and ORM

Defines the Transfer model with state machine logic and database persistence.
"""

import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any
from decimal import Decimal


class TransferState(str, Enum):
    """States in the transfer lifecycle"""
    INITIATED = "INITIATED"  # Transfer request received and validated
    PENDING_DEBIT = "PENDING_DEBIT"  # Debit request sent to ledger, waiting for callback
    DEBIT_POSTED = "DEBIT_POSTED"  # Debit confirmed by ledger
    PENDING_CREDIT = "PENDING_CREDIT"  # Credit request sent to ledger, waiting for callback
    SUCCESS = "SUCCESS"  # Both debit and credit completed
    FAILED = "FAILED"  # Transfer failed (debit failed, credit failed, or timeout)
    ROLLEDBACK = "ROLLEDBACK"  # Failed debit was reversed via compensating transaction


class Transfer:
    """
    Transfer model representing a single funds transfer.
    
    This is a simplified in-memory model for the mock. In production,
    this would be an ORM model (SQLAlchemy, Tortoise, etc.).
    """
    
    def __init__(
        self,
        id: uuid.UUID,
        correlation_id: str,
        idempotency_key: str,
        state: TransferState,
        sender_account: str,
        recipient_account: str,
        amount: Decimal,
        timeout_at: datetime,
        created_at: datetime = None,
        updated_at: datetime = None,
        ledger_debit_txn_id: Optional[str] = None,
        ledger_credit_txn_id: Optional[str] = None,
        reverse_txn_id: Optional[str] = None,
        error_reason: Optional[str] = None
    ):
        self.id = id
        self.correlation_id = correlation_id
        self.idempotency_key = idempotency_key
        self.state = state
        self.sender_account = sender_account
        self.recipient_account = recipient_account
        self.amount = amount
        self.timeout_at = timeout_at
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.ledger_debit_txn_id = ledger_debit_txn_id
        self.ledger_credit_txn_id = ledger_credit_txn_id
        self.reverse_txn_id = reverse_txn_id
        self.error_reason = error_reason
    
    @staticmethod
    def create(
        sender_account: str,
        recipient_account: str,
        amount: Decimal,
        timeout_seconds: int = 30
    ) -> 'Transfer':
        """Create a new transfer"""
        transfer_id = uuid.uuid4()
        correlation_id = _generate_correlation_id()
        idempotency_key = str(uuid.uuid4())
        
        return Transfer(
            id=transfer_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            state=TransferState.INITIATED,
            sender_account=sender_account,
            recipient_account=recipient_account,
            amount=amount,
            timeout_at=datetime.utcnow() + timedelta(seconds=timeout_seconds)
        )
    
    def get_valid_next_states(self) -> list:
        """Get list of valid next states from current state"""
        valid_transitions = {
            TransferState.INITIATED: [TransferState.PENDING_DEBIT, TransferState.FAILED],
            TransferState.PENDING_DEBIT: [TransferState.DEBIT_POSTED, TransferState.FAILED],
            TransferState.DEBIT_POSTED: [TransferState.PENDING_CREDIT, TransferState.FAILED],
            TransferState.PENDING_CREDIT: [TransferState.SUCCESS, TransferState.FAILED],
            TransferState.FAILED: [TransferState.ROLLEDBACK],
            TransferState.SUCCESS: [],
            TransferState.ROLLEDBACK: [],
        }
        return valid_transitions.get(self.state, [])
    
    def can_transition_to(self, new_state: TransferState) -> bool:
        """Check if transition to new_state is valid"""
        return new_state in self.get_valid_next_states()
    
    def transition_to(self, new_state: TransferState, reason: str = None) -> bool:
        """
        Transition to a new state.
        
        Returns True if successful, False if transition not allowed.
        """
        if not self.can_transition_to(new_state):
            return False
        
        self.state = new_state
        self.updated_at = datetime.utcnow()
        return True
    
    def is_timed_out(self) -> bool:
        """Check if transfer has timed out"""
        return datetime.utcnow() > self.timeout_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'id': str(self.id),
            'correlation_id': self.correlation_id,
            'state': self.state.value,
            'sender_account': self.sender_account,
            'recipient_account': self.recipient_account,
            'amount': str(self.amount),
            'ledger_debit_txn_id': self.ledger_debit_txn_id,
            'ledger_credit_txn_id': self.ledger_credit_txn_id,
            'reverse_txn_id': self.reverse_txn_id,
            'error_reason': self.error_reason,
            'created_at': self.created_at.isoformat() + 'Z',
            'updated_at': self.updated_at.isoformat() + 'Z',
            'timeout_at': self.timeout_at.isoformat() + 'Z'
        }


class AuditLog:
    """
    Audit log entry for transfer tracking and reconciliation.
    """
    
    def __init__(
        self,
        correlation_id: str,
        timestamp: datetime,
        step: str,
        actor: str,
        details: Dict[str, Any],
        result: str = 'success',
        error: Optional[str] = None
    ):
        self.id = str(uuid.uuid4())
        self.correlation_id = correlation_id
        self.timestamp = timestamp
        self.step = step
        self.actor = actor
        self.details = details or {}
        self.result = result
        self.error = error
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'correlation_id': self.correlation_id,
            'timestamp': self.timestamp.isoformat() + 'Z',
            'step': self.step,
            'actor': self.actor,
            'details': self.details,
            'result': self.result,
            'error': self.error
        }


# In-memory storage for mock (replace with database in production)
_transfer_store: Dict[uuid.UUID, Transfer] = {}
_audit_log_store: list = []


def store_transfer(transfer: Transfer) -> None:
    """Store transfer in memory"""
    _transfer_store[transfer.id] = transfer


def get_transfer(transfer_id: uuid.UUID) -> Optional[Transfer]:
    """Retrieve transfer from memory"""
    return _transfer_store.get(transfer_id)


def get_transfer_by_correlation_id(correlation_id: str) -> Optional[Transfer]:
    """Find transfer by correlation ID"""
    for transfer in _transfer_store.values():
        if transfer.correlation_id == correlation_id:
            return transfer
    return None


def store_audit_log(log: AuditLog) -> None:
    """Store audit log entry"""
    _audit_log_store.append(log)


def get_audit_logs_for_correlation_id(correlation_id: str) -> list:
    """Get all audit logs for a correlation ID"""
    return [log for log in _audit_log_store if log.correlation_id == correlation_id]


def clear_store() -> None:
    """Clear all stores (for testing)"""
    global _transfer_store, _audit_log_store
    _transfer_store.clear()
    _audit_log_store.clear()


def _generate_correlation_id() -> str:
    """
    Generate a correlation ID in format: TXN-YYYY-DDD-XXXXXX
    
    Example: TXN-2025-330-ABC123
    """
    now = datetime.utcnow()
    year = now.year
    day_of_year = now.timetuple().tm_yday
    random_suffix = uuid.uuid4().hex[:6].upper()
    return f"TXN-{year}-{day_of_year:03d}-{random_suffix}"
