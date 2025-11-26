"""
Transfer API Controller

HTTP endpoints for initiating and querying transfers.
Uses async FastAPI framework.
"""

from typing import Optional, Dict, Any
from decimal import Decimal
from dataclasses import dataclass
import logging

from src.transfer_service import get_transfer_service
from mocks.mock_ledger_service import LedgerCallback, LedgerOperationStatus

logger = logging.getLogger(__name__)


@dataclass
class TransferRequest:
    """Request body for initiating a transfer"""
    sender_account: str
    recipient_account: str
    amount: str  # As string to preserve precision
    
    def validate(self) -> tuple[bool, Optional[str]]:
        """Validate the request"""
        if not self.sender_account or len(self.sender_account) < 1:
            return False, "sender_account is required"
        if not self.recipient_account or len(self.recipient_account) < 1:
            return False, "recipient_account is required"
        try:
            amount = Decimal(self.amount)
            if amount <= 0:
                return False, "amount must be positive"
        except:
            return False, "amount must be a valid decimal number"
        return True, None


@dataclass
class TransferResponse:
    """Response body for transfer API"""
    correlation_id: str
    transfer_id: str
    status: str  # 'IN_PROGRESS' or 'INITIATED'
    status_url: str
    message: str = "Transfer initiated and processing"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'correlation_id': self.correlation_id,
            'transfer_id': self.transfer_id,
            'status': self.status,
            'status_url': self.status_url,
            'message': self.message
        }


@dataclass
class TransferStatusResponse:
    """Response body for status query"""
    correlation_id: str
    transfer_id: str
    status: str
    sender_account: str
    recipient_account: str
    amount: str
    error_reason: Optional[str] = None
    ledger_debit_txn_id: Optional[str] = None
    ledger_credit_txn_id: Optional[str] = None
    reverse_txn_id: Optional[str] = None
    created_at: str = None
    updated_at: str = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'correlation_id': self.correlation_id,
            'transfer_id': self.transfer_id,
            'status': self.status,
            'sender_account': self.sender_account,
            'recipient_account': self.recipient_account,
            'amount': self.amount,
            'error_reason': self.error_reason,
            'ledger_debit_txn_id': self.ledger_debit_txn_id,
            'ledger_credit_txn_id': self.ledger_credit_txn_id,
            'reverse_txn_id': self.reverse_txn_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


@dataclass
class ErrorResponse:
    """Error response body"""
    error: str
    details: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'error': self.error,
            'details': self.details
        }


