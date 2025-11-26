"""
Structured logging utility with unique transaction identifiers
Ensures comprehensive audit trail without exposing sensitive data
"""

import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from pythonjsonlogger import jsonlogger


class SensitiveDataFilter(logging.Filter):
    """Filter to mask sensitive data in logs"""
    
    SENSITIVE_FIELDS = ['account_number', 'card_number', 'pin', 'password']
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Mask sensitive fields in log record"""
        if hasattr(record, 'extra'):
            for field in self.SENSITIVE_FIELDS:
                if field in record.extra:
                    record.extra[field] = self._mask_value(record.extra[field])
        return True
        
    @staticmethod
    def _mask_value(value: str) -> str:
        """Mask sensitive value, showing only last 4 characters"""
        if not value or len(value) <= 4:
            return "****"
        return "*" * (len(value) - 4) + value[-4:]


class TransactionContextFilter(logging.Filter):
    """Add transaction context to all log records"""
    
    def __init__(self):
        super().__init__()
        self._transaction_id: Optional[str] = None
        
    def set_transaction_id(self, transaction_id: str) -> None:
        """Set current transaction ID for context"""
        self._transaction_id = transaction_id
        
    def clear_transaction_id(self) -> None:
        """Clear transaction context"""
        self._transaction_id = None
        
    def filter(self, record: logging.LogRecord) -> bool:
        """Add transaction ID to record if available"""
        if self._transaction_id:
            record.transaction_id = self._transaction_id
        return True


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Setup structured JSON logger with sensitive data filtering.
    
    Args:
        name: Logger name (usually __name__)
        level: Logging level
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Remove existing handlers
    logger.handlers = []
    
    # JSON formatter
    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S'
    )
    
    # Console handler with JSON format
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    # Add filters
    handler.addFilter(SensitiveDataFilter())
    handler.addFilter(TransactionContextFilter())
    
    logger.addHandler(handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get or create logger for module"""
    return logging.getLogger(name)


class AuditLogger:
    """
    High-level audit logger for transfer operations.
    Emits structured events for all critical transfer lifecycle events.
    """
    
    def __init__(self):
        self.logger = get_logger("audit")
        
    def log_transfer_initiated(self, transaction_id: str, 
                               source_account: str,
                               destination_account: str,
                               amount: float,
                               currency: str) -> None:
        """Log transfer initiation"""
        self.logger.info(
            "Transfer initiated",
            extra={
                "event": "transfer_initiated",
                "transaction_id": transaction_id,
                "source_account": self._mask_account(source_account),
                "destination_account": self._mask_account(destination_account),
                "amount": amount,
                "currency": currency,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    def log_state_transition(self, transaction_id: str,
                            from_state: str,
                            to_state: str,
                            reason: Optional[str] = None) -> None:
        """Log state transition"""
        self.logger.info(
            "State transition",
            extra={
                "event": "state_transition",
                "transaction_id": transaction_id,
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    def log_ledger_operation(self, transaction_id: str,
                            operation: str,
                            account: str,
                            amount: float,
                            status: str,
                            error: Optional[str] = None) -> None:
        """Log ledger operation (debit/credit/rollback)"""
        extra = {
            "event": "ledger_operation",
            "transaction_id": transaction_id,
            "operation": operation,
            "account": self._mask_account(account),
            "amount": amount,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if error:
            extra["error"] = error
            
        if status == "failed":
            self.logger.error(f"Ledger operation failed: {operation}", extra=extra)
        else:
            self.logger.info(f"Ledger operation: {operation}", extra=extra)
            
    def log_transfer_completed(self, transaction_id: str,
                               duration_ms: float) -> None:
        """Log successful transfer completion"""
        self.logger.info(
            "Transfer completed successfully",
            extra={
                "event": "transfer_completed",
                "transaction_id": transaction_id,
                "duration_ms": duration_ms,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    def log_transfer_failed(self, transaction_id: str,
                           error_code: str,
                           error_message: str,
                           current_state: str) -> None:
        """Log transfer failure"""
        self.logger.error(
            "Transfer failed",
            extra={
                "event": "transfer_failed",
                "transaction_id": transaction_id,
                "error_code": error_code,
                "error_message": error_message,
                "current_state": current_state,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    def log_rollback(self, transaction_id: str,
                    reason: str,
                    status: str) -> None:
        """Log rollback operation"""
        self.logger.warning(
            "Transfer rollback",
            extra={
                "event": "transfer_rollback",
                "transaction_id": transaction_id,
                "reason": reason,
                "status": status,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    @staticmethod
    def _mask_account(account: str) -> str:
        """Mask account number, showing only last 4 digits"""
        if not account or len(account) <= 4:
            return "****"
        return "*" * (len(account) - 4) + account[-4:]
