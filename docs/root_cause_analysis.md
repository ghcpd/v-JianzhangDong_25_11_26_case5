# Root Cause Analysis: Fixed_Transfer_Flow_v2 — "False Success"

## Summary

A "false success" occurs when the UI/API returns success for a transfer while the core ledger did not commit both the debit and the credit operations. This issue arises in asynchronous flows when only part of the state machine completes and the final status is not tied to final ledger confirmation.

## Transfer Lifecycle (init → in-progress → success/failure)

- INIT: Transfer requested; basic validation done; transaction record created (tx_id).
- IN_PROGRESS: Debit requested and likely committed in the ledger’s reservation or posting.
- CREDIT: Credit requested for beneficiary; can fail or be delayed.
- FINAL: If both debit and credit are committed => SUCCESS; otherwise if any operation fails without rollback => FAILED.

## Observed Failure Patterns

- Async Posting Failure: UI obtains a positive response due to in-memory state or a prematurely set state field, while the credit was never executed or failed later.
- Transient Network Failures: Debit committed, then credit call times out; the UI times out too and assumes success while actual ledger is incomplete.
- Missing Rollback: Debit succeeded but credit failed; rollback wasn't triggered or completed; partial ledger state leads to money being debited but not credited.
- State-Machine Gaps: Lack of idempotency and dependency checks (e.g., marking a transaction SUCCESS if debit started but before credit completed).

## Evidence (logs/state)

- Controller logs showing `debit` success and `credit` failure with the same `tx_id`.
- Ledger state showing committed `debit` op but no `credit` op under the tx_id.
- Absence of rollback or rollback not being completed: no `rolled_back` log entries for the tx_id.

### Example (simplified log evidence)

- "{timestamp, tx_id: X, service: ledger, event: debit, status: committed}"
- "{timestamp, tx_id: X, service: ledger, event: credit, status: transient_failed}"
- "{timestamp, tx_id: X, service: controller, event: complete, status: success}"

## Root Causes

1. UI/API success is derived from application cache or optimistic UI response rather than final ledger commit.
2. State machine allowed progress to SUCCESS on partial commits (debit only).
3. Retry and rollback logic did not ensure idempotency and ledger restoration in failure cases.
4. Lack of end-to-end audit hooks and transaction reconciliation to detect and repair partial completions.

## Impact

- Customer-facing inconsistency (balance mismatch and poor trust).
- Potential monetary loss or double-deduct situations.
- Increased operational overhead for reconciliation.

---

## Next steps proposed by remediation plan
Refer to `docs/remediation_plan.md` for the prioritized remediation tasks and testing plan.
