"""
Transfer Service - Core business logic with ledger integration
Implements the fixed transfer flow with proper state management
"""

import uuid
from datetime import datetime
from typing import Optional, Tuple
from src.models.transfer import (
    Transfer, TransferRequest, TransferState, 
    TransferErrorCode
)
from src.services.transfer_state_machine import TransferStateMachine
from src.services.ledger_adapter import LedgerAdapter
from src.utils.logger import AuditLogger, get_logger

logger = get_logger(__name__)
audit_logger = AuditLogger()


class TransferService:
    """
    Core transfer service implementing the Fixed_Transfer_Flow_v2.
    
    Key improvements over the broken version:
    1. Enforced state machine prevents invalid state transitions
    2. Explicit confirmation of both debit and credit before success
    3. Automatic rollback on partial failures
    4. Comprehensive audit logging
    5. Retry logic with exponential backoff
    """
    
    def __init__(self, ledger_adapter: LedgerAdapter):
        """
        Initialize transfer service.
        
        Args:
            ledger_adapter: Adapter for ledger operations
        """
        self.ledger = ledger_adapter
        self.state_machine = TransferStateMachine
        self.transfers = {}  # In-memory store (use database in production)
        
    def initiate_transfer(self, request: TransferRequest) -> Transfer:
        """
        Initiate a new transfer request.
        
        Args:
            request: Transfer request details
            
        Returns:
            Transfer object in INITIATED state
        """
        # Generate unique transaction ID
        transaction_id = self._generate_transaction_id()
        
        # Create transfer record
        transfer = Transfer(
            transaction_id=transaction_id,
            request=request,
            state=TransferState.INITIATED
        )
        
        # Store transfer
        self.transfers[transaction_id] = transfer
        
        # Audit log
        audit_logger.log_transfer_initiated(
            transaction_id=transaction_id,
            source_account=request.source_account,
            destination_account=request.destination_account,
            amount=request.amount,
            currency=request.currency
        )
        
        logger.info(
            "Transfer initiated",
            extra={
                "transaction_id": transaction_id,
                "amount": request.amount
            }
        )
        
        return transfer
        
    def execute_transfer(self, transaction_id: str) -> Tuple[bool, Optional[str]]:
        """
        Execute the complete transfer flow.
        
        This is the main orchestration method that ensures atomic debit+credit
        operations with proper rollback on failure.
        
        Args:
            transaction_id: ID of transfer to execute
            
        Returns:
            Tuple of (success, error_message)
        """
        transfer = self.transfers.get(transaction_id)
        if not transfer:
            return False, "Transfer not found"
            
        try:
            # Step 1: Validate request
            if not self._validate_transfer(transfer):
                return False, transfer.error_message
                
            # Step 2: Execute debit
            if not self._execute_debit(transfer):
                return False, transfer.error_message
                
            # Step 3: Execute credit
            if not self._execute_credit(transfer):
                # Debit succeeded but credit failed - MUST rollback
                self._rollback_transfer(transfer)
                return False, transfer.error_message
                
            # Step 4: Mark as completed (only after BOTH operations confirmed)
            if not self._complete_transfer(transfer):
                return False, "Failed to complete transfer"
                
            return True, None
            
        except Exception as e:
            logger.exception(
                "Unexpected error during transfer execution",
                extra={"transaction_id": transaction_id}
            )
            
            # Attempt rollback if debit was completed
            if transfer.debit_completed_at:
                self._rollback_transfer(transfer)
                
            transfer.error_code = TransferErrorCode.UNKNOWN_ERROR
            transfer.error_message = str(e)
            self.state_machine.validate_transition(
                transfer, 
                TransferState.FAILED,
                reason="Unexpected error"
            )
            
            return False, str(e)
            
    def _validate_transfer(self, transfer: Transfer) -> bool:
        """Validate transfer request"""
        self.state_machine.validate_transition(
            transfer,
            TransferState.VALIDATING,
            reason="Starting validation"
        )
        
        # Basic validation
        if transfer.request.amount <= 0:
            transfer.error_code = TransferErrorCode.VALIDATION_ERROR
            transfer.error_message = "Amount must be positive"
            self.state_machine.validate_transition(
                transfer,
                TransferState.FAILED,
                reason="Invalid amount"
            )
            return False
            
        if transfer.request.source_account == transfer.request.destination_account:
            transfer.error_code = TransferErrorCode.VALIDATION_ERROR
            transfer.error_message = "Source and destination accounts cannot be the same"
            self.state_machine.validate_transition(
                transfer,
                TransferState.FAILED,
                reason="Same account transfer"
            )
            return False
            
        # Transition to pending
        self.state_machine.validate_transition(
            transfer,
            TransferState.PENDING,
            reason="Validation passed"
        )
        
        return True
        
    def _execute_debit(self, transfer: Transfer) -> bool:
        """
        Execute debit operation on source account.
        
        Returns:
            True if debit successful, False otherwise
        """
        self.state_machine.validate_transition(
            transfer,
            TransferState.DEBIT_PROCESSING,
            reason="Starting debit operation"
        )
        
        # Call ledger service
        status, error_msg = self.ledger.debit_account(
            transaction_id=transfer.transaction_id,
            account_id=transfer.request.source_account,
            amount=transfer.request.amount
        )
        
        # Log ledger operation
        audit_logger.log_ledger_operation(
            transaction_id=transfer.transaction_id,
            operation="debit",
            account=transfer.request.source_account,
            amount=transfer.request.amount,
            status=status.value,
            error=error_msg
        )
        
        if status.value == "success":
            # Record debit completion
            transfer.debit_completed_at = datetime.utcnow()
            transfer.ledger_debit_ref = f"DR-{transfer.transaction_id}"
            
            self.state_machine.validate_transition(
                transfer,
                TransferState.DEBIT_COMPLETED,
                reason="Debit successful"
            )
            
            logger.info(
                "Debit completed",
                extra={"transaction_id": transfer.transaction_id}
            )
            
            return True
        else:
            # Debit failed
            transfer.error_code = TransferErrorCode.DEBIT_FAILED
            transfer.error_message = error_msg or "Debit operation failed"
            
            self.state_machine.validate_transition(
                transfer,
                TransferState.FAILED,
                reason=f"Debit failed: {error_msg}"
            )
            
            audit_logger.log_transfer_failed(
                transaction_id=transfer.transaction_id,
                error_code=transfer.error_code.value,
                error_message=transfer.error_message,
                current_state=transfer.state.value
            )
            
            return False
            
    def _execute_credit(self, transfer: Transfer) -> bool:
        """
        Execute credit operation on destination account.
        
        Returns:
            True if credit successful, False otherwise
        """
        self.state_machine.validate_transition(
            transfer,
            TransferState.CREDIT_PROCESSING,
            reason="Starting credit operation"
        )
        
        # Call ledger service
        status, error_msg = self.ledger.credit_account(
            transaction_id=transfer.transaction_id,
            account_id=transfer.request.destination_account,
            amount=transfer.request.amount
        )
        
        # Log ledger operation
        audit_logger.log_ledger_operation(
            transaction_id=transfer.transaction_id,
            operation="credit",
            account=transfer.request.destination_account,
            amount=transfer.request.amount,
            status=status.value,
            error=error_msg
        )
        
        if status.value == "success":
            # Record credit completion
            transfer.credit_completed_at = datetime.utcnow()
            transfer.ledger_credit_ref = f"CR-{transfer.transaction_id}"
            
            logger.info(
                "Credit completed",
                extra={"transaction_id": transfer.transaction_id}
            )
            
            return True
        else:
            # Credit failed - this is critical as debit already succeeded
            transfer.error_code = TransferErrorCode.CREDIT_FAILED
            transfer.error_message = error_msg or "Credit operation failed"
            
            logger.error(
                "Credit failed after successful debit - rollback required",
                extra={
                    "transaction_id": transfer.transaction_id,
                    "error": error_msg
                }
            )
            
            return False
            
    def _complete_transfer(self, transfer: Transfer) -> bool:
        """
        Mark transfer as completed.
        
        CRITICAL: This method enforces that we can only mark a transfer as
        completed if BOTH debit and credit operations are confirmed.
        This prevents the false success bug.
        
        Returns:
            True if completion successful, False otherwise
        """
        # Validate completion conditions via state machine
        if not self.state_machine.can_complete(transfer):
            logger.error(
                "Cannot complete transfer - completion conditions not met",
                extra={"transaction_id": transfer.transaction_id}
            )
            return False
            
        # Transition to completed state
        success = self.state_machine.validate_transition(
            transfer,
            TransferState.COMPLETED,
            reason="Both debit and credit confirmed"
        )
        
        if success:
            transfer.completed_at = datetime.utcnow()
            duration_ms = (
                transfer.completed_at - transfer.created_at
            ).total_seconds() * 1000
            
            audit_logger.log_transfer_completed(
                transaction_id=transfer.transaction_id,
                duration_ms=duration_ms
            )
            
            logger.info(
                "Transfer completed successfully",
                extra={
                    "transaction_id": transfer.transaction_id,
                    "duration_ms": duration_ms
                }
            )
            
        return success
        
    def _rollback_transfer(self, transfer: Transfer) -> bool:
        """
        Rollback a partially completed transfer.
        
        Called when credit fails after debit succeeds.
        
        Returns:
            True if rollback successful, False otherwise
        """
        logger.warning(
            "Initiating transfer rollback",
            extra={"transaction_id": transfer.transaction_id}
        )
        
        self.state_machine.validate_transition(
            transfer,
            TransferState.ROLLING_BACK,
            reason="Partial failure - rolling back"
        )
        
        # Execute rollback via ledger
        status, error_msg = self.ledger.rollback_transaction(
            transfer.transaction_id
        )
        
        rollback_success = status.value == "success"
        
        audit_logger.log_rollback(
            transaction_id=transfer.transaction_id,
            reason=transfer.error_message or "Partial failure",
            status="success" if rollback_success else "failed"
        )
        
        if not rollback_success:
            logger.critical(
                "ROLLBACK FAILED - Manual intervention required",
                extra={
                    "transaction_id": transfer.transaction_id,
                    "error": error_msg
                }
            )
            transfer.error_code = TransferErrorCode.ROLLBACK_FAILED
            
        # Mark as failed regardless of rollback outcome
        self.state_machine.validate_transition(
            transfer,
            TransferState.FAILED,
            reason="Rollback completed" if rollback_success else "Rollback failed"
        )
        
        transfer.failed_at = datetime.utcnow()
        
        audit_logger.log_transfer_failed(
            transaction_id=transfer.transaction_id,
            error_code=transfer.error_code.value,
            error_message=transfer.error_message,
            current_state=transfer.state.value
        )
        
        return rollback_success
        
    def get_transfer_status(self, transaction_id: str) -> Optional[Transfer]:
        """Get current status of a transfer"""
        return self.transfers.get(transaction_id)
        
    @staticmethod
    def _generate_transaction_id() -> str:
        """Generate unique transaction identifier"""
        return f"TXN-{uuid.uuid4().hex[:12].upper()}"
