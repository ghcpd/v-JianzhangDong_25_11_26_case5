# Root Cause Analysis — Fixed_Transfer_Flow_v2

Summary
-------
This diagnostic focuses on a fault where the UI/API reports "Transfer Successful" while the core ledger never posts debit/credit. After tracing the asynchronous flow and logs, the following root causes were discovered:

- Asynchronous acknowledgement: the API previously returned success immediately after enqueuing a request without waiting for ledger confirmation.
- Missing or weak state machine transitions: the transfer lifecycle lacked a guaranteed atomicity boundary; it didn't require both debit and credit confirmations before emitting final success.
- Retry/Compensation gaps: failures during credit led to no deterministic compensating debit rollback mechanism.
- Lack of audit logs and strong transaction IDs: insufficient structured logging made it hard to reconcile which transfers were partially applied.

Evidence snapshot
-----------------

Flow map (short):

1. Client -> API: submit transfer
2. API -> Orchestrator: create transaction record (state INITIATED)
3. Orchestrator -> Ledger: post debit (async)
4. Orchestrator -> Ledger: post credit (async)
5. API returns 'success' to UI as soon as both tasks enqueued

Where failures manifest (observed by analyzing logs and state):

- Missing state change: Records remained in INITIATED or DEBIT_POSTED without ever reaching CREDIT_POSTED/COMPLETED.
- Failed callback propagation: ledger async callback sometimes failed to update transaction status, leaving it in an inconsistent state.
- No rollback: if debit was applied but credit failed, no compensating transaction was guaranteed or retry eventually left the debit applied while credit never posted.

Observations from simulated logs
-------------------------------

Example early log line (problem):

> INFO api| tx=12345 | state=initiated | enqueued transfer -> RESP: client: success

Later, ledger logs show:

> ERROR ledger| tx=12345 | debit: ok
> ERROR ledger| tx=12345 | credit: error: timeout

But the API never receives or reconciles the failed credit; the UI still shows success.

Concluding root cause
---------------------

Primary root cause: race condition across the enqueue-and-ack boundary — the service returned success too early and lacked sufficient state transitions and compensation to ensure ledger-level consistency.
