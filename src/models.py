"""
Domain models and enums for Fixed_Transfer_Flow_v2.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TransferState(str, Enum):
    INIT = "INIT"
    DEBIT_PENDING = "DEBIT_PENDING"
    DEBIT_CONFIRMED = "DEBIT_CONFIRMED"
    CREDIT_PENDING = "CREDIT_PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class TransferOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class LedgerStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


@dataclass
class LedgerJob:
    job_id: str
    status: LedgerStatus
    last_update: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LedgerPostResponse:
    job: LedgerJob
    correlation_id: str


@dataclass
class LedgerPollResult:
    job: LedgerJob


@dataclass
class TransferRequest:
    source_account: str
    destination_account: str
    amount: float
    currency: str = "USD"
    metadata: Dict[str, Any] = field(default_factory=dict)
    txn_id: Optional[str] = None

    def ensure_txn_id(self) -> str:
        if not self.txn_id:
            self.txn_id = str(uuid.uuid4())
        return self.txn_id


@dataclass
class TransferEvent:
    timestamp: datetime
    state: TransferState
    event: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransferResult:
    txn_id: str
    state: TransferState
    outcome: TransferOutcome
    message: str
    debit_job: Optional[LedgerJob] = None
    credit_job: Optional[LedgerJob] = None
    errors: List[str] = field(default_factory=list)
    audit_trail: List[TransferEvent] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.outcome == TransferOutcome.SUCCESS
