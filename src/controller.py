from __future__ import annotations

import time
from typing import Tuple

from . import audit
from .config import DEFAULT_CONFIG, TransferConfig
from .errors import LedgerPostError, LedgerStatusError, RollbackError, TransferError
from .ledger_adapter import LedgerService
from .models import (
    LedgerJob,
    LedgerStatus,
    TransferOutcome,
    TransferRequest,
    TransferResult,
    TransferState,
)
from .state_machine import InvalidTransition, TransferStateMachine


class FixedTransferFlowV2:
    def __init__(self, ledger: LedgerService, config: TransferConfig = DEFAULT_CONFIG):
        self.ledger = ledger
        self.config = config

    def process_transfer(self, request: TransferRequest) -> TransferResult:
        txn_id = request.ensure_txn_id()
        sm = TransferStateMachine()
        audit_trail = []

        def record(event: str, next_state: TransferState, extra=None):
            ev = sm.transition(event, next_state, extra or {})
            audit_trail.append(ev)
            ctx = audit.build_context(
                txn_id=txn_id,
                source_account=request.source_account,
                destination_account=request.destination_account,
                amount=request.amount,
                currency=request.currency,
                state=next_state.value,
                extra=extra,
            )
            audit.log_event(event, **ctx)

        # Step 1: Post debit with retries
        debit_job: LedgerJob = None  # type: ignore
        debit_corr_id: str = ""
        try:
            debit_job, debit_corr_id = self._post_with_retry(
                request, post_fn=self.ledger.post_debit, action_name="DEBIT",
                max_attempts=self.config.max_post_attempts, txn_id=txn_id
            )
            record("DEBIT_POSTED", TransferState.DEBIT_PENDING, {"correlation_id": debit_corr_id, "job_id": debit_job.job_id})
        except Exception as e:
            record("DEBIT_POST_FAILED", TransferState.FAILED, {"error": str(e)})
            return TransferResult(
                txn_id=txn_id,
                state=TransferState.FAILED,
                outcome=TransferOutcome.FAILURE,
                message=f"Debit posting failed: {e}",
                errors=[str(e)],
                audit_trail=audit_trail,
            )

        # Step 2: Poll debit until completion
        try:
            debit_job = self._poll_until_final(debit_job.job_id, txn_id, phase="DEBIT")
        except Exception as e:
            record("DEBIT_CONFIRM_FAILED", TransferState.FAILED, {"error": str(e), "job_id": debit_job.job_id})
            return TransferResult(
                txn_id=txn_id,
                state=TransferState.FAILED,
                outcome=TransferOutcome.FAILURE,
                message=f"Debit confirmation failed: {e}",
                debit_job=debit_job,
                errors=[str(e)],
                audit_trail=audit_trail,
            )

        record("DEBIT_CONFIRMED", TransferState.DEBIT_CONFIRMED, {"job_id": debit_job.job_id})

        # Step 3: Post credit with retries
        credit_job: LedgerJob = None  # type: ignore
        credit_corr_id: str = ""
        try:
            credit_job, credit_corr_id = self._post_with_retry(
                request, post_fn=self.ledger.post_credit, action_name="CREDIT",
                max_attempts=self.config.max_post_attempts, txn_id=txn_id
            )
            record("CREDIT_POSTED", TransferState.CREDIT_PENDING, {"correlation_id": credit_corr_id, "job_id": credit_job.job_id})
        except Exception as e:
            # attempt rollback because debit already confirmed
            rollback_successful = False
            rollback_error = None
            if self.config.rollback_on_credit_failure:
                try:
                    self._rollback_debit(debit_job.job_id, txn_id)
                    rollback_successful = True
                except Exception as rb_ex:
                    rollback_error = rb_ex
            record(
                "CREDIT_POST_FAILED",
                TransferState.FAILED if not rollback_successful else TransferState.ROLLED_BACK,
                {"error": str(e), "rollback_successful": rollback_successful, "rollback_error": str(rollback_error) if rollback_error else None},
            )
            return TransferResult(
                txn_id=txn_id,
                state=TransferState.ROLLED_BACK if rollback_successful else TransferState.FAILED,
                outcome=TransferOutcome.FAILURE,
                message=f"Credit posting failed: {e}",
                debit_job=debit_job,
                errors=[str(e)] + ([f"Rollback error: {rollback_error}"] if rollback_error else []),
                audit_trail=audit_trail,
            )

        # Step 4: Poll credit until completion
        try:
            credit_job = self._poll_until_final(credit_job.job_id, txn_id, phase="CREDIT")
        except Exception as e:
            # rollback on credit confirmation failure
            rollback_successful = False
            rollback_error = None
            if self.config.rollback_on_credit_failure:
                try:
                    self._rollback_debit(debit_job.job_id, txn_id)
                    rollback_successful = True
                except Exception as rb_ex:
                    rollback_error = rb_ex
            record(
                "CREDIT_CONFIRM_FAILED",
                TransferState.FAILED if not rollback_successful else TransferState.ROLLED_BACK,
                {
                    "error": str(e),
                    "job_id": credit_job.job_id if credit_job else None,
                    "rollback_successful": rollback_successful,
                    "rollback_error": str(rollback_error) if rollback_error else None,
                },
            )
            return TransferResult(
                txn_id=txn_id,
                state=TransferState.ROLLED_BACK if rollback_successful else TransferState.FAILED,
                outcome=TransferOutcome.FAILURE,
                message=f"Credit confirmation failed: {e}",
                debit_job=debit_job,
                credit_job=credit_job,
                errors=[str(e)] + ([f"Rollback error: {rollback_error}"] if rollback_error else []),
                audit_trail=audit_trail,
            )

        record("CREDIT_CONFIRMED", TransferState.COMPLETED, {"job_id": credit_job.job_id})
        return TransferResult(
            txn_id=txn_id,
            state=TransferState.COMPLETED,
            outcome=TransferOutcome.SUCCESS,
            message="Transfer completed",
            debit_job=debit_job,
            credit_job=credit_job,
            audit_trail=audit_trail,
        )

    def _post_with_retry(self, request: TransferRequest, post_fn, action_name: str, max_attempts: int, txn_id: str) -> Tuple[LedgerJob, str]:
        last_err = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = post_fn(request)
                # resp: LedgerPostResponse
                audit.log_event(
                    f"{action_name}_POST_ATTEMPT",
                    txn_id=txn_id,
                    attempt=attempt,
                    correlation_id=resp.correlation_id,
                    job_id=resp.job.job_id,
                    status=resp.job.status.value,
                )
                if resp.job.status == LedgerStatus.FAILED:
                    raise LedgerPostError(f"{action_name} post failed immediately")
                return resp.job, resp.correlation_id
            except Exception as exc:
                last_err = exc
                audit.log_event(
                    f"{action_name}_POST_RETRY",
                    txn_id=txn_id,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt == max_attempts:
                    raise exc
                time.sleep(self.config.status_poll_interval_seconds)
        raise last_err if last_err else LedgerPostError(f"{action_name} post failed")

    def _poll_until_final(self, job_id: str, txn_id: str, phase: str) -> LedgerJob:
        for attempt in range(1, self.config.max_status_attempts + 1):
            resp = self.ledger.poll_status(job_id)
            audit.log_event(
                f"{phase}_STATUS",
                txn_id=txn_id,
                attempt=attempt,
                job_id=job_id,
                status=resp.job.status.value,
            )
            if resp.job.status == LedgerStatus.COMPLETED:
                return resp.job
            if resp.job.status == LedgerStatus.FAILED:
                raise LedgerStatusError(f"{phase} job {job_id} failed")
            if resp.job.status == LedgerStatus.TIMEOUT:
                raise LedgerStatusError(f"{phase} job {job_id} timed out")
            time.sleep(self.config.status_poll_interval_seconds)
        raise LedgerStatusError(f"{phase} job {job_id} did not complete after {self.config.max_status_attempts} attempts")

    def _rollback_debit(self, debit_job_id: str, txn_id: str):
        resp = self.ledger.rollback_debit(debit_job_id)
        audit.log_event(
            "ROLLBACK_POSTED", txn_id=txn_id, job_id=resp.job.job_id, status=resp.job.status.value, correlation_id=resp.correlation_id
        )
        # poll rollback status
        rb_job = self._poll_until_final(resp.job.job_id, txn_id, phase="ROLLBACK")
        audit.log_event("ROLLBACK_CONFIRMED", txn_id=txn_id, job_id=rb_job.job_id)
        return rb_job
