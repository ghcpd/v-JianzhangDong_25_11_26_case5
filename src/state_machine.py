from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

from .models import TransferEvent, TransferState


# Allowed transitions for Fixed_Transfer_Flow_v2
_ALLOWED_TRANSITIONS: Dict[TransferState, Tuple[TransferState, ...]] = {
    TransferState.INIT: (TransferState.DEBIT_PENDING, TransferState.FAILED),
    TransferState.DEBIT_PENDING: (
        TransferState.DEBIT_CONFIRMED,
        TransferState.FAILED,
    ),
    TransferState.DEBIT_CONFIRMED: (
        TransferState.CREDIT_PENDING,
        TransferState.FAILED,
        TransferState.ROLLED_BACK,
    ),
    TransferState.CREDIT_PENDING: (
        TransferState.COMPLETED,
        TransferState.FAILED,
        TransferState.ROLLED_BACK,
    ),
    TransferState.COMPLETED: tuple(),
    TransferState.FAILED: tuple(),
    TransferState.ROLLED_BACK: tuple(),
}


class InvalidTransition(Exception):
    pass


class TransferStateMachine:
    def __init__(self) -> None:
        self.state: TransferState = TransferState.INIT
        self.history: List[TransferEvent] = []

    def transition(self, event: str, next_state: TransferState, details=None) -> TransferEvent:
        details = details or {}
        if next_state not in _ALLOWED_TRANSITIONS.get(self.state, ()):  # type: ignore[arg-type]
            raise InvalidTransition(f"Cannot transition from {self.state} to {next_state} on event {event}")
        self.state = next_state
        ev = TransferEvent(timestamp=datetime.utcnow(), state=next_state, event=event, details=details)
        self.history.append(ev)
        return ev

    def get_history(self) -> List[TransferEvent]:
        return list(self.history)
