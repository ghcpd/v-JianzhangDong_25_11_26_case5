#!/usr/bin/env python3
"""
Main test runner wrapper

Executes the transfer module test suite with a single command.
Usage: python run_tests.sh  (or ./run_tests.sh on Unix)

This script:
1. Sets up the environment
2. Runs the integration test suite
3. Collects and formats results
4. Reports pass/fail status
"""

import subprocess
import sys
import os
from pathlib import Path


def run_tests():
    """Execute the transfer module test suite"""
    
    # Get project root
    script_dir = Path(__file__).parent.absolute()
    project_root = script_dir
    
    print("\n" + "="*70)
    print("  TRANSFER MODULE TEST SUITE RUNNER")
    print("="*70)
    print(f"\nProject root: {project_root}")
    print(f"Working directory: {os.getcwd()}")
    
    # Step 1: Setup environment
    print("\n" + "-"*70)
    print("Step 1: Setting up environment...")
    print("-"*70)
    
    setup_script = project_root / "setup.sh"
    if setup_script.exists():
        result = subprocess.run(
            [sys.executable, str(setup_script)],
            cwd=project_root
        )
        if result.returncode != 0:
            print("\n✗ Setup failed")
            return 1
    
    # Step 2: Run integration tests
    print("\n" + "-"*70)
    print("Step 2: Running integration tests...")
    print("-"*70)
    
    test_runner = project_root / "tests" / "run_suite.py"
    if not test_runner.exists():
        print(f"\n✗ Test runner not found: {test_runner}")
        return 1
    
    result = subprocess.run(
        [sys.executable, str(test_runner)],
        cwd=project_root
    )
    
    test_passed = result.returncode == 0
    
    # Step 3: Print summary
    print("\n" + "="*70)
    print("  FINAL RESULTS")
    print("="*70)
    
    if test_passed:
        print("\n✓ ALL TESTS PASSED")
        print("\nDeliverables:")
        print("  ✓ src/ — Fixed transfer module with state machine")
        print("  ✓ docs/root_cause_analysis.md — Root cause diagnosis")
        print("  ✓ docs/remediation_plan.md — Implementation roadmap")
        print("  ✓ tests/integration/transfer_cases.yaml — Test scenarios")
        print("  ✓ tests/run_suite.py — Test runner")
        print("  ✓ mocks/mock_ledger_service.py — Mock ledger")
        print("  ✓ logs/audit_schema.json — Audit logging schema")
        print("  ✓ requirements.txt — Dependencies")
        print("  ✓ setup.sh — Environment setup")
        print("  ✓ run_tests.sh — Test runner wrapper")
        print("\nNext steps:")
        print("  1. Review root_cause_analysis.md for problem diagnosis")
        print("  2. Review remediation_plan.md for implementation details")
        print("  3. Run tests again: python run_tests.sh")
        print("  4. Deploy fixed backend to test environment")
        return 0
    else:
        print("\n✗ TESTS FAILED")
        print("\nPlease review the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
