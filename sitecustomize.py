"""Allow local `python -m autonomous_dev_agent` execution from the repo root."""

from __future__ import annotations

import sys
from pathlib import Path


def _add_src_to_path() -> None:
    root = Path(__file__).resolve().parent
    src = root / "src"
    if src.is_dir():
        src_path = str(src)
        if src_path not in sys.path:
            sys.path.insert(0, src_path)


_add_src_to_path()

