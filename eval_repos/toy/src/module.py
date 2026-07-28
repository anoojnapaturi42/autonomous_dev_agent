"""Toy module for AST parsing tests."""

import os
from collections import defaultdict


MODULE_LEVEL = 1


def traced(func):
    """Return the wrapped function unchanged."""

    return func


def format_result(value: str) -> str:
    """Format a result string."""

    return value.upper()


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

        result = format_result(os.path.basename("hello.txt"))
        return result


@traced
def build_index() -> defaultdict[str, int]:
    """Build a tiny in-memory index."""

    index = defaultdict(int)
    label = format_result("hello")
    index[label] += 1
    return index
