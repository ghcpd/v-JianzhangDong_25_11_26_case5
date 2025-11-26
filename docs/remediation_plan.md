# Remediation Plan: Fixed_Transfer_Flow_v2

## Overview

This document outlines the architecture and prioritized implementation plan to resolve the "false success" defect in the Mobile Banking Transfer Module. The solution ensures that success acknowledgments are **never** returned until both debit and credit operations are confirmed complete in the core ledger.

---

## 1. Architecture Changes

### Current (Broken) Architecture

```
Frontend
  ↓ (HTTP POST /transfer)
API Controller
  ↓ (validate & queue)
Transfer DB (status='INITIATED')
  ↓ (immediate 200 OK response) ← BUG: Returns success too early!
Frontend gets "Transfer Successful"
  ↓ (async, in background)
Transfer Worker
  ↓ (picks up from queue)
Ledger Service (debit request)
  ↓ (debit succeeds/fails, callback may be lost)
Ledger Service (credit request)
  ↓ (credit succeeds/fails, no compensation if fails)
Transfer DB (state=INITIATED or PENDING, never updated)
```

### Fixed Architecture

```
Frontend
  ↓ (HTTP POST /transfer with correlation_id)
API Controller
  ↓ (validate & queue with correlation_id)
Transfer DB (status='INITIATED')
  ↓ (returns 202 ACCEPTED, NOT 200 OK)
Frontend gets "Transfer In Progress"
  ↓
Worker polls or subscribes to status updates
  ↓ (async worker picks up from queue)
Transfer Worker
  ↓ (registers callback handlers upfront)
Ledger Service (debit request with idempotency_key)
  ↓ (ledger posts debit, returns callback_url)
Ledger Callback (debit complete) ← Idempotent handler
  ↓ (updates Transfer DB: state='DEBIT_POSTED')
Transfer Worker
  ↓ (checks state, proceeds to credit)
Ledger Service (credit request with idempotency_key)
  ↓ (ledger posts credit, returns callback_url)
Ledger Callback (credit complete) ← Idempotent handler
  ↓ (updates Transfer DB: state='SUCCESS')
Frontend polls and gets "Transfer Successful"
  ↓ (or via webhook/event pushed to frontend)
Audit Log (structured, correlation_id, ledger_txn_ids, amounts)
```

---

## 2. Key Design Principles

### Principle 1: Idempotency
Every external call (ledger debit/credit, callback handling) must be idempotent. Use:
- **Idempotency Keys:** Unique identifier sent to ledger; ledger returns same result if called twice
- **State Machine Guards:** Only transition if current state matches expectations

### Principle 2: Reliable Callbacks
- Callback handlers must acknowledge receipt to prevent retry storms
- Callbacks are persisted (in a queue) before being sent
- Retries use exponential backoff

### Principle 3: Compensating Transactions
- If credit fails after debit succeeds, initiate reverse debit immediately
- Reverse operations use same idempotency key logic
- Mark original transfer as FAILED with reverse_txn_id for traceability

### Principle 4: State Durability
- Every state transition is logged to audit table
- Transfers can be reconciled by scanning DB for PENDING states older than timeout
- Background job attempts recovery or alerts operations

### Principle 5: Audit Trail
- Every API call, ledger operation, callback, and state change is logged
- Logs include correlation_id, timestamps, amounts (redacted if needed), and results
- No sensitive data (e.g., full account numbers) in logs

---

## 3. Implementation Breakdown

### Phase 1: Core State Machine & Persistence (Immediate)

**Files:**
- `src/models/transfer.py` — Transfer ORM model with state machine
- `src/state_machine.py` — State transition logic and guards
- `src/audit_log.py` — Audit log model and writer

**Changes:**
1. Add state machine enum: INITIATED, PENDING_DEBIT, DEBIT_POSTED, PENDING_CREDIT, SUCCESS, FAILED, ROLLEDBACK
2. Add `idempotency_key` field to Transfer model (UUID, unique per request)
3. Add `ledger_debit_txn_id` and `ledger_credit_txn_id` fields to link to ledger operations
4. Add `correlation_id` field for audit tracing
5. Add `timeout_at` field to enforce max-wait (e.g., 30 seconds per state)
6. Implement state transition method with guards: `transfer.transition_to(new_state, reason)`
7. Create AuditLog table: correlation_id, step, timestamp, actor, details (JSON), result

