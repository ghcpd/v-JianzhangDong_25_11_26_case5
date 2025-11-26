from enum import Enum
import dataclasses
import time


class TransferState(Enum):
    INITIATED = "initiated"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLEDBACK = "rolled_back"


@dataclasses.dataclass
class TransferRecord:
    tx_id: str
    from_account: str
    to_account: str
    amount: float
    state: TransferState = TransferState.INITIATED
    created_at: float = dataclasses.field(default_factory=time.time)
    updated_at: float = dataclasses.field(default_factory=time.time)
    attempts: int = 0

    def to_dict(self):
        return {
            "tx_id": self.tx_id,
            "from_account": self.from_account,
            "to_account": self.to_account,
            "amount": self.amount,
            "state": self.state.value,
            "attempts": self.attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
