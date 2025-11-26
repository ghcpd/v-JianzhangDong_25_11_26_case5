## Root Cause Analysis — Fixed_Transfer_Flow_v2

Summary:

- The bug appeared when the transfer API returned "success" to UX while the ledger had not yet completed debit/credit due to async queueing and absence of final-state gating between the API and ledger commit confirmation.
- Causes:
  1. Immediate response mode incorrectly used when caller expected synchronous semantics — the API acknowledged acceptance rather than completion.
  2. Missing state machine to prevent a success state transition until both debit and credit events had unequivocally succeeded.
  3. Lack of idempotency and retries in the core ledger adapter allowed partial commits without reliable rollbacks.
  4. Missing audit hooks — logs lacked unique transaction identifiers and causal traces across async boundaries.

Lifecycle mapping (init -> in-progress -> success/failure):

1. API: initiate_transfer -> creates tx_id and writes record INITIATED
2. Queue: event enqueued for processing
3. Worker: marks record IN_PROGRESS and attempts ledger debit
4. Ledger: debit may succeed or fail (retry/timeout)
5. If debit succeeds -> attempt credit; if credit fails -> attempt reverse(debit) -> final state ROLLEDBACK or FAILED
6. If both succeed -> state SUCCEEDED; system emits audit log

Where silent failures can occur:
 - Network errors during credit after debit succeeded (partial commit)
 - Retry limitations (retries exhausted) causing inconsistent partial commits
 - Worker exceptions without rollbacks
 - Lack of idempotency causing double-debits or double credits on retries

Evidence and log examples:

- Example log: {"tx_id": "..., "event": "transfer.succeeded", "from": "A***", "to": "B***", "amount": 100}
- When a partial commit is found, audit should show debit succeeded, credit failed, then rollback attempted.

Breakpoints / Evidence table:

| Stage | Failure Mode | Evidence (logs, state) |
|-------|--------------|------------------------|
| enqueue -> worker | event lost or worker exception | no IN_PROGRESS log or event missing with tx_id |
| debit | network failure or insufficient funds | debit failed audit entry and state = FAILED |
| credit | network failure after debit succeeded | audit showing debit success, credit failed, then no rollback |
| rollback | rollback omitted or fails | debit present in ledger but transaction state marked SUCCEEDED |

