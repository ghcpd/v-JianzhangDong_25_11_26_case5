from __future__ import annotations

import abc
from typing import Protocol

from .models import LedgerPollResult, LedgerPostResponse


class LedgerService(Protocol):
    def post_debit(self, request):
        ...

    def post_credit(self, request):
        ...

    def rollback_debit(self, debit_job_id: str):
        ...

    def poll_status(self, job_id: str):
        ...


class AbstractLedgerService(abc.ABC):
    @abc.abstractmethod
    def post_debit(self, request) -> LedgerPostResponse:
        ...

    @abc.abstractmethod
    def post_credit(self, request) -> LedgerPostResponse:
        ...

    @abc.abstractmethod
    def rollback_debit(self, debit_job_id: str) -> LedgerPostResponse:
        ...

    @abc.abstractmethod
    def poll_status(self, job_id: str) -> LedgerPollResult:
        ...
