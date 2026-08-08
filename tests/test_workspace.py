from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from autonomous_dev_agent.workspace import GitWorkspaceManager


def _run_git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    )


class GitWorkspaceManagerPushTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

        self.remote_dir = self.root / "remote.git"
        self.remote_dir.mkdir()
        _run_git("init", "--bare", "-q", cwd=self.remote_dir)

        self.repo_dir = self.root / "repo"
        self.repo_dir.mkdir()
        _run_git("init", "-q", cwd=self.repo_dir)
        _run_git("config", "user.email", "a@b.com", cwd=self.repo_dir)
        _run_git("config", "user.name", "Test", cwd=self.repo_dir)
        (self.repo_dir / "file.txt").write_text("hello\n", encoding="utf-8")
        _run_git("add", ".", cwd=self.repo_dir)
        _run_git("commit", "-q", "-m", "init", cwd=self.repo_dir)
        _run_git("remote", "add", "origin", str(self.remote_dir), cwd=self.repo_dir)

    def test_push_sends_branch_to_remote(self) -> None:
        manager = GitWorkspaceManager(self.repo_dir)
        state = manager.prepare()
        assert state is not None and state.temporary_branch is not None

        pushed = manager.push(branch=state.temporary_branch)

        self.assertTrue(pushed)
        result = _run_git("branch", "-r", cwd=self.repo_dir)
        self.assertIn(state.temporary_branch, result.stdout)

    def test_push_returns_false_when_remote_missing(self) -> None:
        no_remote_dir = self.root / "no_remote_repo"
        no_remote_dir.mkdir()
        _run_git("init", "-q", cwd=no_remote_dir)
        _run_git("config", "user.email", "a@b.com", cwd=no_remote_dir)
        _run_git("config", "user.name", "Test", cwd=no_remote_dir)
        (no_remote_dir / "file.txt").write_text("hi\n", encoding="utf-8")
        _run_git("add", ".", cwd=no_remote_dir)
        _run_git("commit", "-q", "-m", "init", cwd=no_remote_dir)

        manager = GitWorkspaceManager(no_remote_dir)
        state = manager.prepare()
        assert state is not None and state.temporary_branch is not None

        pushed = manager.push(branch=state.temporary_branch)

        self.assertFalse(pushed)

    def test_authenticated_remote_url_embeds_token_only_for_github_https(self) -> None:
        manager = GitWorkspaceManager(self.repo_dir)

        github_url = manager._authenticated_remote_url("https://github.com/octocat/Hello-World.git", "secret")
        self.assertTrue(github_url.startswith("https://x-access-token:secret@github.com/"))

        local_url = manager._authenticated_remote_url(str(self.remote_dir), "secret")
        self.assertEqual(local_url, str(self.remote_dir))

        no_token_url = manager._authenticated_remote_url("https://github.com/octocat/Hello-World.git", None)
        self.assertEqual(no_token_url, "https://github.com/octocat/Hello-World.git")


if __name__ == "__main__":
    unittest.main()
