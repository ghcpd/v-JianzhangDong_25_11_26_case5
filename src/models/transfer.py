"""
Transfer domain models and state definitions
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


class TransferState(Enum):
    """
    Transfer lifecycle states.
    State transitions are strictly enforced by the state machine.
    """
    INITIATED = "initiated"           # Transfer request received
    VALIDATING = "validating"         # Input validation in progress
    PENDING = "pending"               # Awaiting ledger processing
    DEBIT_PROCESSING = "debit_processing"    # Debit operation in progress
    DEBIT_COMPLETED = "debit_completed"      # Debit successful, credit pending
    CREDIT_PROCESSING = "credit_processing"  # Credit operation in progress
    COMPLETED = "completed"           # Both debit and credit successful
    ROLLING_BACK = "rolling_back"     # Failure detected, rollback in progress
    FAILED = "failed"                 # Transfer failed after rollback
    TIMEOUT = "timeout"               # Operation timed out


class TransferErrorCode(Enum):
    """Standard error codes for transfer failures"""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    INVALID_ACCOUNT = "INVALID_ACCOUNT"
    DEBIT_FAILED = "DEBIT_FAILED"
    CREDIT_FAILED = "CREDIT_FAILED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class TransferRequest:
    """Transfer request payload"""
    source_account: str
    destination_account: str
    amount: float
    currency: str = "USD"
    reference: Optional[str] = None
    idempotency_key: Optional[str] = None


@dataclass
class StateTransition:
    """Record of state transition"""
    from_state: TransferState
    to_state: TransferState
    timestamp: datetime
    reason: Optional[str] = None


@dataclass
class Transfer:
    """
    Complete transfer record with full audit trail.
    Tracks all state transitions and operations.
    """
    transaction_id: str
    request: TransferRequest
    state: TransferState = TransferState.INITIATED
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # State tracking
    state_history: List[StateTransition] = field(default_factory=list)
    
    # Operation results
    debit_completed_at: Optional[datetime] = None
    credit_completed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    
    # Error tracking
    error_code: Optional[TransferErrorCode] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    
    # Ledger references
    ledger_debit_ref: Optional[str] = None
    ledger_credit_ref: Optional[str] = None
    
    def transition_to(self, new_state: TransferState, reason: Optional[str] = None) -> None:
        """
        Transition to a new state with validation.
        Records the transition in history for audit trail.
        """
        transition = StateTransition(
            from_state=self.state,
            to_state=new_state,
            timestamp=datetime.utcnow(),
            reason=reason
        )
        self.state_history.append(transition)
        self.state = new_state
        self.updated_at = datetime.utcnow()
        
    def is_terminal_state(self) -> bool:
        """Check if transfer is in a terminal state"""
        return self.state in [
            TransferState.COMPLETED,
            TransferState.FAILED,
            TransferState.TIMEOUT
        ]
        
    def is_success(self) -> bool:
        """Check if transfer completed successfully"""
        return self.state == TransferState.COMPLETED
        
    def can_retry(self) -> bool:
        """Check if transfer can be retried"""
        return (
            self.state in [TransferState.FAILED, TransferState.TIMEOUT] and
            self.retry_count < 3
        )
