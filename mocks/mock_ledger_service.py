from __future__ import annotations

import itertools
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.errors import LedgerPostError
from src.models import LedgerJob, LedgerPollResult, LedgerPostResponse, LedgerStatus


class MockLedgerService:
    """
    Simulated ledger service for integration testing.

    Scenario configuration format:
    {
      "debit": {
         "post_results": ["PENDING", {"error": "network"}, "PENDING"],
         "poll_results": ["PENDING", "COMPLETED"]
      },
      "credit": {
         "post_results": ["PENDING"],
         "poll_results": ["PENDING", "COMPLETED"]
      },
      "rollback": {
         "post_results": ["PENDING"],
         "poll_results": ["PENDING", "COMPLETED"]
      }
    }
    """

    def __init__(self, scenario_config: Dict[str, Any]):
        self.cfg = scenario_config
        self._job_store: Dict[str, LedgerJob] = {}
        self._job_counter = itertools.count(1)
        self._post_counters = {"debit": 0, "credit": 0, "rollback": 0}
        self._poll_counters: Dict[str, int] = {}

    def post_debit(self, request) -> LedgerPostResponse:
        return self._handle_post("debit")

    def post_credit(self, request) -> LedgerPostResponse:
        return self._handle_post("credit")

    def rollback_debit(self, debit_job_id: str) -> LedgerPostResponse:
        return self._handle_post("rollback")

    def poll_status(self, job_id: str) -> LedgerPollResult:
        job = self._job_store[job_id]
        job_type = self._infer_job_type(job_id)
        poll_seq: List[Any] = self.cfg.get(job_type, {}).get("poll_results", [job.status.value])
        idx = self._poll_counters.get(job_id, 0)
        self._poll_counters[job_id] = idx + 1
        outcome = poll_seq[min(idx, len(poll_seq) - 1)]
        job.status = self._to_status(outcome)
        job.last_update = datetime.utcnow()
        return LedgerPollResult(job)

    # internal helpers
    def _handle_post(self, job_type: str) -> LedgerPostResponse:
        seq: List[Any] = self.cfg.get(job_type, {}).get("post_results", ["PENDING"])
        attempt = self._post_counters[job_type]
        self._post_counters[job_type] += 1
        outcome = seq[min(attempt, len(seq) - 1)]

        if isinstance(outcome, dict) and "error" in outcome:
            raise LedgerPostError(outcome.get("error") or f"{job_type} post error")

        status = self._to_status(outcome)
        job_id = f"{job_type}-{next(self._job_counter)}"
        job = LedgerJob(job_id=job_id, status=status)
        self._job_store[job_id] = job
        corr_id = f"corr-{job_id}-{attempt+1}"
        return LedgerPostResponse(job=job, correlation_id=corr_id)

    @staticmethod
    def _to_status(val: Any) -> LedgerStatus:
        if isinstance(val, LedgerStatus):
            return val
        if isinstance(val, str):
            return LedgerStatus[val.upper()]
        raise ValueError(f"Unknown status value: {val}")

    @staticmethod
    def _infer_job_type(job_id: str) -> str:
        return job_id.split("-")[0]
