"""Semantic chunking, embeddings, and search over repository code."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .embeddings import EmbeddingProvider, EmbeddingProviderConfig, create_embedding_provider
from .symbol_index import PythonFileIndex, PythonSymbol


@dataclass(frozen=True, slots=True)
class SemanticChunk:
    """A logical code chunk linked back to the repository."""

    repository_root: Path
    path: Path
    symbol_name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    text: str
    docstring: str | None
    decorators: tuple[str, ...]
    bases: tuple[str, ...]
    embedding: tuple[float, ...]

    @property
    def chunk_id(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}:{self.qualified_name}"

    def to_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "repository_root": self.repository_root.as_posix(),
            "path": self.path.as_posix(),
            "symbol_name": self.symbol_name,
            "qualified_name": self.qualified_name,
            "kind": self.kind,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "docstring": self.docstring,
            "decorators": list(self.decorators),
            "bases": list(self.bases),
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class SemanticSearchResult:
    """Ranked result from semantic search."""

    chunk: SemanticChunk
    score: float

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "chunk": self.chunk.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SemanticIndex:
    """Semantic index over repository code chunks."""

    chunks: tuple[SemanticChunk, ...]
    provider: EmbeddingProvider

    def search(self, query: str, *, top_k: int = 5) -> tuple[SemanticSearchResult, ...]:
        query_embedding = self.provider.embed(query)
        scored = [
            SemanticSearchResult(chunk=chunk, score=_cosine_similarity(query_embedding, chunk.embedding))
            for chunk in self.chunks
        ]
        scored.sort(key=lambda result: (-result.score, result.chunk.path.as_posix(), result.chunk.start_line, result.chunk.symbol_name))
        return tuple(scored[:top_k])

    def to_json(self, query: str, *, top_k: int = 5, indent: int = 2) -> str:
        results = self.search(query, top_k=top_k)
        payload = {
            "query": query,
            "top_k": top_k,
            "results": [result.to_dict() for result in results],
        }
        return json.dumps(payload, indent=indent, sort_keys=True)


def build_semantic_index(
    repository_root: Path,
    files: tuple[PythonFileIndex, ...] | list[PythonFileIndex],
    source_map: dict[Path, str],
    *,
    provider: EmbeddingProvider | None = None,
) -> SemanticIndex:
    active_provider = provider or create_embedding_provider(EmbeddingProviderConfig())
    chunks: list[SemanticChunk] = []
    for file_index in files:
        source = source_map[file_index.path]
        source_lines = source.splitlines()
        for symbol in file_index.symbols:
            if symbol.kind not in {"class", "function", "method"}:
                continue
            text = _build_chunk_text(symbol, source_lines)
            embedding = active_provider.embed(text)
            chunks.append(
                SemanticChunk(
                    repository_root=repository_root,
                    path=file_index.path,
                    symbol_name=symbol.name,
                    qualified_name=symbol.qualified_name,
                    kind=symbol.kind,
                    start_line=symbol.source_start_line or symbol.line,
                    end_line=symbol.end_line,
                    text=text,
                    docstring=symbol.docstring,
                    decorators=symbol.decorators,
                    bases=symbol.bases,
                    embedding=embedding,
                )
            )
    return SemanticIndex(chunks=tuple(chunks), provider=active_provider)


def _build_chunk_text(symbol: PythonSymbol, source_lines: list[str]) -> str:
    excerpt = _slice_source(source_lines, symbol.source_start_line or symbol.line, symbol.end_line)
    metadata_lines = [
        f"name: {symbol.qualified_name}",
        f"kind: {symbol.kind}",
    ]
    if symbol.docstring:
        metadata_lines.append(f"docstring: {symbol.docstring}")
    if symbol.decorators:
        metadata_lines.append(f"decorators: {', '.join(symbol.decorators)}")
    if symbol.bases:
        metadata_lines.append(f"bases: {', '.join(symbol.bases)}")
    metadata_lines.append("code:")
    metadata_lines.append(excerpt)
    return "\n".join(metadata_lines)


def _slice_source(source_lines: list[str], start_line: int, end_line: int) -> str:
    if start_line < 1:
        start_line = 1
    if end_line < start_line:
        end_line = start_line
    selected = source_lines[start_line - 1 : end_line]
    return "\n".join(selected)


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions do not match.")
    numerator = sum(l * r for l, r in zip(left, right))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)
