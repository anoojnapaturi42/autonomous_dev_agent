"""Structured symbol indexing for parsed Python files."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graphs import CallGraph, ModuleDependencyGraph
    from .semantic import SemanticIndex


@dataclass(frozen=True, slots=True)
class PythonImport:
    """A single import statement captured from the AST."""

    statement: str
    module: str | None
    names: tuple[str, ...]
    line: int
    end_line: int
    targets: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PythonSymbol:
    """A searchable symbol discovered in source code."""

    name: str
    qualified_name: str
    kind: str
    path: Path
    line: int
    end_line: int
    source_start_line: int | None = None
    decorators: tuple[str, ...] = ()
    docstring: str | None = None
    bases: tuple[str, ...] = ()
    calls: tuple[str, ...] = ()


class SymbolIndex:
    """Searchable symbol index built from parsed Python files."""

    def __init__(
        self,
        symbols: tuple[PythonSymbol, ...] = (),
        *,
        repository_root: str | Path | None = None,
    ) -> None:
        self.symbols = symbols
        self._by_name: dict[str, list[PythonSymbol]] = defaultdict(list)
        self._by_path: dict[Path, list[PythonSymbol]] = defaultdict(list)
        self._repository_root = Path(repository_root).resolve() if repository_root is not None else None
        for symbol in symbols:
            self._by_name[symbol.name].append(symbol)
            self._by_path[self._normalize_path(symbol.path)].append(symbol)

    def find_by_name(self, name: str) -> tuple[PythonSymbol, ...]:
        return tuple(self._by_name.get(name, ()))

    def find_by_location(self, path: str | Path, line: int) -> tuple[PythonSymbol, ...]:
        normalized_path = self._normalize_path(path)
        matches = [
            symbol
            for symbol in self._by_path.get(normalized_path, ())
            if (symbol.source_start_line or symbol.line) <= line <= symbol.end_line
        ]
        return tuple(sorted(matches, key=lambda symbol: (symbol.line, symbol.end_line, symbol.kind, symbol.name)))

    def find_in_file(self, path: str | Path) -> tuple[PythonSymbol, ...]:
        return tuple(self._by_path.get(self._normalize_path(path), ()))

    def _normalize_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if self._repository_root is not None and candidate.is_absolute():
            try:
                relative = candidate.resolve().relative_to(self._repository_root)
            except ValueError:
                pass
            else:
                return relative
        if candidate.is_absolute() and self._repository_root is None:
            try:
                candidate = candidate.name if len(candidate.parts) == 1 else Path(*candidate.parts[-2:])
            except Exception:
                return candidate
        return Path(candidate)


@dataclass(frozen=True, slots=True)
class PythonFileIndex:
    """Structured metadata for one Python file."""

    path: Path
    size: int
    modified_at: datetime
    module_docstring: str | None
    imports: tuple[PythonImport, ...]
    symbols: tuple[PythonSymbol, ...]
    parse_error: str | None = None

    @property
    def classes(self) -> tuple[str, ...]:
        return tuple(symbol.name for symbol in self.symbols if symbol.kind == "class")

    @property
    def functions(self) -> tuple[str, ...]:
        return tuple(symbol.name for symbol in self.symbols if symbol.kind == "function")

    @property
    def methods(self) -> tuple[str, ...]:
        return tuple(symbol.name for symbol in self.symbols if symbol.kind == "method")

    @property
    def variables(self) -> tuple[str, ...]:
        return tuple(symbol.name for symbol in self.symbols if symbol.kind == "variable")


@dataclass(frozen=True, slots=True)
class RepositoryIndex:
    """Structured scan results for an indexed repository."""

    root: Path
    python_files: tuple[PythonFileIndex, ...]
    symbol_index: SymbolIndex
    module_graph: ModuleDependencyGraph
    call_graph: CallGraph
    semantic_index: SemanticIndex
    scanned_at: datetime
