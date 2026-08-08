"""Safe, diff-first file editing for repository codebases."""

from __future__ import annotations

import difflib
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .repository import Repository
from .symbol_index import PythonSymbol, RepositoryIndex


@dataclass(frozen=True, slots=True)
class FileEdit:
    """Replace the full contents of a file."""

    path: Path
    replacement_text: str


@dataclass(frozen=True, slots=True)
class SpanEdit:
    """Replace a specific 1-based line range in a file."""

    path: Path
    start_line: int
    end_line: int
    replacement_text: str


@dataclass(frozen=True, slots=True)
class SymbolEdit:
    """Replace a symbol identified through the AST symbol index."""

    path: Path
    replacement_text: str
    symbol_name: str | None = None
    qualified_name: str | None = None


EditRequest = FileEdit | SpanEdit | SymbolEdit


@dataclass(frozen=True, slots=True)
class EditPreview:
    """A diff-first preview of one planned file modification."""

    path: Path
    strategy: str
    start_line: int | None
    end_line: int | None
    original_text: str
    updated_text: str
    diff: str
    symbol_name: str | None = None
    qualified_name: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path.as_posix(),
            "strategy": self.strategy,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol_name": self.symbol_name,
            "qualified_name": self.qualified_name,
            "diff": self.diff,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "EditPreview":
        return cls(
            path=Path(str(payload.get("path", ""))),
            strategy=str(payload.get("strategy", "unknown")),
            start_line=payload.get("start_line"),
            end_line=payload.get("end_line"),
            original_text="",
            updated_text="",
            diff=str(payload.get("diff", "")),
            symbol_name=payload.get("symbol_name") if payload.get("symbol_name") is None else str(payload.get("symbol_name")),
            qualified_name=payload.get("qualified_name") if payload.get("qualified_name") is None else str(payload.get("qualified_name")),
        )


@dataclass(frozen=True, slots=True)
class EditResult:
    """Result of applying a batch of edits."""

    previews: tuple[EditPreview, ...]
    written_paths: tuple[Path, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "written_paths": [path.as_posix() for path in self.written_paths],
            "previews": [preview.to_dict() for preview in self.previews],
        }


class SafeEditingEngine:
    """Apply repository edits after generating Git-style unified diffs."""

    def __init__(self, repository: Repository, *, repository_index: RepositoryIndex | None = None) -> None:
        self._repository = repository
        self._repository_index = repository_index

    def preview(self, edits: Iterable[EditRequest]) -> tuple[EditPreview, ...]:
        working_text: dict[Path, str] = {}
        previews: list[EditPreview] = []
        for edit in edits:
            resolved_path, strategy, start_line, end_line, original_text, updated_text, symbol_name, qualified_name = self._apply_to_working_copy(
                edit,
                working_text,
            )
            previews.append(
                EditPreview(
                    path=resolved_path,
                    strategy=strategy,
                    start_line=start_line,
                    end_line=end_line,
                    original_text=original_text,
                    updated_text=updated_text,
                    diff=_unified_diff(self._relative_path(resolved_path), original_text, updated_text),
                    symbol_name=symbol_name,
                    qualified_name=qualified_name,
                )
            )
        return tuple(previews)

    def apply(self, edits: Iterable[EditRequest]) -> EditResult:
        previews = self.preview(edits)
        written_paths: list[Path] = []
        for preview in previews:
            preview.path.write_text(preview.updated_text, encoding="utf-8")
            written_paths.append(preview.path)
        return EditResult(previews=previews, written_paths=tuple(written_paths))

    def _apply_to_working_copy(
        self,
        edit: EditRequest,
        working_text: dict[Path, str],
    ) -> tuple[Path, str, int | None, int | None, str, str, str | None, str | None]:
        if isinstance(edit, FileEdit):
            path = self._resolve_path(edit.path)
            original_text = self._working_text(path, working_text)
            updated_text = _normalize_full_file_replacement(original_text, edit.replacement_text)
            working_text[path] = updated_text
            return path, "file", None, None, original_text, updated_text, None, None

        if isinstance(edit, SpanEdit):
            path = self._resolve_path(edit.path)
            original_text = self._working_text(path, working_text)
            updated_text = _replace_line_span(
                original_text,
                edit.start_line,
                edit.end_line,
                edit.replacement_text,
            )
            working_text[path] = updated_text
            return path, "span", edit.start_line, edit.end_line, original_text, updated_text, None, None

        if isinstance(edit, SymbolEdit):
            path = self._resolve_path(edit.path)
            original_text = self._working_text(path, working_text)
            symbol = self._resolve_symbol(edit)
            updated_text = _replace_line_span(
                original_text,
                symbol.source_start_line or symbol.line,
                symbol.end_line,
                _reindent_symbol_replacement(symbol, edit.replacement_text, original_text),
            )
            working_text[path] = updated_text
            return (
                path,
                "symbol",
                symbol.source_start_line or symbol.line,
                symbol.end_line,
                original_text,
                updated_text,
                symbol.name,
                symbol.qualified_name,
            )

        raise TypeError(f"Unsupported edit type: {type(edit)!r}")

    def _resolve_symbol(self, edit: SymbolEdit) -> PythonSymbol:
        if self._repository_index is None:
            raise ValueError("Symbol edits require a repository index.")

        path_candidates = [edit.path]
        if not Path(edit.path).is_absolute():
            path_candidates.append(self._repository.root / edit.path)
        symbols: list[PythonSymbol] = []
        for candidate in path_candidates:
            symbols.extend(self._repository_index.symbol_index.find_in_file(candidate))
        candidates = [
            symbol
            for symbol in symbols
            if symbol.kind in {"class", "function", "method"}
            and (edit.symbol_name is None or symbol.name == edit.symbol_name)
            and (edit.qualified_name is None or symbol.qualified_name == edit.qualified_name)
        ]
        if not candidates:
            raise LookupError(f"Could not find symbol to edit: {edit.path}")
        if len(candidates) > 1 and edit.qualified_name is None:
            raise LookupError(
                "Symbol edit is ambiguous without a qualified name: "
                f"{edit.symbol_name!r} in {edit.path}"
            )
        return candidates[0]

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._repository.root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self._repository.root)
        except ValueError as exc:
            raise ValueError(f"Path is outside the repository root: {path}") from exc
        if not resolved.exists():
            raise FileNotFoundError(f"Repository file does not exist: {path}")
        return resolved

    def _read_file(self, path: Path) -> str:
        return self._repository.read_file(path)

    def _relative_path(self, path: Path) -> Path:
        return path.relative_to(self._repository.root)

    def _working_text(self, path: Path, working_text: dict[Path, str]) -> str:
        if path not in working_text:
            working_text[path] = self._read_file(path)
        return working_text[path]