**Example:**
```python
class Transfer(Base):
    id: UUID
    correlation_id: str  # Unique per API request
    idempotency_key: str  # For ledger calls
    state: TransferState  # Enum
    amount: Decimal
    sender_account: str
    recipient_account: str
    ledger_debit_txn_id: Optional[str]  # Set by callback
    ledger_credit_txn_id: Optional[str]  # Set by callback
    timeout_at: datetime
    created_at: datetime
    updated_at: datetime

    def can_transition_to(self, new_state) -> bool:
        # Guard logic
        valid_transitions = {
            INITIATED: [PENDING_DEBIT, FAILED],
            PENDING_DEBIT: [DEBIT_POSTED, FAILED],
            DEBIT_POSTED: [PENDING_CREDIT, FAILED],
            PENDING_CREDIT: [SUCCESS, FAILED],
            FAILED: [ROLLEDBACK],
            ...
        }
        return new_state in valid_transitions[self.state]

    async def transition_to(self, new_state, reason: str = None):
        if not self.can_transition_to(new_state):
            raise InvalidTransition(f"{self.state} → {new_state}")
        self.state = new_state
        self.updated_at = now()
        await self.save()
        await log_audit(self.correlation_id, step=f"state_transition", details={
            "from": self.state, "to": new_state, "reason": reason
        })
```

### Phase 2: Mock Ledger Service (Immediate)

**Files:**
- `mocks/mock_ledger_service.py` — Simulates core ledger with configurable responses

**Features:**
1. Implements debit/credit endpoints with realistic latency (0-500ms)
2. Can be configured to fail, timeout, or succeed
3. Returns `transaction_id` and `callback_url` for async notification
4. Tracks calls for assertions in tests (e.g., "debit was called exactly once")
5. Simulates network partitions (no callback sent)

**Example:**
```python
class MockLedgerService:
    def __init__(self):
        self.debit_calls = []
        self.credit_calls = []
        self.failure_mode = None  # 'fail', 'timeout', 'no_callback', None

    async def post_debit(self, txn_id: str, idempotency_key: str, 
                        amount: Decimal, callback_url: str) -> LedgerResponse:
        if self.failure_mode == 'fail':
            return LedgerResponse(status='FAILED', reason='Insufficient funds')
        if self.failure_mode == 'timeout':
            await asyncio.sleep(31)  # Exceed timeout
            return LedgerResponse(status='TIMEOUT')
        
        self.debit_calls.append({
            'txn_id': txn_id, 'idempotency_key': idempotency_key, 'amount': amount
        })
        
        if self.failure_mode != 'no_callback':
            # Async: schedule callback
            asyncio.create_task(self.send_callback(callback_url, status='SUCCESS'))
        
        return LedgerResponse(status='PENDING', ledger_txn_id='LEDGER-123', 
                            callback_url=callback_url)
```

### Phase 3: Transfer Controller & API (Phase 1 + 2)

**Files:**
- `src/controllers/transfer_controller.py` — HTTP endpoints
- `src/services/transfer_service.py` — Business logic

**Endpoints:**
1. `POST /transfers` — Initiate transfer (returns 202 ACCEPTED with correlation_id)
2. `GET /transfers/{correlation_id}` — Poll transfer status
3. `POST /webhooks/ledger/callback` — Receive ledger callbacks (idempotent)

**Logic:**
- Endpoint 1: Validate input, generate correlation_id & idempotency_key, save to DB in INITIATED state, queue async work, return 202 with status_url
- Endpoint 2: Query DB, return current state and any error reason
- Endpoint 3: Verify callback signature, idempotently update transfer state, return 200 OK

**Example:**
```python
@app.post("/transfers")
async def initiate_transfer(req: TransferRequest, service: TransferService) -> TransferResponse:
    correlation_id = generate_uuid()
    idempotency_key = generate_uuid()
    
    transfer = await service.create_transfer(
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        sender=req.sender_account,
        recipient=req.recipient_account,
        amount=req.amount
    )
    
    # Queue async work
    await service.queue_worker_task(transfer.id)
    
    return TransferResponse(
        status='IN_PROGRESS',
        correlation_id=correlation_id,
        status_url=f'/transfers/{correlation_id}'
    )
```

