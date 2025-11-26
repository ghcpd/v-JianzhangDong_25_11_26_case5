# Remediation Plan — Fixed_Transfer_Flow_v2 (Transfer Consistency)

## Goal
Guarantee that the system only reports success to the API/UI once both debit and credit operations are committed in the ledger and audit logs reflect that state.

## High-level Changes

1. Make the final state dependent on the ledger's idempotent commit acknowledgement for both debit and credit.
2. Implement idempotent, atomic operations with `tx_id` so retries are safe.
3. Add robust retry logic with exponential backoff for transient errors; on exhaustion, perform an atomic rollback and mark the transaction as FAILED.
4. Add audit hooks and structured logs (with tx_id) for all operations.
5. Add reconciliation tasks that periodically scan in-progress or failed transactions to detect partial commits and remediate.

## Code-level Tasks (Priority: P1/P2)

- P1: Modify transfer state machine to move to SUCCESS only upon both operations' succeed; any partial commit triggers rollback.
  - Already implemented in the `TransferManager` class — ensure production integration uses persistent store for `tx_id` states.
- P1: Enforce idempotency in the ledger adapter and ledger service with tx_id keys.
  - `mock_ledger_service` demonstrates this with per-tx states.
- P1: Add structured JSON logging for each action with tx_id; add audit schema `logs/audit_schema.json`.
- P1: Add deterministic retry behavior and a finite retry count; if retries exhaust, perform a rollback immediately.
- P2: Add a reconciliation job for in-flight transactions older than certain thresholds.
- P2: Add monitoring and alerts for inconsistent states (e.g., debit committed but no credit after timeout).

## Testing Strategy

- Add integration tests covering: success, permanent failures, transient retry, timeout rollback, and audit verification.
- Add unit tests for TransferManager and ledger adapter.
- Add property-based testing for idempotency (ensuring second requests don’t double-deduct).

## Operational Considerations

- Add alerts for `partial_commit` patterns in logs.
- Ensure rollback is atomic and logged with `tx_id` and `reason`.
- Implement reconciliation and manual remediation procedures with clear steps.

## Timeline
1. Immediate (1-3 days): Change to state machine and idempotency; unit and integration tests for critical paths.
2. Short term (1-2 weeks): Instrument production with JSON logs and monitoring, add reconciliation jobs.
3. Long term: Integrate with real ledger via adapter gRPC/HTTP; add auditing and cross-service distributed tracing for deeper visibility.
