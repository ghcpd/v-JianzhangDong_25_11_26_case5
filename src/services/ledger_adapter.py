"""
Ledger Adapter - Abstraction layer for ledger operations
Wraps the mock ledger service and provides error handling
"""

from typing import Tuple, Optional
from mocks.mock_ledger_service import MockLedgerService, LedgerStatus
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LedgerAdapter:
    """
    Adapter for ledger service operations.
    Provides abstraction and error handling for ledger interactions.
    """
    
    def __init__(self, ledger_service: MockLedgerService):
        """
        Initialize ledger adapter.
        
        Args:
            ledger_service: Mock ledger service instance
        """
        self.ledger = ledger_service
        
    def debit_account(self, transaction_id: str, account_id: str, 
                     amount: float) -> Tuple[LedgerStatus, Optional[str]]:
        """
        Debit funds from account.
        
        Args:
            transaction_id: Unique transaction identifier
            account_id: Account to debit
            amount: Amount to debit
            
        Returns:
            Tuple of (status, error_message)
        """
        try:
            status, error_msg = self.ledger.debit_account(
                transaction_id=transaction_id,
                account_id=account_id,
                amount=amount
            )
            
            return status, error_msg
            
        except Exception as e:
            logger.exception(
                "Ledger debit operation failed with exception",
                extra={
                    "transaction_id": transaction_id,
                    "account_id": account_id
                }
            )
            return LedgerStatus.FAILED, f"Debit exception: {str(e)}"
            
    def credit_account(self, transaction_id: str, account_id: str, 
                      amount: float) -> Tuple[LedgerStatus, Optional[str]]:
        """
        Credit funds to account.
        
        Args:
            transaction_id: Unique transaction identifier
            account_id: Account to credit
            amount: Amount to credit
            
        Returns:
            Tuple of (status, error_message)
        """
        try:
            status, error_msg = self.ledger.credit_account(
                transaction_id=transaction_id,
                account_id=account_id,
                amount=amount
            )
            
            return status, error_msg
            
        except Exception as e:
            logger.exception(
                "Ledger credit operation failed with exception",
                extra={
                    "transaction_id": transaction_id,
                    "account_id": account_id
                }
            )
            return LedgerStatus.FAILED, f"Credit exception: {str(e)}"
            
    def rollback_transaction(self, transaction_id: str) -> Tuple[LedgerStatus, Optional[str]]:
        """
        Rollback a transaction.
        
        Args:
            transaction_id: Transaction to rollback
            
        Returns:
            Tuple of (status, error_message)
        """
        try:
            status, error_msg = self.ledger.rollback_transaction(transaction_id)
            return status, error_msg
            
        except Exception as e:
            logger.exception(
                "Ledger rollback operation failed with exception",
                extra={"transaction_id": transaction_id}
            )
            return LedgerStatus.FAILED, f"Rollback exception: {str(e)}"
            
    def verify_transaction_complete(self, transaction_id: str) -> bool:
        """
        Verify that both debit and credit operations completed successfully.
        
        This is a critical verification step that prevents false success scenarios.
        
        Args:
            transaction_id: Transaction to verify
            
        Returns:
            True if both operations confirmed, False otherwise
        """
        return self.ledger.is_transaction_complete(transaction_id)
