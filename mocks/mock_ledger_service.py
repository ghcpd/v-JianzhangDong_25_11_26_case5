"""
Mock Ledger Service for Testing Transfer Module

Simulates a core banking ledger system with configurable failure modes.
Used during development and testing to avoid hitting the real ledger.

Features:
- Configurable success/failure/timeout scenarios
- Realistic async callback mechanism
- Idempotency key deduplication
- Call history tracking for test assertions
- Network partition simulation
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass, asdict
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class LedgerOperationStatus(str, Enum):
    """Status of a ledger operation"""
    PENDING = "PENDING"  # Request received, processing
    SUCCESS = "SUCCESS"  # Operation completed successfully
    FAILED = "FAILED"  # Operation failed
    TIMEOUT = "TIMEOUT"  # Request timed out
    UNKNOWN = "UNKNOWN"  # Status cannot be determined


@dataclass
class LedgerResponse:
    """Response from ledger service"""
    status: LedgerOperationStatus
    ledger_txn_id: Optional[str] = None
    callback_url: Optional[str] = None
    reason: Optional[str] = None  # Error reason if failed
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'status': self.status.value,
            'ledger_txn_id': self.ledger_txn_id,
            'callback_url': self.callback_url,
            'reason': self.reason,
            'timestamp': self.timestamp.isoformat() + 'Z'
        }


@dataclass
class LedgerCallback:
    """Callback from ledger service"""
    transfer_id: str
    operation_type: str  # 'debit' or 'credit'
    status: LedgerOperationStatus
    ledger_txn_id: str
    amount: Decimal
    reason: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'transfer_id': self.transfer_id,
            'operation_type': self.operation_type,
            'status': self.status.value,
            'ledger_txn_id': self.ledger_txn_id,
            'amount': str(self.amount),
            'reason': self.reason,
            'timestamp': self.timestamp.isoformat() + 'Z'
        }


@dataclass
class LedgerCall:
    """Record of a call to the ledger service"""
    txn_id: str
    operation_type: str
    idempotency_key: str
    amount: Decimal
    callback_url: str
    timestamp: datetime
    response_status: LedgerOperationStatus
    ledger_txn_id: Optional[str] = None
    retry_count: int = 0


class FailureMode(str, Enum):
    """Configurable failure modes for testing"""
    SUCCESS = "success"  # Normal operation
    FAIL = "fail"  # Operation fails (e.g., insufficient funds)
    TIMEOUT = "timeout"  # Request times out
    NO_CALLBACK = "no_callback"  # Callback is never sent (network partition)
    CALLBACK_DELAYED = "callback_delayed"  # Callback is delayed beyond timeout
    IDEMPOTENCY_MISMATCH = "idempotency_mismatch"  # Same idempotency_key returns different result


class MockLedgerService:
    """
    Mock ledger service for testing the transfer module.
    
    Usage:
        ledger = MockLedgerService()
        
        # Configure failure mode for testing
        ledger.set_failure_mode(FailureMode.SUCCESS)
        
        # Make requests (async)
        response = await ledger.post_debit(
            txn_id="txn-123",
            idempotency_key="idempotency-456",
            amount=Decimal("100.50"),
            callback_url="http://backend/webhooks/ledger/callback"
        )
        
        # Simulate callback being sent (if not in NO_CALLBACK mode)
        # Callbacks are sent asynchronously via registered handler
        
        # Assert calls were made
        assert len(ledger.debit_calls) == 1
        assert ledger.debit_calls[0]['amount'] == Decimal("100.50")
    """
    
    def __init__(self):
        self.failure_mode: FailureMode = FailureMode.SUCCESS
        self.debit_calls: List[LedgerCall] = []
        self.credit_calls: List[LedgerCall] = []
        self.reverse_calls: List[LedgerCall] = []
        self.callback_handler: Optional[Callable] = None
        self.idempotency_cache: Dict[str, LedgerResponse] = {}
        
        # Timing control
        self.debit_latency_ms: int = 100  # Simulate processing time
        self.credit_latency_ms: int = 100
        self.callback_delay_ms: int = 50
        
        # Counters for metrics
        self.total_debit_requests: int = 0
        self.total_credit_requests: int = 0
        self.total_callbacks_sent: int = 0
        
    def set_failure_mode(self, mode: FailureMode):
        """Set the failure mode for subsequent requests"""
        self.failure_mode = mode
        logger.info(f"Ledger failure mode set to: {mode.value}")
    
    def set_callback_handler(self, handler: Callable):
        """
        Register a callback handler to be invoked when operations complete.
        
        Handler signature: async def handle_callback(callback: LedgerCallback) -> bool
        Returns: True if callback was successfully processed
        """
        self.callback_handler = handler
    
    def reset(self):
        """Clear all call history and caches (for test isolation)"""
        self.debit_calls.clear()
        self.credit_calls.clear()
        self.reverse_calls.clear()
        self.idempotency_cache.clear()
        self.total_debit_requests = 0
        self.total_credit_requests = 0
        self.total_callbacks_sent = 0
        logger.info("Mock ledger service reset")
    
    async def post_debit(self, txn_id: str, idempotency_key: str, 
                        amount: Decimal, callback_url: str) -> LedgerResponse:
        """
        Post a debit operation to the ledger.
        
        Args:
            txn_id: Transfer ID from backend
            idempotency_key: Unique key for idempotency; same key = same result
            amount: Amount to debit (e.g., Decimal("100.50"))
            callback_url: URL where ledger will POST the callback
        
        Returns:
            LedgerResponse with status, ledger_txn_id, and callback_url
        """
        self.total_debit_requests += 1
        
        # Idempotency check
        if idempotency_key in self.idempotency_cache:
            logger.info(f"Idempotency cache hit for {idempotency_key}")
            return self.idempotency_cache[idempotency_key]
        
        # Simulate processing time
        await asyncio.sleep(self.debit_latency_ms / 1000.0)
        
        ledger_txn_id = f"LEDGER-{uuid.uuid4().hex[:8].upper()}"
        
        # Determine response based on failure mode
        if self.failure_mode == FailureMode.SUCCESS:
            status = LedgerOperationStatus.SUCCESS
            reason = None
        elif self.failure_mode == FailureMode.FAIL:
            status = LedgerOperationStatus.FAILED
            reason = "Insufficient funds"
        elif self.failure_mode == FailureMode.TIMEOUT:
            status = LedgerOperationStatus.TIMEOUT
            reason = "Request timed out"
        else:
            status = LedgerOperationStatus.SUCCESS
            reason = None
        
        response = LedgerResponse(
            status=status,
            ledger_txn_id=ledger_txn_id,
            callback_url=callback_url,
            reason=reason
        )
        
        # Cache response for idempotency
        self.idempotency_cache[idempotency_key] = response
        
        # Record the call
        call = LedgerCall(
            txn_id=txn_id,
            operation_type='debit',
            idempotency_key=idempotency_key,
            amount=amount,
            callback_url=callback_url,
            timestamp=datetime.utcnow(),
            response_status=status,
            ledger_txn_id=ledger_txn_id,
            retry_count=0
        )
        self.debit_calls.append(call)
        
        logger.info(
            f"Debit posted: txn_id={txn_id}, amount={amount}, status={status.value}, "
            f"ledger_txn_id={ledger_txn_id}"
        )
        
        # Schedule async callback (unless in NO_CALLBACK mode)
        if self.failure_mode != FailureMode.NO_CALLBACK and self.callback_handler:
            delay = (self.callback_delay_ms if self.failure_mode != FailureMode.CALLBACK_DELAYED
                    else 35000)  # Delay beyond 30s timeout
            asyncio.create_task(
                self._send_callback(
                    transfer_id=txn_id,
                    operation_type='debit',
                    status=status,
                    ledger_txn_id=ledger_txn_id,
                    amount=amount,
                    reason=reason,
                    delay_ms=delay
                )
            )
        
        return response
    
    async def post_credit(self, txn_id: str, idempotency_key: str, 
                         amount: Decimal, callback_url: str) -> LedgerResponse:
        """
        Post a credit operation to the ledger.
        
        Args:
            txn_id: Transfer ID from backend
            idempotency_key: Unique key for idempotency
            amount: Amount to credit
            callback_url: URL where ledger will POST the callback
        
        Returns:
            LedgerResponse with status and ledger_txn_id
        """
        self.total_credit_requests += 1
        
        # Idempotency check
        if idempotency_key in self.idempotency_cache:
            logger.info(f"Idempotency cache hit for {idempotency_key}")
            return self.idempotency_cache[idempotency_key]
        
        # Simulate processing time
        await asyncio.sleep(self.credit_latency_ms / 1000.0)
        
        ledger_txn_id = f"LEDGER-{uuid.uuid4().hex[:8].upper()}"
        
        # Determine response based on failure mode
        if self.failure_mode == FailureMode.SUCCESS:
            status = LedgerOperationStatus.SUCCESS
            reason = None
        elif self.failure_mode == FailureMode.FAIL:
            status = LedgerOperationStatus.FAILED
            reason = "Recipient account not found"
        elif self.failure_mode == FailureMode.TIMEOUT:
            status = LedgerOperationStatus.TIMEOUT
            reason = "Request timed out"
        else:
            status = LedgerOperationStatus.SUCCESS
            reason = None
        
        response = LedgerResponse(
            status=status,
            ledger_txn_id=ledger_txn_id,
            callback_url=callback_url,
            reason=reason
        )
        
        # Cache response for idempotency
        self.idempotency_cache[idempotency_key] = response
        
        # Record the call
        call = LedgerCall(
            txn_id=txn_id,
            operation_type='credit',
            idempotency_key=idempotency_key,
            amount=amount,
            callback_url=callback_url,
            timestamp=datetime.utcnow(),
            response_status=status,
            ledger_txn_id=ledger_txn_id,
            retry_count=0
        )
        self.credit_calls.append(call)
        
        logger.info(
            f"Credit posted: txn_id={txn_id}, amount={amount}, status={status.value}, "
            f"ledger_txn_id={ledger_txn_id}"
        )
        
        # Schedule async callback (unless in NO_CALLBACK mode)
        if self.failure_mode != FailureMode.NO_CALLBACK and self.callback_handler:
            delay = (self.callback_delay_ms if self.failure_mode != FailureMode.CALLBACK_DELAYED
                    else 35000)
            asyncio.create_task(
                self._send_callback(
                    transfer_id=txn_id,
                    operation_type='credit',
                    status=status,
                    ledger_txn_id=ledger_txn_id,
                    amount=amount,
                    reason=reason,
                    delay_ms=delay
                )
            )
        
        return response
    
    async def post_reverse_debit(self, txn_id: str, idempotency_key: str, 
                                amount: Decimal, callback_url: str) -> LedgerResponse:
        """
        Post a reverse debit (compensation) to refund a previous debit.
        
        Args:
            txn_id: Original transfer ID (or reverse transaction ID)
            idempotency_key: Unique key for idempotency
            amount: Amount to credit back
            callback_url: URL where ledger will POST the callback
        
        Returns:
            LedgerResponse with status and ledger_txn_id
        """
        # Reverse debits always succeed in this mock
        ledger_txn_id = f"LEDGER-{uuid.uuid4().hex[:8].upper()}"
        
        response = LedgerResponse(
            status=LedgerOperationStatus.SUCCESS,
            ledger_txn_id=ledger_txn_id,
            callback_url=callback_url,
            reason=None
        )
        
        # Cache response for idempotency
        self.idempotency_cache[idempotency_key] = response
        
        # Record the call
        call = LedgerCall(
            txn_id=txn_id,
            operation_type='reverse_debit',
            idempotency_key=idempotency_key,
            amount=amount,
            callback_url=callback_url,
            timestamp=datetime.utcnow(),
            response_status=LedgerOperationStatus.SUCCESS,
            ledger_txn_id=ledger_txn_id,
            retry_count=0
        )
        self.reverse_calls.append(call)
        
        logger.info(
            f"Reverse debit posted: txn_id={txn_id}, amount={amount}, "
            f"ledger_txn_id={ledger_txn_id}"
        )
        
        # Schedule async callback
        if self.callback_handler:
            asyncio.create_task(
                self._send_callback(
                    transfer_id=txn_id,
                    operation_type='reverse_debit',
                    status=LedgerOperationStatus.SUCCESS,
                    ledger_txn_id=ledger_txn_id,
                    amount=amount,
                    reason=None,
                    delay_ms=self.callback_delay_ms
                )
            )
        
        return response
    
    async def _send_callback(self, transfer_id: str, operation_type: str,
                            status: LedgerOperationStatus, ledger_txn_id: str,
                            amount: Decimal, reason: Optional[str],
                            delay_ms: int = 0):
        """
        Internal: Send a callback to the backend (async).
        
        In a real system, this would be an HTTP POST to the callback_url.
        Here, we invoke the registered callback handler directly.
        """
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)
        
        callback = LedgerCallback(
            transfer_id=transfer_id,
            operation_type=operation_type,
            status=status,
            ledger_txn_id=ledger_txn_id,
            amount=amount,
            reason=reason
        )
        
        try:
            if self.callback_handler:
                await self.callback_handler(callback)
            self.total_callbacks_sent += 1
            logger.info(f"Callback sent: {transfer_id}, {operation_type}, {status.value}")
        except Exception as e:
            logger.error(f"Callback handler failed: {e}")
    
    def get_metrics(self) -> dict:
        """Get call metrics for test assertions"""
        return {
            'total_debit_requests': self.total_debit_requests,
            'total_credit_requests': self.total_credit_requests,
            'total_reverse_requests': len(self.reverse_calls),
            'total_callbacks_sent': self.total_callbacks_sent,
            'debit_call_count': len(self.debit_calls),
            'credit_call_count': len(self.credit_calls),
            'reverse_call_count': len(self.reverse_calls),
        }
    
    def get_debit_calls(self) -> List[LedgerCall]:
        """Get all debit calls for inspection"""
        return self.debit_calls.copy()
    
    def get_credit_calls(self) -> List[LedgerCall]:
        """Get all credit calls for inspection"""
        return self.credit_calls.copy()
    
    def get_reverse_calls(self) -> List[LedgerCall]:
        """Get all reverse debit calls for inspection"""
        return self.reverse_calls.copy()


# Global instance for testing
_mock_ledger = MockLedgerService()


def get_mock_ledger() -> MockLedgerService:
    """Get the global mock ledger instance"""
    return _mock_ledger


# Example usage for testing
if __name__ == "__main__":
    import logging
    
    logging.basicConfig(level=logging.INFO)
    
    async def example():
        ledger = get_mock_ledger()
        ledger.reset()
        
        # Callback handler
        async def handle_callback(callback: LedgerCallback):
            print(f"Callback received: {callback}")
        
        ledger.set_callback_handler(handle_callback)
        
        # Test successful debit
        print("\n=== Test 1: Successful Debit ===")
        ledger.set_failure_mode(FailureMode.SUCCESS)
        response = await ledger.post_debit(
            txn_id="txn-001",
            idempotency_key="idempotent-001",
            amount=Decimal("100.50"),
            callback_url="http://backend/webhooks/ledger/callback"
        )
        print(f"Response: {response.to_dict()}")
        await asyncio.sleep(0.2)  # Wait for callback
        
        # Test failed credit
        print("\n=== Test 2: Failed Credit ===")
        ledger.set_failure_mode(FailureMode.FAIL)
        response = await ledger.post_credit(
            txn_id="txn-002",
            idempotency_key="idempotent-002",
            amount=Decimal("50.25"),
            callback_url="http://backend/webhooks/ledger/callback"
        )
        print(f"Response: {response.to_dict()}")
        await asyncio.sleep(0.2)
        
        # Print metrics
        print(f"\nMetrics: {ledger.get_metrics()}")
    
    asyncio.run(example())