### Phase 4: Transfer Worker (async processing)

**Files:**
- `src/workers/transfer_worker.py` — Async job processor

**Logic:**
1. Pick up transfer from queue (state=INITIATED)
2. Register callback handlers for debit & credit
3. Call ledger.post_debit with idempotency_key and callback_url
4. Wait for callback or timeout (with exponential backoff)
5. Verify debit_posted state; if failed or timeout, transition to FAILED
6. If successful, call ledger.post_credit with new idempotency_key
7. Wait for callback or timeout
8. If successful, transition to SUCCESS
9. If credit failed, initiate compensating (reverse) debit transaction
10. Handle all exceptions with structured logging

**Example:**
```python
async def process_transfer(transfer_id: UUID):
    transfer = await Transfer.get(transfer_id)
    
    try:
        await transfer.transition_to(TransferState.PENDING_DEBIT)
        
        callback_url = f"{CONFIG.callback_base_url}/ledger/debit/{transfer.id}"
        debit_resp = await ledger_service.post_debit(
            txn_id=str(transfer.id),
            idempotency_key=transfer.idempotency_key,
            amount=transfer.amount,
            callback_url=callback_url
        )
        
        # Store ledger txn id
        transfer.ledger_debit_txn_id = debit_resp.ledger_txn_id
        await transfer.save()
        
        # Wait for callback with timeout
        state = await wait_for_state(transfer.id, target=TransferState.DEBIT_POSTED, 
                                     timeout=30)
        if state != TransferState.DEBIT_POSTED:
            raise TimeoutError(f"Debit timeout for {transfer.id}")
        
        # Proceed to credit
        await transfer.transition_to(TransferState.PENDING_CREDIT)
        credit_resp = await ledger_service.post_credit(...)
        
        # ... similar credit flow ...
        
        await transfer.transition_to(TransferState.SUCCESS)
        
    except Exception as e:
        await handle_transfer_failure(transfer, e)
```

### Phase 5: Callback Handler (Idempotent)

**Files:**
- `src/handlers/ledger_callback_handler.py`

**Logic:**
1. Receive callback (contains transfer_id, operation_type, status, ledger_txn_id)
2. Verify callback signature (if needed)
3. Fetch transfer; check if already processed
4. Based on operation_type and current state, update accordingly
5. Transition state if appropriate
6. Log audit entry
7. Return 200 OK (ledger will retry until it sees 200)

**Example:**
```python
@app.post("/webhooks/ledger/callback")
async def ledger_callback(callback: LedgerCallback) -> dict:
    transfer_id = UUID(callback.transfer_id)
    transfer = await Transfer.get(transfer_id)
    
    # Idempotency: check if already processed
    existing_audit = await AuditLog.find_one({
        "correlation_id": transfer.correlation_id,
        "step": f"ledger_{callback.operation_type}_callback",
        "details.ledger_txn_id": callback.ledger_txn_id
    })
    if existing_audit:
        return {"status": "already_processed"}  # Idempotent
    
    if callback.operation_type == 'debit':
        if callback.status == 'SUCCESS':
            transfer.ledger_debit_txn_id = callback.ledger_txn_id
            await transfer.transition_to(TransferState.DEBIT_POSTED)
        else:
            await transfer.transition_to(TransferState.FAILED, 
                                        reason=f"Debit failed: {callback.reason}")
    
    elif callback.operation_type == 'credit':
        if callback.status == 'SUCCESS':
            transfer.ledger_credit_txn_id = callback.ledger_txn_id
            await transfer.transition_to(TransferState.SUCCESS)
        else:
            # Credit failed, initiate reverse debit
            reverse = await initiate_reverse_debit(transfer)
            await transfer.transition_to(TransferState.FAILED, 
                                        reason=f"Credit failed: {callback.reason}",
                                        reverse_txn_id=reverse.id)
    
    return {"status": "processed"}
```

