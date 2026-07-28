from pathlib import Path


def guide_root() -> Path:
    """Return the root path for the guide."""

    return Path(__file__).parent
