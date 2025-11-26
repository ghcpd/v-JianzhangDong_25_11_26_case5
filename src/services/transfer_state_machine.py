"""
Transfer State Machine - Enforces valid state transitions
Prevents invalid state changes that could lead to false success scenarios
"""

from typing import Set, Dict, Optional
from src.models.transfer import TransferState, Transfer
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TransferStateMachine:
    """
    Enforces valid state transitions for transfers.
    Prevents the system from marking transfers as successful without proper validation.
    """
    
    # Define valid state transitions
    VALID_TRANSITIONS: Dict[TransferState, Set[TransferState]] = {
        TransferState.INITIATED: {
            TransferState.VALIDATING,
            TransferState.FAILED
        },
        TransferState.VALIDATING: {
            TransferState.PENDING,
            TransferState.FAILED
        },
        TransferState.PENDING: {
            TransferState.DEBIT_PROCESSING,
            TransferState.TIMEOUT,
            TransferState.FAILED
        },
        TransferState.DEBIT_PROCESSING: {
            TransferState.DEBIT_COMPLETED,
            TransferState.ROLLING_BACK,
            TransferState.TIMEOUT,
            TransferState.FAILED
        },
        TransferState.DEBIT_COMPLETED: {
            TransferState.CREDIT_PROCESSING,
            TransferState.ROLLING_BACK,
            TransferState.TIMEOUT
        },
        TransferState.CREDIT_PROCESSING: {
            TransferState.COMPLETED,
            TransferState.ROLLING_BACK,
            TransferState.TIMEOUT,
            TransferState.FAILED
        },
        TransferState.ROLLING_BACK: {
            TransferState.FAILED
        },
        TransferState.COMPLETED: set(),  # Terminal state
        TransferState.FAILED: set(),     # Terminal state
        TransferState.TIMEOUT: {
            TransferState.ROLLING_BACK,
            TransferState.FAILED
        }
    }
    
    @classmethod
    def can_transition(cls, current_state: TransferState, 
                      target_state: TransferState) -> bool:
        """
        Check if transition from current_state to target_state is valid.
        
        Args:
            current_state: Current transfer state
            target_state: Desired target state
            
        Returns:
            True if transition is valid, False otherwise
        """
        valid_targets = cls.VALID_TRANSITIONS.get(current_state, set())
        return target_state in valid_targets
        
    @classmethod
    def validate_transition(cls, transfer: Transfer, 
                          target_state: TransferState,
                          reason: Optional[str] = None) -> bool:
        """
        Validate and execute state transition.
        
        Args:
            transfer: Transfer object to transition
            target_state: Desired target state
            reason: Optional reason for transition
            
        Returns:
            True if transition successful, False otherwise
        """
        if not cls.can_transition(transfer.state, target_state):
            logger.error(
                "Invalid state transition attempted",
                extra={
                    "transaction_id": transfer.transaction_id,
                    "current_state": transfer.state.value,
                    "target_state": target_state.value,
                    "reason": reason
                }
            )
            return False
            
        logger.info(
            "State transition",
            extra={
                "transaction_id": transfer.transaction_id,
                "from_state": transfer.state.value,
                "to_state": target_state.value,
                "reason": reason
            }
        )
        
        transfer.transition_to(target_state, reason)
        return True
        
    @classmethod
    def can_complete(cls, transfer: Transfer) -> bool:
        """
        Verify if transfer can be marked as completed.
        Ensures both debit and credit operations are confirmed.
        
        This is a critical check that prevents false success scenarios.
        """
        # Must be in CREDIT_PROCESSING state
        if transfer.state != TransferState.CREDIT_PROCESSING:
            logger.warning(
                "Cannot complete transfer - not in credit processing state",
                extra={
                    "transaction_id": transfer.transaction_id,
                    "current_state": transfer.state.value
                }
            )
            return False
            
        # Must have debit completion timestamp
        if not transfer.debit_completed_at:
            logger.error(
                "Cannot complete transfer - debit not confirmed",
                extra={
                    "transaction_id": transfer.transaction_id
                }
            )
            return False
            
        # Must have ledger references
        if not transfer.ledger_debit_ref:
            logger.error(
                "Cannot complete transfer - missing ledger debit reference",
                extra={
                    "transaction_id": transfer.transaction_id
                }
            )
            return False
            
        return True
        
    @classmethod
    def must_rollback(cls, transfer: Transfer) -> bool:
        """
        Determine if transfer requires rollback.
        Any failure after debit completion requires rollback.
        """
        return (
            transfer.state in [
                TransferState.DEBIT_COMPLETED,
                TransferState.CREDIT_PROCESSING
            ] and
            transfer.debit_completed_at is not None
        )
