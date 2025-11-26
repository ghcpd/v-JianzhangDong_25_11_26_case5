"""
Transfer Service

Core business logic for initiating and processing transfers.
Orchestrates the interaction between API layer, state machine, and ledger service.
"""

import asyncio
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
import logging

from src.models import (
    Transfer, TransferState, AuditLog,
    store_transfer, get_transfer, get_transfer_by_correlation_id, store_audit_log
)
from mocks.mock_ledger_service import LedgerCallback, get_mock_ledger

logger = logging.getLogger(__name__)


class TransferService:
    """
    Service for managing transfers.
    
    Responsibilities:
    - Create and initialize transfers
    - Process transfers through state machine
    - Interact with ledger service
    - Record audit logs
    - Handle failures and compensation
    """
    
    def __init__(self):
        self.ledger = get_mock_ledger()
        self.pending_transfers: Dict[uuid.UUID, Transfer] = {}
        self.worker_tasks: Dict[uuid.UUID, asyncio.Task] = {}
    
    async def initiate_transfer(
        self,
        sender_account: str,
        recipient_account: str,
        amount: Decimal,
        timeout_seconds: int = 30
    ) -> Transfer:
        """
        Initiate a new transfer request.
        
        This creates the Transfer record in INITIATED state and queues it for processing.
        
        Args:
            sender_account: Sender's account identifier
            recipient_account: Recipient's account identifier
            amount: Amount to transfer
            timeout_seconds: Max time to wait for completion (default 30s)
        
        Returns:
            Transfer object (status = INITIATED)
        """
        # Create transfer record
        transfer = Transfer.create(
            sender_account=sender_account,
            recipient_account=recipient_account,
            amount=amount,
            timeout_seconds=timeout_seconds
        )
        
        # Store transfer
        store_transfer(transfer)
        
        # Record audit log
        await self._log_audit(
            transfer.correlation_id,
            step='transfer_initiated',
            actor='api_controller',
            details={
                'transfer_id': str(transfer.id),
                'amount': str(transfer.amount),
                'currency': 'USD'
            },
            result='success'
        )
        
        logger.info(
            f"Transfer initiated: correlation_id={transfer.correlation_id}, "
            f"transfer_id={transfer.id}, amount={amount}"
        )
        
        return transfer
    
    async def queue_worker_task(self, transfer_id: uuid.UUID) -> None:
        """
        Queue a transfer for async processing by the worker.
        
        This starts a background task that will:
        1. Call ledger.post_debit() and wait for callback
        2. Call ledger.post_credit() and wait for callback
        3. Update transfer state at each step
        4. Handle failures and compensation
        """
        # Check if task already running
        if transfer_id in self.worker_tasks:
            logger.warning(f"Worker task already running for {transfer_id}")
            return
        
        # Create and store task
        task = asyncio.create_task(self._process_transfer(transfer_id))
        self.worker_tasks[transfer_id] = task
    
    async def _process_transfer(self, transfer_id: uuid.UUID) -> None:
        """
        Worker coroutine that processes a transfer through the state machine.
        
        This is the main async flow:
        1. INITIATED → PENDING_DEBIT → (wait for debit callback)
        2. DEBIT_POSTED → PENDING_CREDIT → (wait for credit callback)
        3. SUCCESS (or FAILED with potential reverse debit)
        """
        transfer = get_transfer(transfer_id)
        if not transfer:
            logger.error(f"Transfer not found: {transfer_id}")
            return
        
        try:
            # Step 1: Transition to PENDING_DEBIT
            if not transfer.transition_to(TransferState.PENDING_DEBIT):
                raise ValueError(f"Cannot transition from {transfer.state} to PENDING_DEBIT")
            
            store_transfer(transfer)
            
            await self._log_audit(
                transfer.correlation_id,
                step='state_transition',
                actor='transfer_worker',
                details={
                    'transfer_id': str(transfer.id),
                    'state_from': TransferState.INITIATED.value,
                    'state_to': TransferState.PENDING_DEBIT.value,
                    'reason': 'Transfer queued for processing'
                },
                result='success'
            )
            
            # Step 2: Request debit from ledger
            debit_response = await self._request_debit(transfer)
            if not debit_response:
                # Debit request failed
                await self._transition_failed(
                    transfer,
                    reason='Debit request failed'
                )
                return
            
            # Step 3: Wait for debit callback (with timeout)
            debit_success = await self._wait_for_state(
                transfer_id,
                target_state=TransferState.DEBIT_POSTED,
                timeout_seconds=30
            )
            
            if not debit_success:
                # Debit callback timeout or failure
                await self._transition_failed(
                    transfer,
                    reason='Debit callback timeout or failure'
                )
                return
            
            # Refresh transfer state
            transfer = get_transfer(transfer_id)
            
            # Step 4: Transition to PENDING_CREDIT
            if not transfer.transition_to(TransferState.PENDING_CREDIT):
                raise ValueError(f"Cannot transition from {transfer.state} to PENDING_CREDIT")
            
            store_transfer(transfer)
            
            await self._log_audit(
                transfer.correlation_id,
                step='state_transition',
                actor='transfer_worker',
                details={
                    'transfer_id': str(transfer.id),
                    'state_from': TransferState.DEBIT_POSTED.value,
                    'state_to': TransferState.PENDING_CREDIT.value,
                    'reason': 'Debit confirmed, initiating credit'
                },
                result='success'
            )
            
            # Step 5: Request credit from ledger
            credit_response = await self._request_credit(transfer)
            if not credit_response:
                # Credit request failed - must compensate (reverse debit)
                await self._initiate_reverse_debit(transfer)
                await self._transition_failed(
                    transfer,
                    reason='Credit request failed; reverse debit initiated'
                )
                return
            
            # Step 6: Wait for credit callback (with timeout)
            credit_success = await self._wait_for_state(
                transfer_id,
                target_state=TransferState.SUCCESS,
                timeout_seconds=30
            )
            
            if not credit_success:
                # Credit callback timeout or failure - must compensate
                await self._initiate_reverse_debit(transfer)
                await self._transition_failed(
                    transfer,
                    reason='Credit callback timeout or failure; reverse debit initiated'
                )
                return
            
            # Success!
            transfer = get_transfer(transfer_id)
            await self._log_audit(
                transfer.correlation_id,
                step='transfer_completed',
                actor='transfer_worker',
                details={
                    'transfer_id': str(transfer.id),
                    'state': TransferState.SUCCESS.value,
                    'reason': 'Both debit and credit confirmed',
                    'ledger_debit_txn_id': transfer.ledger_debit_txn_id,
                    'ledger_credit_txn_id': transfer.ledger_credit_txn_id,
                    'amount': str(transfer.amount)
                },
                result='success'
            )
            
            logger.info(
                f"Transfer completed successfully: correlation_id={transfer.correlation_id}, "
                f"transfer_id={transfer.id}, amount={transfer.amount}"
            )
        
        except Exception as e:
            logger.error(
                f"Transfer processing failed: correlation_id={transfer.correlation_id}, "
                f"transfer_id={transfer_id}, error={e}",
                exc_info=True
            )
            await self._transition_failed(transfer, reason=str(e))
        
        finally:
            # Clean up task reference
            if transfer_id in self.worker_tasks:
                del self.worker_tasks[transfer_id]
    
    async def _request_debit(self, transfer: Transfer) -> bool:
        """
        Request a debit from the ledger service.
        
        Returns True if request was submitted successfully (callback will follow).
        Returns False if request itself failed.
        """
        try:
            callback_url = f"http://backend/webhooks/ledger/callback/{transfer.id}"
            
            response = await self.ledger.post_debit(
                txn_id=str(transfer.id),
                idempotency_key=transfer.idempotency_key,
                amount=transfer.amount,
                callback_url=callback_url
            )
            
            # Store ledger transaction ID
            transfer.ledger_debit_txn_id = response.ledger_txn_id
            store_transfer(transfer)
            
            await self._log_audit(
                transfer.correlation_id,
                step='ledger_debit_request',
                actor='transfer_worker',
                details={
                    'transfer_id': str(transfer.id),
                    'operation_type': 'debit',
                    'amount': str(transfer.amount),
                    'currency': 'USD',
                    'ledger_txn_id': response.ledger_txn_id,
                    'duration_ms': 100  # Simulated
                },
                result='success'
            )
            
            logger.info(
                f"Debit request submitted: correlation_id={transfer.correlation_id}, "
                f"ledger_txn_id={response.ledger_txn_id}"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Debit request failed: {e}")
            await self._log_audit(
                transfer.correlation_id,
                step='ledger_debit_request',
                actor='transfer_worker',
                details={
                    'transfer_id': str(transfer.id),
                    'operation_type': 'debit',
                    'amount': str(transfer.amount),
                    'error_code': 'REQUEST_FAILED'
                },
                result='failure',
                error=str(e)
            )
            return False
    
    async def _request_credit(self, transfer: Transfer) -> bool:
        """
        Request a credit from the ledger service.
        
        Returns True if request was submitted successfully (callback will follow).
        Returns False if request itself failed.
        """
        try:
            callback_url = f"http://backend/webhooks/ledger/callback/{transfer.id}"
            
            response = await self.ledger.post_credit(
                txn_id=str(transfer.id),
                idempotency_key=str(uuid.uuid4()),  # New idempotency key for credit
                amount=transfer.amount,
                callback_url=callback_url
            )
            
            # Store ledger transaction ID
            transfer.ledger_credit_txn_id = response.ledger_txn_id
            store_transfer(transfer)
            
            await self._log_audit(
                transfer.correlation_id,
                step='ledger_credit_request',
                actor='transfer_worker',
                details={
                    'transfer_id': str(transfer.id),
                    'operation_type': 'credit',
                    'amount': str(transfer.amount),
                    'currency': 'USD',
                    'ledger_txn_id': response.ledger_txn_id,
                    'duration_ms': 100
                },
                result='success'
            )
            
            logger.info(
                f"Credit request submitted: correlation_id={transfer.correlation_id}, "
                f"ledger_txn_id={response.ledger_txn_id}"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Credit request failed: {e}")
            await self._log_audit(
                transfer.correlation_id,
                step='ledger_credit_request',
                actor='transfer_worker',
                details={
                    'transfer_id': str(transfer.id),
                    'operation_type': 'credit',
                    'amount': str(transfer.amount),
                    'error_code': 'REQUEST_FAILED'
                },
                result='failure',
                error=str(e)
            )
            return False
    
    async def _initiate_reverse_debit(self, transfer: Transfer) -> bool:
        """
        Initiate a reverse debit (compensating transaction) to refund a failed credit.
        
        This creates a new transfer record to represent the reverse operation.
        """
        try:
            # Create reverse transaction
            reverse_txn_id = uuid.uuid4()
            transfer.reverse_txn_id = str(reverse_txn_id)
            
            reverse_callback_url = f"http://backend/webhooks/ledger/callback/{reverse_txn_id}"
            
            response = await self.ledger.post_reverse_debit(
                txn_id=str(reverse_txn_id),
                idempotency_key=str(uuid.uuid4()),
                amount=transfer.amount,
                callback_url=reverse_callback_url
            )
            
            store_transfer(transfer)
            
            await self._log_audit(
                transfer.correlation_id,
                step='reverse_debit_initiated',
                actor='transfer_worker',
                details={
                    'transfer_id': str(transfer.id),
                    'reverse_txn_id': str(reverse_txn_id),
                    'amount': str(transfer.amount),
                    'reason': 'Credit operation failed; compensating debit initiated'
                },
                result='success'
            )
            
            logger.info(
                f"Reverse debit initiated: correlation_id={transfer.correlation_id}, "
                f"reverse_txn_id={reverse_txn_id}"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Reverse debit initiation failed: {e}")
            await self._log_audit(
                transfer.correlation_id,
                step='reverse_debit_initiated',
                actor='transfer_worker',
                details={
                    'transfer_id': str(transfer.id),
                    'error_code': 'REVERSE_FAILED'
                },
                result='failure',
                error=str(e)
            )
            return False
    
    async def _wait_for_state(
        self,
        transfer_id: uuid.UUID,
        target_state: TransferState,
        timeout_seconds: int
    ) -> bool:
        """
        Wait for a transfer to reach the target state (via callback).
        
        Polls the transfer state until it reaches target_state or timeout.
        
        Returns True if target_state reached, False if timeout.
        """
        start_time = datetime.utcnow()
        
        while True:
            transfer = get_transfer(transfer_id)
            if not transfer:
                logger.error(f"Transfer not found: {transfer_id}")
                return False
            
            # Check if target state reached
            if transfer.state == target_state:
                return True
            
            # Check if timeout exceeded
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > timeout_seconds:
                logger.warning(
                    f"State wait timeout: transfer_id={transfer_id}, "
                    f"target={target_state.value}, current={transfer.state.value}, "
                    f"elapsed={elapsed:.1f}s"
                )
                return False
            
            # Check if in error state
            if transfer.state == TransferState.FAILED:
                logger.error(f"Transfer failed while waiting: {transfer_id}")
                return False
            
            # Wait a bit before polling again
            await asyncio.sleep(0.1)
    
    async def handle_ledger_callback(self, callback: LedgerCallback) -> bool:
        """
        Handle a callback from the ledger service.
        
        This is called when the ledger posts a callback about debit/credit completion.
        Updates the transfer state based on the operation type and result.
        
        Returns True if callback was processed, False if not found/duplicate.
        """
        transfer_id = uuid.UUID(callback.transfer_id)
        transfer = get_transfer(transfer_id)
        
        if not transfer:
            logger.error(f"Callback received for unknown transfer: {transfer_id}")
            return False
        
        logger.info(
            f"Ledger callback received: transfer_id={transfer_id}, "
            f"operation={callback.operation_type}, status={callback.status.value}"
        )
        
        # Check for idempotency (already processed)
        existing_logs = [
            log for log in _get_audit_logs_for_transfer(transfer.correlation_id)
            if log.step == f"ledger_{callback.operation_type}_callback"
            and log.details.get('ledger_txn_id') == callback.ledger_txn_id
        ]
        if existing_logs:
            logger.info(f"Callback already processed (idempotent): {callback.ledger_txn_id}")
            return True  # Idempotent: already handled
        
        # Process based on operation type and status
        if callback.operation_type == 'debit':
            if callback.status.value == 'SUCCESS':
                success = transfer.transition_to(TransferState.DEBIT_POSTED)
                if success:
                    store_transfer(transfer)
                    await self._log_audit(
                        transfer.correlation_id,
                        step='ledger_debit_callback',
                        actor='callback_handler',
                        details={
                            'transfer_id': str(transfer.id),
                            'ledger_txn_id': callback.ledger_txn_id,
                            'operation_type': 'debit',
                            'ledger_status': 'SUCCESS',
                            'amount': str(callback.amount)
                        },
                        result='success'
                    )
                    await self._log_audit(
                        transfer.correlation_id,
                        step='state_transition',
                        actor='callback_handler',
                        details={
                            'transfer_id': str(transfer.id),
                            'state_from': TransferState.PENDING_DEBIT.value,
                            'state_to': TransferState.DEBIT_POSTED.value,
                            'reason': 'Ledger debit callback received successfully'
                        },
                        result='success'
                    )
                    logger.info(f"Debit confirmed: transfer_id={transfer_id}")
            else:
                # Debit failed
                success = transfer.transition_to(TransferState.FAILED)
                if success:
                    transfer.error_reason = f"Debit failed: {callback.reason}"
                    store_transfer(transfer)
                    await self._log_audit(
                        transfer.correlation_id,
                        step='ledger_debit_callback',
                        actor='callback_handler',
                        details={
                            'transfer_id': str(transfer.id),
                            'ledger_txn_id': callback.ledger_txn_id,
                            'operation_type': 'debit',
                            'ledger_status': callback.status.value,
                            'error_code': 'DEBIT_FAILED',
                            'error_message': callback.reason
                        },
                        result='failure'
                    )
                    logger.error(f"Debit failed: transfer_id={transfer_id}, reason={callback.reason}")
        
        elif callback.operation_type == 'credit':
            if callback.status.value == 'SUCCESS':
                success = transfer.transition_to(TransferState.SUCCESS)
                if success:
                    store_transfer(transfer)
                    await self._log_audit(
                        transfer.correlation_id,
                        step='ledger_credit_callback',
                        actor='callback_handler',
                        details={
                            'transfer_id': str(transfer.id),
                            'ledger_txn_id': callback.ledger_txn_id,
                            'operation_type': 'credit',
                            'ledger_status': 'SUCCESS',
                            'amount': str(callback.amount)
                        },
                        result='success'
                    )
                    await self._log_audit(
                        transfer.correlation_id,
                        step='state_transition',
                        actor='callback_handler',
                        details={
                            'transfer_id': str(transfer.id),
                            'state_from': TransferState.PENDING_CREDIT.value,
                            'state_to': TransferState.SUCCESS.value,
                            'reason': 'Ledger credit callback received successfully'
                        },
                        result='success'
                    )
                    logger.info(f"Credit confirmed: transfer_id={transfer_id}")
            else:
                # Credit failed - initiate reverse debit
                await self._initiate_reverse_debit(transfer)
                success = transfer.transition_to(TransferState.FAILED)
                if success:
                    transfer.error_reason = f"Credit failed: {callback.reason}"
                    store_transfer(transfer)
                    await self._log_audit(
                        transfer.correlation_id,
                        step='ledger_credit_callback',
                        actor='callback_handler',
                        details={
                            'transfer_id': str(transfer.id),
                            'ledger_txn_id': callback.ledger_txn_id,
                            'operation_type': 'credit',
                            'ledger_status': callback.status.value,
                            'error_code': 'CREDIT_FAILED',
                            'error_message': callback.reason
                        },
                        result='failure'
                    )
                    logger.error(f"Credit failed: transfer_id={transfer_id}, reason={callback.reason}")
        
        elif callback.operation_type == 'reverse_debit':
            # Just log the reverse debit completion
            await self._log_audit(
                transfer.correlation_id,
                step='reverse_debit_callback',
                actor='callback_handler',
                details={
                    'transfer_id': str(transfer.id),
                    'ledger_txn_id': callback.ledger_txn_id,
                    'operation_type': 'reverse_debit',
                    'ledger_status': callback.status.value,
                    'amount': str(callback.amount)
                },
                result='success' if callback.status.value == 'SUCCESS' else 'failure'
            )
        
        return True
    
    async def _transition_failed(self, transfer: Transfer, reason: str) -> None:
        """Transition transfer to FAILED state and log"""
        if transfer.state != TransferState.FAILED:
            transfer.transition_to(TransferState.FAILED)
            transfer.error_reason = reason
            store_transfer(transfer)
            
            await self._log_audit(
                transfer.correlation_id,
                step='state_transition',
                actor='transfer_worker',
                details={
                    'transfer_id': str(transfer.id),
                    'state_from': transfer.state.value,
                    'state_to': TransferState.FAILED.value,
                    'reason': reason
                },
                result='failure'
            )
    
    async def _log_audit(
        self,
        correlation_id: str,
        step: str,
        actor: str,
        details: Dict[str, Any],
        result: str = 'success',
        error: Optional[str] = None
    ) -> None:
        """Log an audit entry"""
        log = AuditLog(
            correlation_id=correlation_id,
            timestamp=datetime.utcnow(),
            step=step,
            actor=actor,
            details=details,
            result=result,
            error=error
        )
        store_audit_log(log)
        logger.debug(f"Audit log: {log.to_dict()}")
    
    def get_transfer_status(self, correlation_id: str) -> Optional[Dict[str, Any]]:
        """Get current transfer status by correlation ID"""
        transfer = get_transfer_by_correlation_id(correlation_id)
        if not transfer:
            return None
        return transfer.to_dict()


# Global instance
_service: Optional[TransferService] = None


def get_transfer_service() -> TransferService:
    """Get or create the global transfer service instance"""
    global _service
    if _service is None:
        _service = TransferService()
    return _service


def _get_audit_logs_for_transfer(correlation_id: str) -> list:
    """Get all audit logs for a transfer (for internal use)"""
    from src.models import get_audit_logs_for_correlation_id
    return get_audit_logs_for_correlation_id(correlation_id)
