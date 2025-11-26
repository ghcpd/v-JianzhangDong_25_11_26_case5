# Remediation Plan — Fixed_Transfer_Flow_v2

Goals
-----
- Guarantee that success is only reported after debit and credit complete (atomicity at the user-visible level).
- Provide robust retry and compensating rollback mechanisms.
- Add structured auditing and tracing for post-incident reconciliation.

Priority tasks
--------------

1. Implement an explicit transfer state machine (initiated → debit_posted → credit_posted → completed / failed). Make all state transitions idempotent and persisted.
2. Change API acknowledgement policy: only return `success` when the transfer reaches the `COMPLETED` state. If posting is still in-flight, return `in-progress`.
3. Implement ledger posting with retry semantics and backoff for transient failures.
4. Implement deterministic compensation: if debit succeeds but credit ultimately fails, run a rollback of the debit (or schedule compensation) and set state to `FAILED`.
5. Add structured logs including unique transaction id, state transitions, non-sensitive references to accounts, retry attempts and decisions.
6. Add audit hooks: emit compact immutable audit lines (JSON) for every significant lifecycle event for reconciliation.
7. Add integration tests verifying each failure and retry/rollback path.

Operational considerations
------------------------

- Add an asynchronous reconciler job to detect "stuck" transactions and attempt remediation or generate operational alerts.
- Ensure safe idempotency keys when posting operations to ledger to prevent double-debits on retry.

Milestones
----------

1. Developer changes and unit tests (2 days) — implement transfer state machine, ledger adapter, and structured logs.
2. Integration tests + mocks (1 day) — create repeatable tests covering at least five failure/success scenarios.
3. Staging run and reconciliation tool (2 days) — run long-tail tests and add a reconciler for production monitoring.