class TransferController:
    """
    HTTP API controller for transfer endpoints.
    
    In a real application, this would be decorated with FastAPI @app.post(), etc.
    Here we provide the handler methods that can be used by a web framework.
    """
    
    def __init__(self):
        self.service = get_transfer_service()
    
    async def initiate_transfer(self, request: TransferRequest) -> tuple[Dict[str, Any], int]:
        """
        Initiate a new transfer.
        
        HTTP: POST /transfers
        Response: 202 ACCEPTED (NOT 200 OK!)
        
        This endpoint returns immediately while the transfer is processed asynchronously.
        Use the status_url to poll for completion.
        """
        # Validate request
        is_valid, error_msg = request.validate()
        if not is_valid:
            return ErrorResponse(error='Invalid request', details=error_msg).to_dict(), 400
        
        try:
            # Create and initiate transfer
            transfer = await self.service.initiate_transfer(
                sender_account=request.sender_account,
                recipient_account=request.recipient_account,
                amount=Decimal(request.amount),
                timeout_seconds=30
            )
            
            # Queue async processing
            await self.service.queue_worker_task(transfer.id)
            
            # Return 202 ACCEPTED (not 200 OK!)
            response = TransferResponse(
                correlation_id=transfer.correlation_id,
                transfer_id=str(transfer.id),
                status='IN_PROGRESS',
                status_url=f'/transfers/{transfer.correlation_id}'
            )
            
            logger.info(f"Transfer initiated: {transfer.correlation_id}")
            return response.to_dict(), 202
        
        except Exception as e:
            logger.error(f"Failed to initiate transfer: {e}", exc_info=True)
            return ErrorResponse(
                error='Failed to initiate transfer',
                details=str(e)
            ).to_dict(), 500
    
    async def get_transfer_status(self, correlation_id: str) -> tuple[Dict[str, Any], int]:
        """
        Get transfer status by correlation ID.
        
        HTTP: GET /transfers/{correlation_id}
        Response: 200 OK with current status
        
        Status values:
        - 'IN_PROGRESS': Transfer is being processed
        - 'SUCCESS': Transfer completed successfully
        - 'FAILED': Transfer failed
        - 'NOT_FOUND': No transfer with this ID
        """
        try:
            status_dict = self.service.get_transfer_status(correlation_id)
            
            if not status_dict:
                return ErrorResponse(
                    error='Transfer not found',
                    details=f"No transfer with correlation_id {correlation_id}"
                ).to_dict(), 404
            
            # Convert to response format
            response = TransferStatusResponse(
                correlation_id=correlation_id,
                transfer_id=status_dict['id'],
                status=status_dict['state'],
                sender_account=status_dict['sender_account'],
                recipient_account=status_dict['recipient_account'],
                amount=status_dict['amount'],
                error_reason=status_dict.get('error_reason'),
                ledger_debit_txn_id=status_dict.get('ledger_debit_txn_id'),
                ledger_credit_txn_id=status_dict.get('ledger_credit_txn_id'),
                reverse_txn_id=status_dict.get('reverse_txn_id'),
                created_at=status_dict.get('created_at'),
                updated_at=status_dict.get('updated_at')
            )
            
            return response.to_dict(), 200
        
        except Exception as e:
            logger.error(f"Failed to get transfer status: {e}", exc_info=True)
            return ErrorResponse(
                error='Failed to get transfer status',
                details=str(e)
            ).to_dict(), 500
    
    async def handle_ledger_callback(
        self,
        transfer_id: str,
        operation_type: str,
        status: str,
        ledger_txn_id: str,
        amount: str,
        reason: Optional[str] = None
    ) -> tuple[Dict[str, Any], int]:
        """
        Handle callback from ledger service.
        
        HTTP: POST /webhooks/ledger/callback/{transfer_id}
        Body:
        {
            "operation_type": "debit" or "credit" or "reverse_debit",
            "status": "SUCCESS" or "FAILED" or "TIMEOUT",
            "ledger_txn_id": "LEDGER-123",
            "amount": "100.50",
            "reason": "error message if failed"
        }
        Response: 200 OK (or 202 for idempotent/duplicate calls)
        
        This endpoint MUST return 200 OK to acknowledge receipt.
        If 200 is not returned within timeout, ledger will retry.
        """
        try:
            # Parse status enum
            try:
                status_enum = LedgerOperationStatus(status)
            except ValueError:
                return ErrorResponse(
                    error='Invalid status value',
                    details=f"status must be one of: {', '.join([s.value for s in LedgerOperationStatus])}"
                ).to_dict(), 400
            
            # Create callback object
            callback = LedgerCallback(
                transfer_id=transfer_id,
                operation_type=operation_type,
                status=status_enum,
                ledger_txn_id=ledger_txn_id,
                amount=Decimal(amount),
                reason=reason
            )
            
            # Handle callback
            success = await self.service.handle_ledger_callback(callback)
            
            if success:
                logger.info(
                    f"Ledger callback processed: transfer_id={transfer_id}, "
                    f"operation={operation_type}, status={status}"
                )
                return {'status': 'processed'}, 200
            else:
                # Callback not found or duplicate (idempotent)
                logger.warning(
                    f"Ledger callback not processed (unknown transfer): transfer_id={transfer_id}"
                )
                return {'status': 'unknown_transfer'}, 202
        
        except Exception as e:
            logger.error(f"Failed to handle ledger callback: {e}", exc_info=True)
            # Return 200 anyway to stop ledger retry loop
            # Real systems would queue for manual investigation
            return {'status': 'error_logged'}, 200


# Global instance
_controller: Optional[TransferController] = None


def get_transfer_controller() -> TransferController:
    """Get or create the global transfer controller instance"""
    global _controller
    if _controller is None:
        _controller = TransferController()
    return _controller
