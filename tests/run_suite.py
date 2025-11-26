"""
Integration Test Suite for Transfer Flow
Implements the five test cases defined in transfer_cases.yaml
"""

import sys
import json
import yaml
from datetime import datetime
from typing import Dict, List, Any
from dataclasses import dataclass

from mocks.mock_ledger_service import MockLedgerService
from src.services.ledger_adapter import LedgerAdapter
from src.services.transfer_service import TransferService
from src.models.transfer import TransferRequest, TransferState, TransferErrorCode
from src.controllers.transfer_controller import TransferController


@dataclass
class TestResult:
    """Test execution result"""
    test_id: str
    test_name: str
    passed: bool
    duration_ms: float
    error_message: str = None
    verification_results: List[Dict] = None


class TransferIntegrationTests:
    """Integration test suite for transfer flow"""
    
    def __init__(self):
        self.results: List[TestResult] = []
        self.audit_logs: List[Dict] = []
        
    def setup_test_environment(self, failure_mode: str = None) -> TransferController:
        """Setup test environment with specified configuration"""
        # Create mock ledger service
        ledger_service = MockLedgerService(failure_mode=failure_mode)
        
        # Create adapter and service
        ledger_adapter = LedgerAdapter(ledger_service)
        transfer_service = TransferService(ledger_adapter)
        
        # Create controller
        controller = TransferController(transfer_service)
        
        return controller, ledger_service
        
    def verify_condition(self, condition: bool, description: str) -> Dict:
        """Verify a test condition"""
        result = {
            "condition": description,
            "passed": condition,
            "timestamp": datetime.utcnow().isoformat()
        }
        return result
        
    # =========================================================================
    # TC-001: Normal Success Path
    # =========================================================================
    
    def test_normal_success_path(self) -> TestResult:
        """TC-001: Verify successful end-to-end transfer"""
        start_time = datetime.utcnow()
        test_id = "TC-001"
        test_name = "Normal Success Path - Complete Transfer"
        verifications = []
        
        try:
            # Setup
            controller, ledger = self.setup_test_environment(failure_mode=None)
            ledger.set_account_balance("ACC-SOURCE-001", 1000.00)
            ledger.set_account_balance("ACC-DEST-001", 500.00)
            
            # Execute transfer
            request = {
                "source_account": "ACC-SOURCE-001",
                "destination_account": "ACC-DEST-001",
                "amount": 100.00,
                "currency": "USD"
            }
            
            response = controller.create_transfer(request)
            
            # Verify response
            verifications.append(
                self.verify_condition(
                    response.get("status") == "success",
                    "API response status is 'success'"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    "transaction_id" in response,
                    "Transaction ID present in response"
                )
            )
            
            # Get transfer details
            txn_id = response.get("transaction_id")
            transfer = controller.service.get_transfer_status(txn_id)
            
            # Verify transfer state
            verifications.append(
                self.verify_condition(
                    transfer.state == TransferState.COMPLETED,
                    f"Transfer state is COMPLETED (actual: {transfer.state.value})"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    transfer.is_success(),
                    "Transfer marked as successful"
                )
            )
            
            # Verify timestamps
            verifications.append(
                self.verify_condition(
                    transfer.debit_completed_at is not None,
                    "Debit completion timestamp exists"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    transfer.credit_completed_at is not None,
                    "Credit completion timestamp exists"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    transfer.completed_at is not None,
                    "Transfer completion timestamp exists"
                )
            )
            
            # Verify account balances
            source_balance = ledger.get_account_balance("ACC-SOURCE-001")
            dest_balance = ledger.get_account_balance("ACC-DEST-001")
            
            verifications.append(
                self.verify_condition(
                    source_balance == 900.00,
                    f"Source account balance is 900.00 (actual: {source_balance})"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    dest_balance == 600.00,
                    f"Destination account balance is 600.00 (actual: {dest_balance})"
                )
            )
            
            # Verify ledger transaction
            verifications.append(
                self.verify_condition(
                    ledger.is_transaction_complete(txn_id),
                    "Ledger confirms transaction complete"
                )
            )
            
            # All verifications passed?
            all_passed = all(v["passed"] for v in verifications)
            
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return TestResult(
                test_id=test_id,
                test_name=test_name,
                passed=all_passed,
                duration_ms=duration,
                verification_results=verifications
            )
            
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            return TestResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                duration_ms=duration,
                error_message=str(e),
                verification_results=verifications
            )
            
    # =========================================================================
    # TC-002: Credit Failure with Rollback
    # =========================================================================
    
    def test_credit_failure_with_rollback(self) -> TestResult:
        """TC-002: Verify automatic rollback on credit failure"""
        start_time = datetime.utcnow()
        test_id = "TC-002"
        test_name = "Credit Failure with Automatic Rollback"
        verifications = []
        
        try:
            # Setup with credit failure mode
            controller, ledger = self.setup_test_environment(failure_mode="partial_success")
            ledger.set_account_balance("ACC-SOURCE-002", 1000.00)
            ledger.set_account_balance("ACC-DEST-CLOSED", 500.00)
            
            # Execute transfer (should fail)
            request = {
                "source_account": "ACC-SOURCE-002",
                "destination_account": "ACC-DEST-CLOSED",
                "amount": 150.00,
                "currency": "USD"
            }
            
            response = controller.create_transfer(request)
            
            # Verify response indicates failure
            verifications.append(
                self.verify_condition(
                    response.get("status") == "failed",
                    f"API response status is 'failed' (actual: {response.get('status')})"
                )
            )
            
            # Get transfer details
            txn_id = response.get("transaction_id")
            transfer = controller.service.get_transfer_status(txn_id)
            
            # Verify transfer state
            verifications.append(
                self.verify_condition(
                    transfer.state == TransferState.FAILED,
                    f"Transfer state is FAILED (actual: {transfer.state.value})"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    transfer.error_code == TransferErrorCode.CREDIT_FAILED,
                    f"Error code is CREDIT_FAILED (actual: {transfer.error_code})"
                )
            )
            
            # Verify rollback occurred
            verifications.append(
                self.verify_condition(
                    any("rolling_back" == t.to_state.value for t in transfer.state_history),
                    "Rollback state transition occurred"
                )
            )
            
            # Verify account balances restored
            source_balance = ledger.get_account_balance("ACC-SOURCE-002")
            dest_balance = ledger.get_account_balance("ACC-DEST-CLOSED")
            
            verifications.append(
                self.verify_condition(
                    source_balance == 1000.00,
                    f"Source balance restored to 1000.00 (actual: {source_balance})"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    dest_balance == 500.00,
                    f"Destination balance unchanged at 500.00 (actual: {dest_balance})"
                )
            )
            
            # All verifications passed?
            all_passed = all(v["passed"] for v in verifications)
            
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return TestResult(
                test_id=test_id,
                test_name=test_name,
                passed=all_passed,
                duration_ms=duration,
                verification_results=verifications
            )
            
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            return TestResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                duration_ms=duration,
                error_message=str(e),
                verification_results=verifications
            )
            
    # =========================================================================
    # TC-003: Network Timeout
    # =========================================================================
    
    def test_network_timeout(self) -> TestResult:
        """TC-003: Verify timeout handling"""
        start_time = datetime.utcnow()
        test_id = "TC-003"
        test_name = "Network Timeout with Retry and Rollback"
        verifications = []
        
        try:
            # Setup with timeout mode
            controller, ledger = self.setup_test_environment(failure_mode="timeout")
            ledger.set_account_balance("ACC-SOURCE-003", 1000.00)
            ledger.set_account_balance("ACC-DEST-003", 500.00)
            
            # Execute transfer (should timeout)
            request = {
                "source_account": "ACC-SOURCE-003",
                "destination_account": "ACC-DEST-003",
                "amount": 200.00,
                "currency": "USD"
            }
            
            response = controller.create_transfer(request)
            
            # Verify response indicates failure
            verifications.append(
                self.verify_condition(
                    response.get("status") in ["failed", "pending"],
                    f"API response status indicates timeout/failure (actual: {response.get('status')})"
                )
            )
            
            # Get transfer details
            txn_id = response.get("transaction_id")
            transfer = controller.service.get_transfer_status(txn_id)
            
            # Verify transfer state (timeout or failed)
            verifications.append(
                self.verify_condition(
                    transfer.state in [TransferState.TIMEOUT, TransferState.FAILED],
                    f"Transfer state is TIMEOUT or FAILED (actual: {transfer.state.value})"
                )
            )
            
            # Verify no partial operations
            source_balance = ledger.get_account_balance("ACC-SOURCE-003")
            dest_balance = ledger.get_account_balance("ACC-DEST-003")
            
            verifications.append(
                self.verify_condition(
                    source_balance == 1000.00,
                    f"Source balance unchanged at 1000.00 (actual: {source_balance})"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    dest_balance == 500.00,
                    f"Destination balance unchanged at 500.00 (actual: {dest_balance})"
                )
            )
            
            # All verifications passed?
            all_passed = all(v["passed"] for v in verifications)
            
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return TestResult(
                test_id=test_id,
                test_name=test_name,
                passed=all_passed,
                duration_ms=duration,
                verification_results=verifications
            )
            
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            return TestResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                duration_ms=duration,
                error_message=str(e),
                verification_results=verifications
            )
            
    # =========================================================================
    # TC-004: Debit Failure
    # =========================================================================
    
    def test_debit_failure(self) -> TestResult:
        """TC-004: Verify debit failure handling (no rollback needed)"""
        start_time = datetime.utcnow()
        test_id = "TC-004"
        test_name = "Debit Failure - No Rollback Needed"
        verifications = []
        
        try:
            # Setup with debit failure mode
            controller, ledger = self.setup_test_environment(failure_mode="debit_fail")
            ledger.set_account_balance("ACC-SOURCE-INSUFFICIENT", 100.00)
            ledger.set_account_balance("ACC-DEST-004", 500.00)
            
            # Execute transfer (should fail at debit)
            request = {
                "source_account": "ACC-SOURCE-INSUFFICIENT",
                "destination_account": "ACC-DEST-004",
                "amount": 5000.00,
                "currency": "USD"
            }
            
            response = controller.create_transfer(request)
            
            # Verify response indicates failure
            verifications.append(
                self.verify_condition(
                    response.get("status") == "failed",
                    f"API response status is 'failed' (actual: {response.get('status')})"
                )
            )
            
            # Get transfer details
            txn_id = response.get("transaction_id")
            transfer = controller.service.get_transfer_status(txn_id)
            
            # Verify transfer state
            verifications.append(
                self.verify_condition(
                    transfer.state == TransferState.FAILED,
                    f"Transfer state is FAILED (actual: {transfer.state.value})"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    transfer.error_code == TransferErrorCode.DEBIT_FAILED,
                    f"Error code is DEBIT_FAILED (actual: {transfer.error_code})"
                )
            )
            
            # Verify no rollback occurred (debit never succeeded)
            verifications.append(
                self.verify_condition(
                    not any("rolling_back" == t.to_state.value for t in transfer.state_history),
                    "No rollback state transition (debit never succeeded)"
                )
            )
            
            # Verify account balances unchanged
            source_balance = ledger.get_account_balance("ACC-SOURCE-INSUFFICIENT")
            dest_balance = ledger.get_account_balance("ACC-DEST-004")
            
            verifications.append(
                self.verify_condition(
                    source_balance == 100.00,
                    f"Source balance unchanged at 100.00 (actual: {source_balance})"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    dest_balance == 500.00,
                    f"Destination balance unchanged at 500.00 (actual: {dest_balance})"
                )
            )
            
            # All verifications passed?
            all_passed = all(v["passed"] for v in verifications)
            
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return TestResult(
                test_id=test_id,
                test_name=test_name,
                passed=all_passed,
                duration_ms=duration,
                verification_results=verifications
            )
            
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            return TestResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                duration_ms=duration,
                error_message=str(e),
                verification_results=verifications
            )
            
    # =========================================================================
    # TC-005: Audit Trail Verification
    # =========================================================================
    
    def test_audit_trail_verification(self) -> TestResult:
        """TC-005: Verify comprehensive audit logging"""
        start_time = datetime.utcnow()
        test_id = "TC-005"
        test_name = "Complete Audit Trail Verification"
        verifications = []
        
        try:
            # Setup
            controller, ledger = self.setup_test_environment(failure_mode=None)
            ledger.set_account_balance("ACC-SOURCE-005", 1000.00)
            ledger.set_account_balance("ACC-DEST-005", 500.00)
            
            # Execute transfer
            request = {
                "source_account": "ACC-SOURCE-005",
                "destination_account": "ACC-DEST-005",
                "amount": 250.00,
                "currency": "USD"
            }
            
            response = controller.create_transfer(request)
            
            # Verify transaction ID format
            txn_id = response.get("transaction_id")
            verifications.append(
                self.verify_condition(
                    txn_id and txn_id.startswith("TXN-") and len(txn_id) == 16,
                    f"Transaction ID has correct format (TXN-XXXXXXXXXXXX): {txn_id}"
                )
            )
            
            # Get transfer details
            transfer = controller.service.get_transfer_status(txn_id)
            
            # Verify state history (audit trail)
            verifications.append(
                self.verify_condition(
                    len(transfer.state_history) > 0,
                    f"State history exists ({len(transfer.state_history)} transitions)"
                )
            )
            
            # Verify key state transitions exist
            state_values = [t.to_state.value for t in transfer.state_history]
            
            verifications.append(
                self.verify_condition(
                    "validating" in state_values,
                    "VALIDATING state in history"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    "pending" in state_values,
                    "PENDING state in history"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    "debit_completed" in state_values,
                    "DEBIT_COMPLETED state in history"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    "credit_processing" in state_values,
                    "CREDIT_PROCESSING state in history"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    "completed" in state_values,
                    "COMPLETED state in history"
                )
            )
            
            # Verify timestamps are sequential
            timestamps = [t.timestamp for t in transfer.state_history]
            sequential = all(timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1))
            
            verifications.append(
                self.verify_condition(
                    sequential,
                    "State transition timestamps are sequential"
                )
            )
            
            # Verify ledger references exist
            verifications.append(
                self.verify_condition(
                    transfer.ledger_debit_ref is not None,
                    f"Ledger debit reference exists: {transfer.ledger_debit_ref}"
                )
            )
            
            verifications.append(
                self.verify_condition(
                    transfer.ledger_credit_ref is not None,
                    f"Ledger credit reference exists: {transfer.ledger_credit_ref}"
                )
            )
            
            # All verifications passed?
            all_passed = all(v["passed"] for v in verifications)
            
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return TestResult(
                test_id=test_id,
                test_name=test_name,
                passed=all_passed,
                duration_ms=duration,
                verification_results=verifications
            )
            
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            return TestResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                duration_ms=duration,
                error_message=str(e),
                verification_results=verifications
            )
            
    # =========================================================================
    # Test Execution
    # =========================================================================
    
    def run_all_tests(self) -> List[TestResult]:
        """Execute all test cases"""
        print("=" * 80)
        print("Transfer Integration Test Suite - Fixed_Transfer_Flow_v2")
        print("=" * 80)
        print()
        
        tests = [
            ("TC-001", self.test_normal_success_path),
            ("TC-002", self.test_credit_failure_with_rollback),
            ("TC-003", self.test_network_timeout),
            ("TC-004", self.test_debit_failure),
            ("TC-005", self.test_audit_trail_verification)
        ]
        
        results = []
        
        for test_id, test_func in tests:
            print(f"Running {test_id}: {test_func.__doc__}")
            result = test_func()
            results.append(result)
            
            status = "✓ PASSED" if result.passed else "✗ FAILED"
            print(f"  {status} ({result.duration_ms:.2f}ms)")
            
            if not result.passed and result.error_message:
                print(f"  Error: {result.error_message}")
                
            print()
            
        self.results = results
        return results
        
    def print_summary(self):
        """Print test execution summary"""
        print("=" * 80)
        print("Test Summary")
        print("=" * 80)
        print()
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed/total*100):.1f}%")
        print()
        
        if failed > 0:
            print("Failed Tests:")
            for result in self.results:
                if not result.passed:
                    print(f"  - {result.test_id}: {result.test_name}")
                    if result.error_message:
                        print(f"    Error: {result.error_message}")
            print()
            
        total_duration = sum(r.duration_ms for r in self.results)
        print(f"Total Duration: {total_duration:.2f}ms")
        print()
        
    def generate_json_report(self, output_file: str = "test_results.json"):
        """Generate JSON test report"""
        report = {
            "test_suite": "Transfer Integration Tests",
            "version": "2.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total": len(self.results),
                "passed": sum(1 for r in self.results if r.passed),
                "failed": sum(1 for r in self.results if not r.passed),
                "duration_ms": sum(r.duration_ms for r in self.results)
            },
            "tests": [
                {
                    "test_id": r.test_id,
                    "test_name": r.test_name,
                    "passed": r.passed,
                    "duration_ms": r.duration_ms,
                    "error_message": r.error_message,
                    "verifications": r.verification_results
                }
                for r in self.results
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
            
        print(f"JSON report saved to: {output_file}")


def main():
    """Main test execution"""
    suite = TransferIntegrationTests()
    
    # Run all tests
    results = suite.run_all_tests()
    
    # Print summary
    suite.print_summary()
    
    # Generate JSON report
    suite.generate_json_report("test_results.json")
    
    # Exit with appropriate code
    all_passed = all(r.passed for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
