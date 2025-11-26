"""
Transfer Controller - API endpoint handler
Exposes transfer operations to frontend/API layer
"""

from typing import Dict, Any
from src.services.transfer_service import TransferService
from src.models.transfer import TransferRequest, TransferState
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TransferController:
    """
    Controller for transfer API endpoints.
    Handles request validation and response formatting.
    """
    
    def __init__(self, transfer_service: TransferService):
        """
        Initialize controller.
        
        Args:
            transfer_service: Transfer service instance
        """
        self.service = transfer_service
        
    def create_transfer(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle transfer creation request.
        
        Args:
            request_data: Transfer request payload
            
        Returns:
            Response with transaction ID and status
        """
        try:
            # Parse request
            request = TransferRequest(
                source_account=request_data["source_account"],
                destination_account=request_data["destination_account"],
                amount=float(request_data["amount"]),
                currency=request_data.get("currency", "USD"),
                reference=request_data.get("reference"),
                idempotency_key=request_data.get("idempotency_key")
            )
            
            # Initiate transfer
            transfer = self.service.initiate_transfer(request)
            
            # Execute transfer synchronously
            success, error_msg = self.service.execute_transfer(transfer.transaction_id)
            
            # Format response based on actual state
            # CRITICAL: Only return success if transfer is in COMPLETED state
            if success and transfer.state == TransferState.COMPLETED:
                return {
                    "status": "success",
                    "transaction_id": transfer.transaction_id,
                    "message": "Transfer completed successfully",
                    "state": transfer.state.value,
                    "completed_at": transfer.completed_at.isoformat() if transfer.completed_at else None
                }
            elif transfer.state in [TransferState.FAILED, TransferState.TIMEOUT]:
                return {
                    "status": "failed",
                    "transaction_id": transfer.transaction_id,
                    "message": error_msg or transfer.error_message,
                    "error_code": transfer.error_code.value if transfer.error_code else None,
                    "state": transfer.state.value
                }
            else:
                # Transfer still in progress or unknown state
                return {
                    "status": "pending",
                    "transaction_id": transfer.transaction_id,
                    "message": "Transfer is being processed",
                    "state": transfer.state.value
                }
                
        except KeyError as e:
            logger.error(f"Missing required field: {e}")
            return {
                "status": "error",
                "message": f"Missing required field: {e}"
            }
        except ValueError as e:
            logger.error(f"Invalid value: {e}")
            return {
                "status": "error",
                "message": f"Invalid value: {e}"
            }
        except Exception as e:
            logger.exception("Unexpected error in create_transfer")
            return {
                "status": "error",
                "message": "Internal server error"
            }
            
    def get_transfer_status(self, transaction_id: str) -> Dict[str, Any]:
        """
        Get current status of a transfer.
        
        Args:
            transaction_id: Transaction ID to query
            
        Returns:
            Transfer status response
        """
        transfer = self.service.get_transfer_status(transaction_id)
        
        if not transfer:
            return {
                "status": "error",
                "message": "Transfer not found"
            }
            
        response = {
            "transaction_id": transfer.transaction_id,
            "state": transfer.state.value,
            "created_at": transfer.created_at.isoformat(),
            "updated_at": transfer.updated_at.isoformat(),
            "source_account": transfer.request.source_account,
            "destination_account": transfer.request.destination_account,
            "amount": transfer.request.amount,
            "currency": transfer.request.currency
        }
        
        # Add completion/failure details
        if transfer.state == TransferState.COMPLETED:
            response["status"] = "success"
            response["completed_at"] = transfer.completed_at.isoformat()
        elif transfer.state in [TransferState.FAILED, TransferState.TIMEOUT]:
            response["status"] = "failed"
            response["error_code"] = transfer.error_code.value if transfer.error_code else None
            response["error_message"] = transfer.error_message
            response["failed_at"] = transfer.failed_at.isoformat() if transfer.failed_at else None
        else:
            response["status"] = "pending"
            
        return response
