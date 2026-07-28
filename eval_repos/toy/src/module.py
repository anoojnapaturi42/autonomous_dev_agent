import os
from collections import defaultdict


class SampleWorker:
    def run(self) -> str:
        return os.path.basename("hello.txt")


def build_index() -> defaultdict[str, int]:
    index = defaultdict(int)
    index["hello"] += 1
    return index
