import re
from typing import Optional


def mask_account(account: Optional[str]) -> Optional[str]:
    if not account:
        return account
    # Keep first 2 and last 2 characters, mask the rest
    return re.sub(r"(?<=..).(?=..)", "*", account)
