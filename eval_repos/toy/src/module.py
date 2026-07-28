"""Toy module for AST parsing tests."""

import os
from collections import defaultdict


MODULE_LEVEL = 1


def traced(func):
    """Return the wrapped function unchanged."""

    return func


class BaseWorker:
    """Base worker implementation."""

    base_kind = "base"


@traced
class SampleWorker(BaseWorker):
    """Sample worker implementation."""

    base_role = "worker"

    @traced
    def run(self) -> str:
        """Return the basename of a known file."""

        result = os.path.basename("hello.txt")
        return result


@traced
def build_index() -> defaultdict[str, int]:
    """Build a tiny in-memory index."""

    index = defaultdict(int)
    index["hello"] += 1
    return index
