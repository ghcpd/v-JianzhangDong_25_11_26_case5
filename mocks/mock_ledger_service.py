"""
Mock Ledger Service for Testing Transfer Flow
Simulates core banking ledger operations without connecting to production systems.
"""

import time
import random
from enum import Enum
from typing import Dict, Optional, Tuple
from datetime import datetime


class LedgerOperation(Enum):
    """Ledger operation types"""
    DEBIT = "debit"
    CREDIT = "credit"
    ROLLBACK = "rollback"


class LedgerStatus(Enum):
    """Ledger transaction status"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class MockLedgerService:
    """
    Simulated core ledger service that mimics real banking operations.
    Supports configurable failure modes for testing various scenarios.
    """
    
    def __init__(self, failure_mode: Optional[str] = None, delay_ms: int = 100):
        """
        Initialize mock ledger service.
        
        Args:
            failure_mode: Optional failure scenario ('debit_fail', 'credit_fail', 
                         'timeout', 'network_error', 'partial_success')
            delay_ms: Simulated network/processing delay in milliseconds
        """
        self.failure_mode = failure_mode
        self.delay_ms = delay_ms
        self.transactions: Dict[str, Dict] = {}
        self.account_balances: Dict[str, float] = {}
        
    def set_account_balance(self, account_id: str, balance: float) -> None:
        """Set initial account balance for testing"""
        self.account_balances[account_id] = balance
        
    def get_account_balance(self, account_id: str) -> float:
        """Get current account balance"""
        return self.account_balances.get(account_id, 0.0)
        
    def _simulate_delay(self) -> None:
        """Simulate network/processing delay"""
        time.sleep(self.delay_ms / 1000.0)
        
    def _should_fail(self, operation: str) -> bool:
        """Determine if operation should fail based on failure mode"""
        if self.failure_mode == f"{operation}_fail":
            return True
        if self.failure_mode == "random_fail":
            return random.random() < 0.3
        return False
        
    def debit_account(self, transaction_id: str, account_id: str, 
                     amount: float) -> Tuple[LedgerStatus, Optional[str]]:
        """
        Debit funds from source account.
        
        Args:
            transaction_id: Unique transaction identifier
            account_id: Source account to debit
            amount: Amount to debit
            
        Returns:
            Tuple of (status, error_message)
        """
        self._simulate_delay()
        
        # Check for timeout simulation
        if self.failure_mode == "timeout":
            time.sleep(5)  # Simulate timeout
            return LedgerStatus.TIMEOUT, "Operation timed out"
            
        # Check for network error simulation
        if self.failure_mode == "network_error":
            return LedgerStatus.FAILED, "Network connection failed"
            
        # Check for debit failure
        if self._should_fail("debit"):
            return LedgerStatus.FAILED, "Insufficient funds or account locked"
            
        # Check balance
        current_balance = self.account_balances.get(account_id, 0.0)
        if current_balance < amount:
            return LedgerStatus.FAILED, "Insufficient funds"
            
        # Execute debit
        self.account_balances[account_id] = current_balance - amount
        
        # Record transaction
        if transaction_id not in self.transactions:
            self.transactions[transaction_id] = {}
        self.transactions[transaction_id]["debit"] = {
            "account": account_id,
            "amount": amount,
            "status": LedgerStatus.SUCCESS,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return LedgerStatus.SUCCESS, None
        
    def credit_account(self, transaction_id: str, account_id: str, 
                      amount: float) -> Tuple[LedgerStatus, Optional[str]]:
        """
        Credit funds to destination account.
        
        Args:
            transaction_id: Unique transaction identifier
            account_id: Destination account to credit
            amount: Amount to credit
            
        Returns:
            Tuple of (status, error_message)
        """
        self._simulate_delay()
        
        # Check for partial success (debit worked, credit fails)
        if self.failure_mode == "partial_success":
            return LedgerStatus.FAILED, "Credit posting failed - account invalid"
            
        # Check for credit failure
        if self._should_fail("credit"):
            return LedgerStatus.FAILED, "Account closed or invalid"
            
        # Execute credit
        current_balance = self.account_balances.get(account_id, 0.0)
        self.account_balances[account_id] = current_balance + amount
        
        # Record transaction
        if transaction_id not in self.transactions:
            self.transactions[transaction_id] = {}
        self.transactions[transaction_id]["credit"] = {
            "account": account_id,
            "amount": amount,
            "status": LedgerStatus.SUCCESS,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return LedgerStatus.SUCCESS, None
        
    def rollback_transaction(self, transaction_id: str) -> Tuple[LedgerStatus, Optional[str]]:
        """
        Rollback a partially completed transaction.
        
        Args:
            transaction_id: Transaction to rollback
            
        Returns:
            Tuple of (status, error_message)
        """
        self._simulate_delay()
        
        if transaction_id not in self.transactions:
            return LedgerStatus.FAILED, "Transaction not found"
            
        txn = self.transactions[transaction_id]
        
        # Rollback debit if it occurred
        if "debit" in txn and txn["debit"]["status"] == LedgerStatus.SUCCESS:
            account_id = txn["debit"]["account"]
            amount = txn["debit"]["amount"]
            # Restore funds to source account
            self.account_balances[account_id] = self.account_balances.get(account_id, 0.0) + amount
            txn["debit"]["status"] = LedgerStatus.FAILED
            txn["debit"]["rollback_timestamp"] = datetime.utcnow().isoformat()
            
        # Rollback credit if it occurred
        if "credit" in txn and txn["credit"]["status"] == LedgerStatus.SUCCESS:
            account_id = txn["credit"]["account"]
            amount = txn["credit"]["amount"]
            # Remove funds from destination account
            self.account_balances[account_id] = self.account_balances.get(account_id, 0.0) - amount
            txn["credit"]["status"] = LedgerStatus.FAILED
            txn["credit"]["rollback_timestamp"] = datetime.utcnow().isoformat()
            
        return LedgerStatus.SUCCESS, None
        
    def get_transaction_status(self, transaction_id: str) -> Optional[Dict]:
        """Get transaction details"""
        return self.transactions.get(transaction_id)
        
    def is_transaction_complete(self, transaction_id: str) -> bool:
        """Check if both debit and credit operations completed successfully"""
        txn = self.transactions.get(transaction_id)
        if not txn:
            return False
            
        debit_success = (
            "debit" in txn and 
            txn["debit"]["status"] == LedgerStatus.SUCCESS
        )
        credit_success = (
            "credit" in txn and 
            txn["credit"]["status"] == LedgerStatus.SUCCESS
        )
        
        return debit_success and credit_success
