from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from autonomous_dev_agent.repository import LocalRepository


REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_REPOS_ROOT = REPO_ROOT / "eval_repos"
LOCAL_REPO_FIXTURE = EVAL_REPOS_ROOT / "toy"
NON_REPO_FIXTURE = EVAL_REPOS_ROOT / "not_a_repo"


class CLITestCase(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        src_path = str(REPO_ROOT / "src")
        env["PYTHONPATH"] = (
            src_path if not env.get("PYTHONPATH") else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
        )
        return subprocess.run(
            [sys.executable, "-m", "autonomous_dev_agent", *args],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_help_starts_successfully(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Usage", result.stdout)

    def test_placeholder_agent_command_runs(self) -> None:
        result = self.run_cli("agent")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("agent logic is not implemented yet", result.stdout.lower())


class LocalRepositoryTestCase(unittest.TestCase):
    def test_lists_files_and_ignores_virtualenv_and_cache_dirs(self) -> None:
        repo = LocalRepository(LOCAL_REPO_FIXTURE)

        files = repo.list_files()

        self.assertEqual(
            files,
            [
                Path("docs/guide.py"),
                Path("src/module.py"),
                Path("src/notes.txt"),
            ],
        )

    def test_discovers_python_files_only(self) -> None:
        repo = LocalRepository(LOCAL_REPO_FIXTURE)

        python_files = repo.list_python_files()

        self.assertEqual(
            python_files,
            [Path("docs/guide.py"), Path("src/module.py")],
        )

    def test_reads_file_contents(self) -> None:
        repo = LocalRepository(LOCAL_REPO_FIXTURE)

        contents = repo.read_file("src/module.py")

        self.assertTrue(contents.startswith('"""Toy module for AST parsing tests."""'))
        self.assertIn("class SampleWorker(BaseWorker):", contents)
        self.assertIn("@traced", contents)
        self.assertIn("def build_index() -> defaultdict[str, int]:", contents)

    def test_rejects_non_git_directory(self) -> None:
        with self.assertRaises(ValueError):
            LocalRepository(NON_REPO_FIXTURE)
