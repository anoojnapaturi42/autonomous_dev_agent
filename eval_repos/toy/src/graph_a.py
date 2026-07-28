"""Module dependency cycle A."""

from src import graph_b


def get_name() -> str:
    """Call into graph_b."""

    return graph_b.describe()
