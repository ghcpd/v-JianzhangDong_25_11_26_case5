#!/usr/bin/env python3
"""
Transfer Test Suite Executor

Detailed test execution script with metrics and reporting.
Called by run_tests.sh and scripts/run_transfer_suite.sh

Features:
- Runs all 5 transfer test scenarios
- Collects detailed metrics
- Generates human-readable and JSON reports
- Validates all assertions
"""

import asyncio
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.run_suite import TransferTestSuite


async def run_test_suite() -> int:
    """Run the full test suite and report results"""
    
    suite = TransferTestSuite()
    
    start_time = time.time()
    
    try:
        await suite.run_all_scenarios()
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    elapsed = time.time() - start_time
    
    # Generate report
    report = _generate_report(suite, elapsed)
    
    # Print report
    print("\n" + "="*70)
    print("  DETAILED TEST REPORT")
    print("="*70 + "\n")
    
    print(json.dumps(report, indent=2))
    
    # Save report
    report_file = Path(__file__).parent.parent / "logs" / "test_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✓ Report saved to: {report_file}")
    
    # Determine exit code
    all_passed = all(r.passed for r in suite.results)
    return 0 if all_passed else 1


def _generate_report(suite: TransferTestSuite, elapsed: float) -> Dict[str, Any]:
    """Generate test report"""
    
    passed = sum(1 for r in suite.results if r.passed)
    failed = sum(1 for r in suite.results if r.failed)
    
    scenarios = []
    for result in suite.results:
        scenario_report = {
            'name': result.scenario_name,
            'passed': result.passed,
            'failed': result.failed,
            'duration_seconds': result.duration_seconds,
            'error': result.error,
            'assertions': [
                {
                    'description': desc,
                    'passed': passed_val,
                    'error': err
                }
                for desc, passed_val, err in result.assertions
            ],
            'metrics': result.metrics
        }
        scenarios.append(scenario_report)
    
    return {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'summary': {
            'total_scenarios': len(suite.results),
            'passed': passed,
            'failed': failed,
            'total_duration_seconds': elapsed,
            'all_passed': all(r.passed for r in suite.results)
        },
        'scenarios': scenarios
    }


if __name__ == "__main__":
    exit_code = asyncio.run(run_test_suite())
    sys.exit(exit_code)
