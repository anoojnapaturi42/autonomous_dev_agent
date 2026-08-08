"""Git repository cloning helpers, including GitHub URL normalization."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from .repository import LocalRepository


_GITHUB_SSH_RE = re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$")
_GITHUB_PATH_RE = re.compile(r"^(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$")


@dataclass(frozen=True, slots=True)
class CloneResult:
    """Structured result of cloning a repository."""

    source: str
    source_url: str
    destination: Path
    repository_name: str
    cloned_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "source_url": self.source_url,
            "destination": self.destination.as_posix(),
            "repository_name": self.repository_name,
            "cloned_at": self.cloned_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class GitHubRepositoryReference:
    """Normalized representation of a GitHub repository reference."""

    owner: str
    repository: str
    ref: str | None = None

    @property
    def repository_name(self) -> str:
        return self.repository.removesuffix(".git")

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repository_name}.git"

    @classmethod
    def from_value(cls, value: str) -> "GitHubRepositoryReference | None":
        text = value.strip()
        parsed = urlparse(text)
        if parsed.netloc.lower() == "github.com":
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) < 2:
                return None
            owner, repository = parts[0], parts[1]
            ref = parts[3] if len(parts) > 3 and parts[2] == "tree" else None
            return cls(owner=owner, repository=repository.removesuffix(".git"), ref=ref)
        ssh_match = _GITHUB_SSH_RE.match(text)
        if ssh_match:
            return cls(owner=ssh_match.group("owner"), repository=ssh_match.group("repo").removesuffix(".git"))
        path_match = _GITHUB_PATH_RE.match(text)
        if path_match and "/" in text and "://" not in text and "@" not in text:
            return cls(owner=path_match.group("owner"), repository=path_match.group("repo").removesuffix(".git"))
        return None


class GitRepositoryCloner:
    """Clone a Git repository into a local workspace."""

    def __init__(self, *, git_executable: str = "git") -> None:
        self._git_executable = git_executable

    def clone(
        self,
        source: str | Path | GitHubRepositoryReference,
        destination: str | Path | None = None,
        *,
        branch: str | None = None,
        depth: int | None = 1,
    ) -> CloneResult:
        source_url, repository_name, source_label = self._normalize_source(source)
        destination_path = self._resolve_destination(destination, repository_name)
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        command = [self._git_executable, "clone"]
        if depth is not None and depth > 0:
            command.extend(["--depth", str(depth)])
        if branch:
            command.extend(["--branch", branch])
        command.extend([source_url, str(destination_path)])

        subprocess.run(command, capture_output=True, text=True, check=True)
        return CloneResult(
            source=source_label,
            source_url=source_url,
            destination=destination_path.resolve(),
            repository_name=repository_name,
            cloned_at=datetime.now(timezone.utc),
        )

    def clone_local_repository(
        self,
        source: str | Path | GitHubRepositoryReference,
        destination: str | Path | None = None,
        *,
        branch: str | None = None,
        depth: int | None = 1,
    ) -> LocalRepository:
        result = self.clone(source, destination, branch=branch, depth=depth)
        return LocalRepository(result.destination)

    def _normalize_source(
        self,
        source: str | Path | GitHubRepositoryReference,
    ) -> tuple[str, str, str]:
        if isinstance(source, GitHubRepositoryReference):
            return source.clone_url, source.repository_name, f"github:{source.owner}/{source.repository_name}"

        source_text = str(source).strip()
        github_reference = GitHubRepositoryReference.from_value(source_text)
        if github_reference is not None:
            return github_reference.clone_url, github_reference.repository_name, f"github:{github_reference.owner}/{github_reference.repository_name}"

        source_path = Path(source_text)
        if source_path.exists():
            return str(source_path.resolve()), source_path.name.removesuffix(".git") or source_path.name, source_path.resolve().as_posix()

        repository_name = Path(urlparse(source_text).path).name.removesuffix(".git") or "repository"
        return source_text, repository_name, source_text

    def _resolve_destination(self, destination: str | Path | None, repository_name: str) -> Path:
        if destination is None:
            base = Path.cwd() / "clones"
            return (base / f"{repository_name}-{uuid4().hex[:8]}").resolve()
        destination_path = Path(destination).expanduser()
        if not destination_path.is_absolute():
            destination_path = Path.cwd() / destination_path
        return destination_path.resolve()
