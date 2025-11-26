from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import structlog

from .utils import mask_account


# Configure structlog for JSON output
logging.basicConfig(level=logging.INFO)
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


AUDIT_LOGGER_NAME = "transfer_audit"


def get_logger():
    return structlog.get_logger(AUDIT_LOGGER_NAME)


def build_context(
    txn_id: str,
    correlation_id: Optional[str] = None,
    source_account: Optional[str] = None,
    destination_account: Optional[str] = None,
    amount: Optional[float] = None,
    currency: Optional[str] = None,
    state: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ctx = {
        "txn_id": txn_id,
    }
    if correlation_id:
        ctx["correlation_id"] = correlation_id
    if source_account:
        ctx["source_account"] = mask_account(source_account)
    if destination_account:
        ctx["destination_account"] = mask_account(destination_account)
    if amount is not None:
        ctx["amount"] = amount
    if currency:
        ctx["currency"] = currency
    if state:
        ctx["state"] = state
    if extra:
        ctx.update(extra)
    return ctx


def log_event(message: str, **ctx):
    logger = get_logger()
    logger.info(message, **ctx)
