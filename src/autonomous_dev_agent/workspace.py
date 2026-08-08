"""Git workspace preparation and rollback helpers."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class GitWorkspaceState:
    """Snapshot of the original repository checkout."""

    repository_root: Path
    original_branch: str | None
    original_head: str | None
    temporary_branch: str | None
    prepared_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "repository_root": self.repository_root.as_posix(),
            "original_branch": self.original_branch,
            "original_head": self.original_head,
            "temporary_branch": self.temporary_branch,
            "prepared_at": self.prepared_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "GitWorkspaceState":
        return cls(
            repository_root=Path(str(payload.get("repository_root", "."))).resolve(),
            original_branch=payload.get("original_branch") if payload.get("original_branch") is None else str(payload.get("original_branch")),
            original_head=payload.get("original_head") if payload.get("original_head") is None else str(payload.get("original_head")),
            temporary_branch=payload.get("temporary_branch") if payload.get("temporary_branch") is None else str(payload.get("temporary_branch")),
            prepared_at=datetime.fromisoformat(str(payload.get("prepared_at"))),
        )


class GitWorkspaceManager:
    """Prepare a temporary branch for edits and restore the original state on demand."""

    def __init__(self, repository_root: str | Path, *, state_path: str | Path | None = None) -> None:
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.state_path = (
            Path(state_path).expanduser().resolve()
            if state_path is not None
            else self.repository_root / ".autonomous_dev_agent" / "workspace.json"
        )

    def load_state(self) -> GitWorkspaceState | None:
        if not self.state_path.exists():
            return None
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return GitWorkspaceState.from_dict(payload)

    def save_state(self, state: GitWorkspaceState) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def prepare(self) -> GitWorkspaceState | None:
        if not self._is_git_repository():
            return None

        existing = self.load_state()
        if existing is not None and existing.temporary_branch and self._branch_exists(existing.temporary_branch):
            self._checkout(existing.temporary_branch)
            return existing

        original_branch = self._current_branch()
        original_head = self._current_head()
        temporary_branch = f"autonomous-dev-agent/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
        self._run_git("checkout", "-b", temporary_branch)
        state = GitWorkspaceState(
            repository_root=self.repository_root,
            original_branch=original_branch,
            original_head=original_head,
            temporary_branch=temporary_branch,
            prepared_at=datetime.now(timezone.utc),
        )
        self.save_state(state)
        return state

    def rollback(self) -> bool:
        state = self.load_state()
        if state is None or not self._is_git_repository():
            return False
        if state.original_branch:
            self._checkout(state.original_branch)
        if state.original_head:
            self._run_git("reset", "--hard", state.original_head)
        try:
            self.state_path.unlink(missing_ok=True)
        except OSError:
            pass
        return True

    def clear(self) -> None:
        try:
            self.state_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _is_git_repository(self) -> bool:
        return self._run_git("rev-parse", "--is-inside-work-tree", check=False).returncode == 0

    def _current_branch(self) -> str | None:
        result = self._run_git("branch", "--show-current", check=False)
        branch = result.stdout.strip()
        return branch or None

    def _current_head(self) -> str | None:
        result = self._run_git("rev-parse", "HEAD", check=False)
        head = result.stdout.strip()
        return head or None

    def _branch_exists(self, branch_name: str) -> bool:
        return self._run_git("rev-parse", "--verify", branch_name, check=False).returncode == 0

    def _checkout(self, branch_name: str) -> None:
        self._run_git("checkout", branch_name)

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repository_root), *args],
            capture_output=True,
            text=True,
            check=check,
        )
