## Remediation Plan — Fixed_Transfer_Flow_v2

Objectives:
 - Ensure the API only reports success after ledger debit and credit are confirmed.
 - Ensure idempotency and retries are in place for ledger operations.
 - Add rollback and audit mechanisms for partial failures.
 - Provide better observability with structured logs and unique tx identifiers.

High-level steps (priority ordered):
1. Implement transfer state machine and a queue-based worker that only transitions to SUCCEEDED when ledger confirms both sides.
2. Add LedgerAdapter with built-in retries and idempotent operation semantics.
3. Add rollback logic to reverse debit if credit fails; retries on reversal if needed.
4. Add audit log hooks at each state change and include tx_id, masked account ids, and operation outcomes.
5. Add integration tests simulating success/failure/retry/rollback cases.

Notes on deployment and backward compatibility:
 - Default behavior remains async acceptance/pending for backward compatibility; an optionally-synchronous mode blocks for final-state confirmation for critical flows.

Validation and monitoring:
 - Implement checks for transactions stuck IN_PROGRESS beyond a configured SLA; escalate and reconcile with ledger.
 - Implement a reconciliation job to detect partial commits or missing rollbacks and auto-remediate or alert.