### Phase 6: Reconciliation & Timeout Handler

**Files:**
- `src/jobs/reconciliation_job.py`

**Logic:**
- Runs every 5 minutes (configurable)
- Scans for transfers in PENDING_* states older than timeout threshold (e.g., 30 min)
- For each orphaned transfer:
  - Query ledger to check if debit/credit was actually posted
  - If posted, sync state in DB
  - If not posted, mark as FAILED
  - If unknown, alert operations team
- Emit metrics (orphaned count, resolved count)

**Example:**
```python
async def reconciliation_job():
    timeout_threshold = now() - timedelta(minutes=30)
    orphaned = await Transfer.find({
        "state": {"$in": [TransferState.PENDING_DEBIT, TransferState.PENDING_CREDIT]},
        "updated_at": {"$lt": timeout_threshold}
    })
    
    for transfer in orphaned:
        try:
            ledger_status = await ledger_service.query_status(transfer.ledger_debit_txn_id)
            if ledger_status == 'POSTED':
                await transfer.transition_to(TransferState.DEBIT_POSTED, 
                                            reason="Reconciliation catch-up")
            elif ledger_status == 'FAILED':
                await transfer.transition_to(TransferState.FAILED, 
                                            reason="Reconciliation: ledger rejected")
            else:
                alert_ops(f"Unreconciled transfer {transfer.id}")
        except Exception as e:
            log_error(f"Reconciliation failed for {transfer.id}: {e}")
```

### Phase 7: Structured Audit Logging

**Files:**
- `src/audit_log.py` — AuditLog model and logger
- `logs/audit_schema.json` — Schema definition

**Schema:**
```json
{
  "correlation_id": "TXN-2025-001-ABC123",
  "timestamp": "2025-11-26T10:15:30.123456Z",
  "step": "transfer_initiated | state_transition | ledger_debit_request | ledger_debit_callback | ...",
  "actor": "api | transfer_worker | reconciliation_job | ledger_service",
  "details": {
    "transfer_id": "550e8400-e29b-41d4-a716-446655440000",
    "ledger_txn_id": "LEDGER-123",
    "amount": "100.00",
    "currency": "USD",
    "state_from": "INITIATED",
    "state_to": "PENDING_DEBIT",
    "reason": "Normal flow",
    "error": null,
    "retry_count": 0,
    "duration_ms": 45
  },
  "result": "success | failure | timeout"
}
```

**Implementation:**
```python
async def log_audit(correlation_id: str, step: str, actor: str, 
                   details: dict, result: str = 'success', error: str = None):
    entry = AuditLog(
        correlation_id=correlation_id,
        timestamp=now_utc(),
        step=step,
        actor=actor,
        details=details,
        result=result,
        error=error
    )
    await entry.save()
    
    # Optionally: emit to central logging (e.g., ELK, Splunk)
    if CONFIG.log_to_central:
        await central_logger.log(entry.dict())
```

---

## 4. Prioritized Implementation Tasks

| Priority | Task | Owner | Est. Time | Dependencies |
|---|---|---|---|---|
| **P0** | Define Transfer state machine & ORM model | Backend | 4h | None |
| **P0** | Implement mock ledger service with configurable failures | QA | 4h | None |
| **P0** | Create transfer controller (POST /transfers, GET /transfers/{id}) | Backend | 4h | P0 task 1 |
| **P0** | Implement async transfer worker (debit → credit flow) | Backend | 8h | P0 tasks 1,2,3 |
| **P0** | Create idempotent ledger callback handler | Backend | 4h | P0 task 4 |
| **P0** | Implement compensating transaction (reverse debit) | Backend | 4h | P0 task 5 |
| **P1** | Add reconciliation job (timeout & orphan detection) | Backend | 4h | P0 tasks 1-6 |
| **P1** | Create audit logging infrastructure & schema | Backend | 3h | P0 task 1 |
| **P2** | Integration tests (5 scenarios) | QA | 12h | P0 tasks 1-8 |
| **P2** | Add monitoring/alerting for failed transfers | DevOps | 4h | P0 tasks 1-8 |

