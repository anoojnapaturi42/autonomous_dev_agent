"""Dependency and call graphs built from AST analysis."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .symbol_index import PythonFileIndex, PythonSymbol


def module_name_from_path(path: str | Path) -> str:
    """Convert a repository-relative path to a dotted module name."""

    relative_path = Path(path)
    parts = list(relative_path.parts)
    if not parts:
        return ""

    filename = parts[-1]
    if filename == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = Path(filename).stem

    return ".".join(part for part in parts if part)


@dataclass(slots=True)
class ModuleDependencyGraph:
    """Internal module dependency graph."""

    nodes: tuple[str, ...]
    adjacency: dict[str, tuple[str, ...]]

    def dependencies_of(self, module: str) -> tuple[str, ...]:
        return self.adjacency.get(module, ())

    def dependents_of(self, module: str) -> tuple[str, ...]:
        dependents = [node for node, targets in self.adjacency.items() if module in targets]
        return tuple(sorted(dependents))

    def cycles(self) -> tuple[tuple[str, ...], ...]:
        components = _strongly_connected_components(self.adjacency)
        cyclic_components: list[tuple[str, ...]] = []
        for component in components:
            if len(component) > 1:
                cyclic_components.append(tuple(sorted(component)))
                continue
            node = component[0]
            if node in self.adjacency.get(node, ()):
                cyclic_components.append((node,))
        return tuple(sorted(cyclic_components))

    def to_dict(self) -> dict[str, object]:
        return {
            "nodes": list(self.nodes),
            "edges": [
                {"from": source, "to": target}
                for source in self.nodes
                for target in self.adjacency.get(source, ())
            ],
            "cycles": [list(cycle) for cycle in self.cycles()],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


@dataclass(slots=True)
class CallGraph:
    """Approximate call graph inferred from AST call sites."""

    nodes: tuple[str, ...]
    adjacency: dict[str, tuple[str, ...]]

    def callees_of(self, symbol: str) -> tuple[str, ...]:
        return self.adjacency.get(symbol, ())

    def callers_of(self, symbol: str) -> tuple[str, ...]:
        callers = [caller for caller, callees in self.adjacency.items() if symbol in callees]
        return tuple(sorted(callers))

    def to_dict(self) -> dict[str, object]:
        return {
            "nodes": list(self.nodes),
            "edges": [
                {"from": source, "to": target}
                for source in self.nodes
                for target in self.adjacency.get(source, ())
            ],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def build_module_dependency_graph(files: Iterable[PythonFileIndex]) -> ModuleDependencyGraph:
    file_list = list(files)
    module_names = [module_name_from_path(file.path) for file in file_list]
    module_map = {module_name: file.path for module_name, file in zip(module_names, file_list)}

    adjacency: dict[str, tuple[str, ...]] = {}
    for file, module_name in zip(file_list, module_names):
        dependencies: list[str] = []
        seen: set[str] = set()
        for imported in file.imports:
            for target in imported.targets:
                normalized = target.lstrip(".")
                if not normalized:
                    continue
                if normalized in module_map and normalized not in seen:
                    dependencies.append(normalized)
                    seen.add(normalized)
        adjacency[module_name] = tuple(dependencies)

    return ModuleDependencyGraph(nodes=tuple(module_names), adjacency=adjacency)


def build_call_graph(files: Iterable[PythonFileIndex]) -> CallGraph:
    file_list = list(files)
    adjacency: dict[str, tuple[str, ...]] = {}
    nodes: set[str] = set()
    for file in file_list:
        for symbol in file.symbols:
            if symbol.kind not in {"function", "method"}:
                continue
            caller = symbol.qualified_name
            nodes.add(caller)
            nodes.update(symbol.calls)
            adjacency[caller] = symbol.calls

    return CallGraph(nodes=tuple(sorted(nodes)), adjacency=adjacency)


def _strongly_connected_components(adjacency: dict[str, tuple[str, ...]]) -> list[tuple[str, ...]]:
    index = 0
    stack: list[str] = []
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in adjacency.get(node, ()):  # type: ignore[arg-type]
            if neighbor not in indices:
                visit(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

        if lowlinks[node] == indices[node]:
            component: list[str] = []
            while True:
                candidate = stack.pop()
                on_stack.remove(candidate)
                component.append(candidate)
                if candidate == node:
                    break
            components.append(tuple(component))

    nodes = set(adjacency)
    for targets in adjacency.values():
        nodes.update(targets)
    for node in sorted(nodes):
        if node not in indices:
            visit(node)

    return components
