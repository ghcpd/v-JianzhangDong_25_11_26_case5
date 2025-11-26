class TransferError(Exception):
    """Base transfer error."""


class LedgerPostError(TransferError):
    pass


class LedgerStatusError(TransferError):
    pass


class RollbackError(TransferError):
    pass
