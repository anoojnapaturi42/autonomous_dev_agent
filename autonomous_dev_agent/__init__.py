"""Compatibility shim that forwards imports to the implementation under `src/`."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC_PACKAGE = _ROOT / "src" / "autonomous_dev_agent"

if str(_SRC_PACKAGE) not in __path__:
    __path__.append(str(_SRC_PACKAGE))

from .config import Settings, load_settings
from .logging_config import configure_logging
from .repository import LocalRepository, Repository

__all__ = [
    "LocalRepository",
    "Repository",
    "Settings",
    "configure_logging",
    "load_settings",
]

__version__ = "0.1.0"

