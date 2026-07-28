"""Recursive repository scanning and Python indexing."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .ast_parser import AstPythonParser
from .embeddings import EmbeddingProvider
from .graphs import build_call_graph, build_module_dependency_graph
from .repository import Repository
from .semantic import build_semantic_index
from .symbol_index import PythonFileIndex, PythonSymbol, RepositoryIndex, SymbolIndex


class RepositoryScanner:
    """Build a structured index for every Python file in a repository."""

    def __init__(self, repository: Repository, *, embedding_provider: EmbeddingProvider | None = None) -> None:
        self._repository = repository
        self._parser = AstPythonParser()
        self._embedding_provider = embedding_provider

    def scan(self) -> RepositoryIndex:
        indexed_files: list[PythonFileIndex] = []
        symbols: list[PythonSymbol] = []
        source_map: dict[Path, str] = {}
        for path in self._repository.list_python_files():
            file_index, contents = self._scan_python_file(path)
            indexed_files.append(file_index)
            symbols.extend(file_index.symbols)
            source_map[file_index.path] = contents
        module_graph = build_module_dependency_graph(indexed_files)
        call_graph = build_call_graph(indexed_files)
        semantic_index = build_semantic_index(
            self._repository.root,
            indexed_files,
            source_map,
            provider=self._embedding_provider,
        )
        return RepositoryIndex(
            root=self._repository.root,
            python_files=tuple(indexed_files),
            symbol_index=SymbolIndex(tuple(symbols)),
            module_graph=module_graph,
            call_graph=call_graph,
            semantic_index=semantic_index,
            scanned_at=datetime.now(timezone.utc),
        )

    def _scan_python_file(self, relative_path: Path) -> tuple[PythonFileIndex, str]:
        absolute_path = self._repository.root / relative_path
        contents = self._repository.read_file(relative_path)
        stat_result = absolute_path.stat()

        parsed = self._parser.parse(
            relative_path,
            contents,
            size=stat_result.st_size,
            modified_at=datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc),
        )
        return parsed.file_index, contents
