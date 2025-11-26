from dataclasses import dataclass


@dataclass
class TransferConfig:
    max_post_attempts: int = 3
    max_status_attempts: int = 5
    status_poll_interval_seconds: float = 0.1
    rollback_on_credit_failure: bool = True
    ledger_timeout_seconds: float = 5.0
    audit_mask_account: bool = True


DEFAULT_CONFIG = TransferConfig()
