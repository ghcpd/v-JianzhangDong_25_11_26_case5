#!/usr/bin/env python3
"""
Direct test runner - bypasses shell script issues
Run with: python test_runner.py
"""

import asyncio
import sys
sys.path.insert(0, '.')

from tests.run_suite import TransferTestSuite


async def main():
    """Run all test scenarios"""
    suite = TransferTestSuite()
    await suite.run_all_scenarios()
    exit_code = suite._print_results()
    return exit_code


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code if exit_code is not None else 0)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Test suite was interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
