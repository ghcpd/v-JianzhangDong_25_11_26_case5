# Fixed_Transfer_Flow_v2 – Root Cause Analysis

## Summary
**Defect:** UI/API reported **"transfer successful"** while the core ledger **never debited/credited** funds. 

**Root causes:**
- **Async ledger posting failures were not propagated** to the status chain.
- **State machine gaps** allowed transitions to *Success* without confirming ledger completion.
- **Rollback omissions:** Debit remained posted when credit failed/timeouts occurred.
- **Insufficient audit/reconciliation data** to trace discrepancies.

## Transfer Lifecycle Map

| Stage | State | Trigger | Expected Exit | Failure Risks |
|-------|-------|---------|---------------|---------------|
| Init | `INIT` | Request accepted | `DEBIT_PENDING` | Input validation errors |
| Debit posted | `DEBIT_PENDING` | Ledger `post_debit` | `DEBIT_CONFIRMED` on `COMPLETED` | Post failure, network error |
| Debit confirmed | `DEBIT_CONFIRMED` | Ledger `poll_status` | `CREDIT_PENDING` | Poll timeout, failed status |
| Credit posted | `CREDIT_PENDING` | Ledger `post_credit` | `COMPLETED` on `COMPLETED` | Credit post failure, poll timeout |
| Success | `COMPLETED` | Debit+Credit confirmed | — | — |
| Failure | `FAILED` | Any unrecoverable error | — | — |
| Rollback | `ROLLED_BACK` | Credit failure after debit | — | Rollback failure |

**Diagram:**
```
INIT ──post_debit──> DEBIT_PENDING ──confirm──> DEBIT_CONFIRMED ──post_credit──> CREDIT_PENDING ──confirm──> COMPLETED
   \                           \                        \                         \_failure-> ROLLED_BACK
    \_failure-> FAILED          \_failure-> FAILED        \_failure-> FAILED
```

## Breakpoints & Evidence

| Breakpoint | Description | Evidence (Integration Case) | Observed State | Fix |
|------------|-------------|-----------------------------|----------------|-----|
| Debit post failure | `post_debit` errors not surfaced; UI showed success | `debit_post_failure` | `FAILED` (now) | Retry, fail-fast, audit drill-down |
| Network retry gap | First post attempt fails, success on retry not handled | `network_retry_then_success` | `COMPLETED` | Bounded retries with logging |
| Credit timeout | Debit confirmed but credit never completes; no rollback | `credit_timeout_with_rollback` | `ROLLED_BACK` | Automatic rollback + audit |
| Async status gap | State advanced without confirmed ledger completion | `normal_success` confirms both legs | `COMPLETED` only after both confirmations | State machine gating |
| Audit visibility | No structured correlation IDs to reconcile | `audit_verification` | Masked accounts, txn_id, corr_id | JSON structured logging |

### Sample Structured Log (masked)
```json
{
  "timestamp": "2025-11-26T12:00:00.123Z",
  "level": "info",
  "event": "DEBIT_POSTED",
  "txn_id": "f8a0...",
  "correlation_id": "corr-debit-1-1",
  "state": "DEBIT_PENDING",
  "source_account": "12****78",
  "destination_account": "87****21",
  "amount": 100.0,
  "currency": "USD"
}
```

## Root Cause Details
1. **Async posting failures suppressed:** Exceptions in `post_debit/post_credit` were caught upstream but not reflected in the final status; UI assumed success. 
2. **State-machine gaps:** Success state was reachable without confirmed ledger statuses.
3. **Rollback omissions:** No compensating action when credit failed after successful debit.
4. **Lack of audit identifiers:** Missing `txn_id`/`correlation_id` prevented reconciliation; sensitive data was logged unmasked.

## Remediation Overview
- **Strict state machine gating**: success only after **debit + credit confirmed**.
- **Bounded retries** for posting and polling with explicit failure states.
- **Automatic rollback** on credit failure/timeouts; propagate rollback results.
- **Structured JSON logging** with **masked accounts**, `txn_id`, and `correlation_id`.
- **Integration suite** covering five critical scenarios via `tests/run_suite.py`.