**Critical Path:** P0 tasks 1,2,3,4,5,6 (estimated 28 hours of focused backend work)

---

## 5. Testing Strategy

### Unit Tests
- State transition validation (can/cannot transition tests)
- Idempotency key deduplication
- Audit log formatting

### Integration Tests (5 scenarios)
1. **Scenario 1: Normal Success Flow**
   - User initiates transfer → API returns 202 → Worker debit → Callback debit success → Worker credit → Callback credit success → Transfer shows SUCCESS
   
2. **Scenario 2: Posting Failure (Insufficient Funds)**
   - User initiates transfer → Worker calls debit → Ledger rejects (insufficient funds) → Callback failure → Transfer shows FAILED
   
3. **Scenario 3: Network Retry**
   - User initiates transfer → Worker calls debit → Network timeout → Worker retries with backoff → Debit succeeds → Full flow completes
   
4. **Scenario 4: Timeout Rollback (Credit Fails)**
   - User initiates transfer → Debit succeeds → Credit called → Credit timeout/failure → Reverse debit initiated → Transfer shows FAILED with reverse_txn_id
   
5. **Scenario 5: Audit Reconciliation**
   - User initiates transfer → Callback lost (no_callback mode) → Reconciliation job runs → Detects orphaned transfer → Queries ledger → Syncs state → Transfer reconciled

### Test Execution
- Run via single command: `./run_tests.sh`
- Output: pass/fail for each scenario, metrics (total time, retry count, ledger calls)
- Report format: JSON and human-readable summary

---

## 6. Deployment & Rollout

### Pre-Deployment
- Run full integration test suite (all 5 scenarios pass)
- Load test with 1000 concurrent transfers
- Verify audit logs are being written correctly
- Backup existing transfer table

### Deployment
- Deploy backend changes (API, worker, callback handler, reconciliation job)
- Enable feature flag for new flow (keep old code path for 48 hours)
- Monitor error rates, callback success rate, reconciliation metrics

### Post-Deployment
- Verify no increase in failed transfers
- Check reconciliation job identifies and fixes orphaned transfers
- Gather customer feedback (verify no false successes reported)
- After 48h, disable old code path

---

## 7. Success Criteria

✅ **No false successes:** Every transfer reported as "SUCCESS" has matching debit + credit in ledger  
✅ **Resilient to failures:** Network timeouts, ledger rejections, and callback losses are handled gracefully  
✅ **Auditable:** Every transfer state change is logged with correlation ID, timestamps, and amounts (redacted)  
✅ **Reconcilable:** Operations team can trace any transfer from frontend request → backend state → ledger posting  
✅ **Testable:** All 5 integration scenarios pass repeatably  
✅ **Observable:** Metrics show callback success rate, retry count, reconciliation rate

---

## 8. Files to Deliver

- `src/models/transfer.py` — ORM model with state machine
- `src/state_machine.py` — State machine logic
- `src/controllers/transfer_controller.py` — HTTP endpoints
- `src/services/transfer_service.py` — Business logic
- `src/workers/transfer_worker.py` — Async worker
- `src/handlers/ledger_callback_handler.py` — Callback processing
- `src/jobs/reconciliation_job.py` — Reconciliation & timeout handler
- `src/audit_log.py` — Audit logging
- `mocks/mock_ledger_service.py` — Mock ledger for testing
- `tests/integration/transfer_cases.yaml` — Test scenario definitions
- `tests/run_suite.py` — Test runner
- `logs/audit_schema.json` — Audit logging schema
- `scripts/run_transfer_suite.sh` — Shell script to run tests
- `requirements.txt` — Dependencies
- `setup.sh` — Environment setup
- `run_tests.sh` — Wrapper for test execution
- `docs/root_cause_analysis.md` — Root cause analysis (this doc)
- `docs/remediation_plan.md` — This file

---

## 9. References

- State Machine Pattern: https://en.wikipedia.org/wiki/State_machine
- Idempotency: https://tools.ietf.org/html/draft-idempotency-header-def-00
- Compensating Transactions (Saga Pattern): https://microservices.io/patterns/data/saga.html
- Async Callbacks & Webhooks: https://zapier.com/engineering/async-webhooks/
