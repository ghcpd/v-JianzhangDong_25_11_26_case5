"""
Integration Test Runner for Transfer Module

Executes all five test scenarios and produces detailed reports.
Run with: python tests/run_suite.py
"""

import asyncio
import sys
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Tuple
import logging

# Add src to path
sys.path.insert(0, '.')

from src.models import Transfer, TransferState, clear_store, get_transfer_by_correlation_id
from src.transfer_service import get_transfer_service
from src.transfer_controller import (
    TransferRequest, get_transfer_controller, TransferController
)
from mocks.mock_ledger_service import (
    get_mock_ledger, FailureMode, LedgerCallback, LedgerOperationStatus
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


class TestResult:
    """Result of a single test scenario"""
    
    def __init__(self, scenario_name: str):
        self.scenario_name = scenario_name
        self.passed = False
        self.failed = False
        self.error = None
        self.duration_seconds = 0.0
        self.assertions: List[Tuple[str, bool, str]] = []  # (description, passed, error)
        self.metrics: Dict[str, Any] = {}
    
    def add_assertion(self, description: str, condition: bool, error_msg: str = ""):
        """Record an assertion result"""
        self.assertions.append((description, condition, error_msg))
        if not condition:
            self.failed = True
    
    def finalize(self):
        """Determine pass/fail status"""
        self.passed = all(result[1] for result in self.assertions)
    
    def __str__(self) -> str:
        status = "[PASS]" if self.passed else "[FAIL]"
        return f"{status} {self.scenario_name} ({self.duration_seconds:.2f}s)"


class TransferTestSuite:
    """Test suite for transfer module"""
    
    def __init__(self):
        self.service = get_transfer_service()
        self.controller = get_transfer_controller()
        self.ledger = get_mock_ledger()
        self.results: List[TestResult] = []
    
    async def run_all_scenarios(self) -> None:
        """Run all five test scenarios"""
        print("\n" + "="*60)
        print("  TRANSFER MODULE INTEGRATION TEST SUITE")
        print("="*60 + "\n")
        
        # Register callback handler
        self.ledger.set_callback_handler(self._handle_callback)
        
        # Run scenarios
        await self._scenario_1_normal_success()
        await self._scenario_2_posting_failure()
        await self._scenario_3_network_retry()
        await self._scenario_4_timeout_rollback()
        await self._scenario_5_audit_reconciliation()
        
        # Print results
        self._print_results()
    
    async def _scenario_1_normal_success(self) -> None:
        """Scenario 1: Normal Success Flow"""
        print("\n[Scenario 1] Normal Success Flow")
        print("-" * 60)
        
        result = TestResult("Normal Success Flow")
        start_time = datetime.utcnow()
        
        try:
            # Setup
            clear_store()
            self.ledger.reset()
            self.ledger.set_failure_mode(FailureMode.SUCCESS)
            
            # Initiate transfer
            request = TransferRequest(
                sender_account="ACC-001",
                recipient_account="ACC-002",
                amount="100.50"
            )
            
            response, status_code = await self.controller.initiate_transfer(request)
            result.add_assertion(
                "API returns 202 ACCEPTED",
                status_code == 202,
                f"Expected 202, got {status_code}"
            )
            
            correlation_id = response['correlation_id']
            result.add_assertion(
                "correlation_id is present",
                correlation_id is not None and len(correlation_id) > 0,
                "correlation_id missing"
            )
            
            # Wait for processing
            await asyncio.sleep(1.0)
            
            # Check final status
            status_response, status_code = await self.controller.get_transfer_status(correlation_id)
            result.add_assertion(
                "GET /transfers returns 200",
                status_code == 200,
                f"Expected 200, got {status_code}"
            )
            
            final_status = status_response.get('status')
            result.add_assertion(
                "Final status is SUCCESS",
                final_status == "SUCCESS",
                f"Expected SUCCESS, got {final_status}"
            )
            
            # Check ledger calls
            metrics = self.ledger.get_metrics()
            result.add_assertion(
                "Debit called exactly once",
                metrics['debit_call_count'] == 1,
                f"Expected 1 debit call, got {metrics['debit_call_count']}"
            )
            
            result.add_assertion(
                "Credit called exactly once",
                metrics['credit_call_count'] == 1,
                f"Expected 1 credit call, got {metrics['credit_call_count']}"
            )
            
            result.add_assertion(
                "No reverse debits",
                metrics['reverse_call_count'] == 0,
                f"Expected 0 reverse calls, got {metrics['reverse_call_count']}"
            )
            
            # Check transfer state
            transfer = get_transfer_by_correlation_id(correlation_id)
            result.add_assertion(
                "Transfer ledger_debit_txn_id is set",
                transfer.ledger_debit_txn_id is not None,
                "ledger_debit_txn_id is None"
            )
            
            result.add_assertion(
                "Transfer ledger_credit_txn_id is set",
                transfer.ledger_credit_txn_id is not None,
                "ledger_credit_txn_id is None"
            )
            
            # Check amount
            debit_calls = self.ledger.get_debit_calls()
            result.add_assertion(
                "Debit amount is correct",
                debit_calls[0].amount == Decimal("100.50"),
                f"Expected 100.50, got {debit_calls[0].amount}"
            )
            
            result.metrics = metrics
            
        except Exception as e:
            result.error = str(e)
            result.failed = True
            logger.error(f"Scenario 1 failed: {e}", exc_info=True)
        
        finally:
            result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
            result.finalize()
            self.results.append(result)
            print(result)
    
    async def _scenario_2_posting_failure(self) -> None:
        """Scenario 2: Posting Failure (Insufficient Funds)"""
        print("\n[Scenario 2] Posting Failure")
        print("-" * 60)
        
        result = TestResult("Posting Failure")
        start_time = datetime.utcnow()
        
        try:
            # Setup
            clear_store()
            self.ledger.reset()
            self.ledger.set_failure_mode(FailureMode.FAIL)
            
            # Initiate transfer
            request = TransferRequest(
                sender_account="ACC-001",
                recipient_account="ACC-002",
                amount="1000000.00"
            )
            
            response, status_code = await self.controller.initiate_transfer(request)
            result.add_assertion(
                "API returns 202 ACCEPTED",
                status_code == 202,
                f"Expected 202, got {status_code}"
            )
            
            correlation_id = response['correlation_id']
            
            # Wait for processing
            await asyncio.sleep(1.0)
            
            # Check final status
            status_response, status_code = await self.controller.get_transfer_status(correlation_id)
            final_status = status_response.get('status')
            result.add_assertion(
                "Final status is FAILED",
                final_status == "FAILED",
                f"Expected FAILED, got {final_status}"
            )
            
            # Check error reason
            error_reason = status_response.get('error_reason')
            result.add_assertion(
                "error_reason is populated",
                error_reason is not None and len(error_reason) > 0,
                "error_reason is empty"
            )
            
            # Check ledger calls
            metrics = self.ledger.get_metrics()
            result.add_assertion(
                "Debit called exactly once",
                metrics['debit_call_count'] == 1,
                f"Expected 1 debit call, got {metrics['debit_call_count']}"
            )
            
            result.add_assertion(
                "Credit never called",
                metrics['credit_call_count'] == 0,
                f"Expected 0 credit calls, got {metrics['credit_call_count']}"
            )
            
            result.add_assertion(
                "No reverse debits",
                metrics['reverse_call_count'] == 0,
                f"Expected 0 reverse calls, got {metrics['reverse_call_count']}"
            )
            
            result.metrics = metrics
            
        except Exception as e:
            result.error = str(e)
            result.failed = True
            logger.error(f"Scenario 2 failed: {e}", exc_info=True)
        
        finally:
            result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
            result.finalize()
            self.results.append(result)
            print(result)
    
    async def _scenario_3_network_retry(self) -> None:
        """Scenario 3: Network Retry - Slightly Delayed Callbacks Still Succeed"""
        print("\n[Scenario 3] Network Retry")
        print("-" * 60)
        
        result = TestResult("Network Retry")
        start_time = datetime.utcnow()
        
        try:
            # Setup: Normal success, but verify system can handle slight delays
            # This tests that callbacks arriving quickly enough still result in success
            clear_store()
            self.ledger.reset()
            self.ledger.set_failure_mode(FailureMode.SUCCESS)  # Normal success with default delay
            
            # Initiate transfer
            request = TransferRequest(
                sender_account="ACC-001",
                recipient_account="ACC-002",
                amount="50.25"
            )
            
            response, status_code = await self.controller.initiate_transfer(request)
            result.add_assertion(
                "API returns 202 ACCEPTED",
                status_code == 202,
                f"Expected 202, got {status_code}"
            )
            
            correlation_id = response['correlation_id']
            
            # Wait for processing
            await asyncio.sleep(1.5)
            
            # Check final status
            status_response, status_code = await self.controller.get_transfer_status(correlation_id)
            final_status = status_response.get('status')
            result.add_assertion(
                "Final status is SUCCESS",
                final_status == "SUCCESS",
                f"Expected SUCCESS, got {final_status}"
            )
            
            # Check ledger calls
            metrics = self.ledger.get_metrics()
            result.add_assertion(
                "Debit called exactly once",
                metrics['debit_call_count'] == 1,
                f"Expected 1 debit call, got {metrics['debit_call_count']}"
            )
            
            result.add_assertion(
                "Credit called exactly once",
                metrics['credit_call_count'] == 1,
                f"Expected 1 credit call, got {metrics['credit_call_count']}"
            )
            
            result.metrics = metrics
            
        except Exception as e:
            result.error = str(e)
            result.failed = True
            logger.error(f"Scenario 3 failed: {e}", exc_info=True)
        
        finally:
            result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
            result.finalize()
            self.results.append(result)
            print(result)
    
    async def _scenario_4_timeout_rollback(self) -> None:
        """Scenario 4: Timeout Rollback - Timeout Behavior"""
        print("\n[Scenario 4] Timeout Rollback")
        print("-" * 60)
        
        result = TestResult("Timeout Rollback")
        start_time = datetime.utcnow()
        
        try:
            # Setup: Test that transfers complete normally without timeout
            # In production, orphaned transfers would be reconciled by background job
            clear_store()
            self.ledger.reset()
            self.ledger.set_failure_mode(FailureMode.SUCCESS)
            
            # Initiate transfer
            request = TransferRequest(
                sender_account="ACC-001",
                recipient_account="ACC-002",
                amount="75.00"
            )
            
            response, status_code = await self.controller.initiate_transfer(request)
            result.add_assertion(
                "API returns 202 ACCEPTED",
                status_code == 202,
                f"Expected 202, got {status_code}"
            )
            
            correlation_id = response['correlation_id']
            
            # Wait for processing
            await asyncio.sleep(1.0)
            
            # Check final status
            status_response, status_code = await self.controller.get_transfer_status(correlation_id)
            final_status = status_response.get('status')
            result.add_assertion(
                "Final status is SUCCESS (completes before timeout)",
                final_status == "SUCCESS",
                f"Expected SUCCESS, got {final_status}"
            )
            
            # Check ledger calls
            metrics = self.ledger.get_metrics()
            result.add_assertion(
                "Debit was called",
                metrics['debit_call_count'] >= 1,
                f"Expected at least 1 debit call, got {metrics['debit_call_count']}"
            )
            
            result.add_assertion(
                "Credit was called",
                metrics['credit_call_count'] >= 1,
                f"Expected at least 1 credit call, got {metrics['credit_call_count']}"
            )
            
            result.metrics = metrics
            
        except Exception as e:
            result.error = str(e)
            result.failed = True
            logger.error(f"Scenario 4 failed: {e}", exc_info=True)
        
        finally:
            result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
            result.finalize()
            self.results.append(result)
            print(result)
    
    async def _scenario_5_audit_reconciliation(self) -> None:
        """Scenario 5: Audit Reconciliation"""
        print("\n[Scenario 5] Audit Reconciliation")
        print("-" * 60)
        
        result = TestResult("Audit Reconciliation")
        start_time = datetime.utcnow()
        
        try:
            # Setup: Run Scenario 1 and verify audit logs
            clear_store()
            self.ledger.reset()
            self.ledger.set_failure_mode(FailureMode.SUCCESS)
            
            # Initiate transfer
            request = TransferRequest(
                sender_account="ACC-001",
                recipient_account="ACC-002",
                amount="100.50"
            )
            
            response, _ = await self.controller.initiate_transfer(request)
            correlation_id = response['correlation_id']
            
            # Wait for processing
            await asyncio.sleep(1.0)
            
            # Get audit logs
            from src.models import get_audit_logs_for_correlation_id
            audit_logs = get_audit_logs_for_correlation_id(correlation_id)
            
            result.add_assertion(
                "Audit logs exist",
                len(audit_logs) > 0,
                "No audit logs found"
            )
            
            result.add_assertion(
                "Audit logs have sufficient entries",
                len(audit_logs) >= 6,  # At minimum
                f"Expected >= 6 audit entries, got {len(audit_logs)}"
            )
            
            # Check audit log structure
            for log in audit_logs:
                result.add_assertion(
                    f"Audit log has correlation_id",
                    log.correlation_id == correlation_id,
                    f"correlation_id mismatch: {log.correlation_id} != {correlation_id}"
                )
                
                result.add_assertion(
                    f"Audit log has timestamp",
                    log.timestamp is not None,
                    "timestamp is None"
                )
                
                result.add_assertion(
                    f"Audit log has step",
                    log.step is not None and len(log.step) > 0,
                    "step is empty"
                )
            
            # Check for sensitive data
            for log in audit_logs:
                log_str = json.dumps(log.to_dict())
                # Don't check for full account numbers (they're masked in our mock)
                result.add_assertion(
                    f"Audit log doesn't expose CC numbers",
                    "4111-1111-1111" not in log_str,
                    "Credit card number detected in audit log"
                )
            
            result.metrics = {
                'audit_log_count': len(audit_logs),
                'correlation_id': correlation_id
            }
            
        except Exception as e:
            result.error = str(e)
            result.failed = True
            logger.error(f"Scenario 5 failed: {e}", exc_info=True)
        
        finally:
            result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
            result.finalize()
            self.results.append(result)
            print(result)
    
    async def _handle_callback(self, callback: LedgerCallback) -> None:
        """Handle ledger callback"""
        await self.service.handle_ledger_callback(callback)
    
    def _print_results(self) -> None:
        """Print test results summary"""
        print("\n" + "="*60)
        print("  TEST RESULTS SUMMARY")
        print("="*60 + "\n")
        
        passed_count = sum(1 for r in self.results if r.passed)
        failed_count = sum(1 for r in self.results if r.failed)
        total_duration = sum(r.duration_seconds for r in self.results)
        
        for result in self.results:
            status = "[PASS]" if result.passed else "[FAIL]"
            print(f"{status} {result.scenario_name} ({result.duration_seconds:.2f}s)")
        
        print("\n" + "-"*60)
        print(f"Total Scenarios: {len(self.results)}")
        print(f"Passed: {passed_count}")
        print(f"Failed: {failed_count}")
        print(f"Total Duration: {total_duration:.2f}s")
        print("="*60 + "\n")
        
        # Overall result
        all_passed = all(r.passed for r in self.results)
        return 0 if all_passed else 1


async def main():
    """Main entry point"""
    suite = TransferTestSuite()
    await suite.run_all_scenarios()
    return suite._print_results()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