def _replace_line_span(original_text: str, start_line: int, end_line: int, replacement_text: str) -> str:
    if start_line < 1:
        raise ValueError("start_line must be greater than or equal to 1")
    if end_line < start_line:
        raise ValueError("end_line must be greater than or equal to start_line")

    original_lines = original_text.splitlines(keepends=True)
    start_index = start_line - 1
    end_index = min(end_line, len(original_lines))
    replacement = _normalize_span_replacement(original_text, replacement_text, original_lines, start_index, end_index)
    updated_lines = [*original_lines[:start_index], *replacement, *original_lines[end_index:]]
    return "".join(updated_lines)


def _normalize_span_replacement(
    original_text: str,
    replacement_text: str,
    original_lines: list[str],
    start_index: int,
    end_index: int,
) -> list[str]:
    if not replacement_text:
        return []

    newline = _detect_newline(original_text)
    normalized = replacement_text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = textwrap.dedent(normalized)
    if normalized and not normalized.endswith("\n") and original_text.endswith(("\n", "\r\n")):
        normalized = f"{normalized}\n"
    normalized = normalized.replace("\n", newline)
    return normalized.splitlines(keepends=True)


def _normalize_full_file_replacement(original_text: str, replacement_text: str) -> str:
    if replacement_text == "":
        return replacement_text
    newline = _detect_newline(original_text)
    normalized = replacement_text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", newline)
    if original_text.endswith(("\n", "\r\n")) and not normalized.endswith(("\n", "\r\n")):
        normalized = f"{normalized}{newline}"
    return normalized


def _reindent_symbol_replacement(symbol: PythonSymbol, replacement_text: str, original_text: str) -> str:
    if not replacement_text:
        return replacement_text

    original_lines = original_text.splitlines()
    start_line = (symbol.source_start_line or symbol.line) - 1
    if start_line < 0 or start_line >= len(original_lines):
        return replacement_text

    target_line = original_lines[start_line]
    indent = target_line[: len(target_line) - len(target_line.lstrip())]
    normalized = textwrap.dedent(replacement_text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = normalized.split("\n")
    reindented = [
        f"{indent}{line}" if line.strip() else ""
        for line in lines
    ]
    return "\n".join(reindented)


def _unified_diff(path: Path, original_text: str, updated_text: str) -> str:
    original_lines = original_text.splitlines(keepends=True)
    updated_lines = updated_text.splitlines(keepends=True)
    diff_lines = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=f"a/{path.as_posix()}",
        tofile=f"b/{path.as_posix()}",
        lineterm="\n",
    )
    return "".join(diff_lines)


def _detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"
