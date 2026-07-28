"""Recursive repository scanning and Python indexing."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .repository import Repository


@dataclass(frozen=True, slots=True)
class PythonFileIndex:
    """Structured metadata for one Python file."""

    path: Path
    size: int
    modified_at: datetime
    imports: tuple[str, ...]
    classes: tuple[str, ...]
    functions: tuple[str, ...]
    parse_error: str | None = None


@dataclass(frozen=True, slots=True)
class RepositoryIndex:
    """Structured scan results for an indexed repository."""

    root: Path
    python_files: tuple[PythonFileIndex, ...]
    scanned_at: datetime


class RepositoryScanner:
    """Build a structured index for every Python file in a repository."""

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def scan(self) -> RepositoryIndex:
        indexed_files = tuple(self._scan_python_file(path) for path in self._repository.list_python_files())
        return RepositoryIndex(
            root=self._repository.root,
            python_files=indexed_files,
            scanned_at=datetime.now(timezone.utc),
        )

    def _scan_python_file(self, relative_path: Path) -> PythonFileIndex:
        absolute_path = self._repository.root / relative_path
        contents = self._repository.read_file(relative_path)
        stat_result = absolute_path.stat()

        imports, classes, functions, parse_error = self._extract_python_symbols(contents)

        return PythonFileIndex(
            path=relative_path,
            size=stat_result.st_size,
            modified_at=datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc),
            imports=imports,
            classes=classes,
            functions=functions,
            parse_error=parse_error,
        )

    def _extract_python_symbols(
        self, source: str
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None]:
        try:
            module = ast.parse(source)
        except SyntaxError as exc:
            return (), (), (), str(exc)

        imports: list[str] = []
        classes: list[str] = []
        functions: list[str] = []

        for node in module.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(ast.unparse(node).strip())
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)

        return tuple(imports), tuple(classes), tuple(functions), None

