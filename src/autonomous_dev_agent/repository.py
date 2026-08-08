"""Repository abstractions for codebases the agent can operate on."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


_IGNORED_NAMES = {
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".hypothesis",
    ".autonomous_dev_agent",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "git-meta",
}


class Repository(ABC):
    """Common interface for any repository provider."""

    root: Path

    @abstractmethod
    def validate(self) -> None:
        """Ensure the repository provider is usable."""

    @abstractmethod
    def list_files(self) -> list[Path]:
        """Return repository files relative to the repository root."""

    @abstractmethod
    def list_python_files(self) -> list[Path]:
        """Return Python files relative to the repository root."""

    @abstractmethod
    def read_file(self, path: str | Path, encoding: str = "utf-8") -> str:
        """Read a file from the repository."""


@dataclass(slots=True)
class LocalRepository(Repository):
    """Repository provider for a local Git checkout."""

    root: Path
    ignored_directory_names: frozenset[str] = field(
        default_factory=lambda: frozenset(_IGNORED_NAMES)
    )

    def __post_init__(self) -> None:
        self.root = self.root.expanduser().resolve()
        self.validate()

    def validate(self) -> None:
        if not self.root.exists():
            raise FileNotFoundError(f"Repository root does not exist: {self.root}")
        if not self.root.is_dir():
            raise NotADirectoryError(f"Repository root is not a directory: {self.root}")
        if not self._has_git_metadata():
            raise ValueError(f"Repository root is not a Git repository: {self.root}")

    def list_files(self) -> list[Path]:
        files = list(self._iter_files())
        return sorted(files)

    def list_python_files(self) -> list[Path]:
        return [path for path in self.list_files() if path.suffix == ".py"]

    def read_file(self, path: str | Path, encoding: str = "utf-8") -> str:
        resolved_path = self._resolve_repo_path(path)
        return resolved_path.read_text(encoding=encoding)

    def _has_git_metadata(self) -> bool:
        metadata_path = self.root / ".git"
        if metadata_path.is_dir():
            return True
        if metadata_path.is_file():
            try:
                contents = metadata_path.read_text(encoding="utf-8").strip()
            except OSError:
                return False
            if contents.lower().startswith("gitdir:"):
                git_path = contents.split(":", maxsplit=1)[1].strip()
                candidate = (metadata_path.parent / git_path).resolve()
                return candidate.exists()
        return False

    def _iter_files(self) -> Iterator[Path]:
        for current_root, dirnames, filenames in self._walkable(self.root):
            relative_root = current_root.relative_to(self.root)
            for filename in filenames:
                if filename == ".git":
                    continue
                if filename in self.ignored_directory_names:
                    continue
                yield relative_root / filename if relative_root != Path(".") else Path(filename)

    def _walkable(self, root: Path) -> Iterator[tuple[Path, list[str], list[str]]]:
        for current_root, dirnames, filenames in self._walk(root):
            dirnames[:] = [name for name in dirnames if name not in self.ignored_directory_names]
            yield current_root, dirnames, filenames

    def _walk(self, root: Path) -> Iterator[tuple[Path, list[str], list[str]]]:
        import os

        for current_root, dirnames, filenames in os.walk(root):
            yield Path(current_root), dirnames, filenames

    def _resolve_repo_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"Path is outside the repository root: {path}") from exc
        if not resolved.is_file():
            raise FileNotFoundError(f"Repository file does not exist: {path}")
        return resolved
