"""Module dependency cycle B."""

from src import graph_a


def describe() -> str:
    """Call back into graph_a."""

    return graph_a.get_name()
