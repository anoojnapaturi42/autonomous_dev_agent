# leading comment
from __future__ import annotations

def helper() -> str:
    return "helper"

@logged
def target(value: str) -> str:
    """Return a transformed value."""
    return value.strip()

# trailing comment
