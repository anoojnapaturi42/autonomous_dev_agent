from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from autonomous_dev_agent.cli import app as cli_app
from autonomous_dev_agent.cloning import CloneResult
from autonomous_dev_agent.repository import LocalRepository
from autonomous_dev_agent.tester import PytestTestRunner, TestCaseResult, TestRunResult
from typer.testing import CliRunner
from datetime import datetime, timezone


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

    def test_test_command_runs_pytest_and_emits_structured_json(self) -> None:
        if os.environ.get("AUTONOMOUS_DEV_AGENT_RUNNING_PYTEST") == "1":
            fake_result = TestRunResult(
                runner="pytest",
                exit_code=0,
                success=True,
                stdout="",
                stderr="",
                command=(sys.executable, "-m", "pytest", "-q"),
                cwd=REPO_ROOT,
                cases=(
                    TestCaseResult(
                        nodeid="tests/test_sample.py::test_sample",
                        outcome="passed",
                        file="tests/test_sample.py",
                        line=1,
                        duration=0.01,
                    ),
                ),
            )
            with patch("autonomous_dev_agent.cli.PytestTestRunner.run", return_value=fake_result):
                result = CliRunner().invoke(cli_app, ["test"])
        else:
            result = self.run_cli("test")
        exit_code = result.returncode if hasattr(result, "returncode") else result.exit_code
        stdout = result.stdout if hasattr(result, "stdout") else result.output
        stderr = result.stderr if hasattr(result, "stderr") else ""
        self.assertEqual(exit_code, 0, msg=stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["runner"], "pytest")
        self.assertEqual(payload["exit_code"], 0)
        self.assertTrue(payload["success"])
        self.assertIn("summary", payload)
        self.assertIn("cases", payload)
        self.assertEqual(payload["cases"][0]["outcome"], "passed")

    def test_clone_command_returns_structured_json(self) -> None:
        fake_result = CloneResult(
            source="github:octocat/Hello-World",
            source_url="https://github.com/octocat/Hello-World.git",
            destination=Path("/tmp/hello-world"),
            repository_name="Hello-World",
            cloned_at=datetime.now(timezone.utc),
        )
        with patch("autonomous_dev_agent.cli.GitRepositoryCloner.clone", return_value=fake_result):
            result = CliRunner().invoke(cli_app, ["clone", "octocat/Hello-World"])
        self.assertEqual(result.exit_code, 0, msg=result.stderr)
        payload = json.loads(result.output)
        self.assertEqual(payload["repository_name"], "Hello-World")
        self.assertEqual(payload["source_url"], "https://github.com/octocat/Hello-World.git")

    def test_test_command_with_sandbox_uses_docker_executor_when_available(self) -> None:
        fake_result = TestRunResult(
            runner="pytest",
            exit_code=0,
            success=True,
            stdout="",
            stderr="",
            command=("python", "-m", "pytest", "-q"),
            cwd=REPO_ROOT,
            cases=(),
        )
        with patch("autonomous_dev_agent.cli.DockerSandboxRunner.is_available", return_value=True):
            with patch(
                "autonomous_dev_agent.cli.PytestTestRunner.run", return_value=fake_result
            ) as mock_run:
                result = CliRunner().invoke(cli_app, ["test", "--sandbox"])
        self.assertEqual(result.exit_code, 0, msg=result.stderr)
        mock_run.assert_called_once()
        payload = json.loads(result.output)
        self.assertTrue(payload["success"])

    def test_test_command_with_sandbox_fails_clearly_when_docker_unavailable(self) -> None:
        with patch("autonomous_dev_agent.cli.DockerSandboxRunner.is_available", return_value=False):
            result = CliRunner().invoke(cli_app, ["test", "--sandbox"])
        self.assertNotEqual(result.exit_code, 0)

    def test_autonomous_command_runs_and_returns_structured_json(self) -> None:
        fake_result = Mock()
        fake_result.to_dict.return_value = {
            "objective": "Improve the repository based on failed tests",
            "retry_limit": 0,
            "succeeded": True,
            "stop_reason": "tests_passed",
            "attempts": [],
            "final_test_result": {
                "runner": "pytest",
                "exit_code": 0,
                "success": True,
            },
            "final_failure_summary": {
                "total_failures": 0,
                "root_causes": [],
                "failures": [],
            },
        }
        with patch("autonomous_dev_agent.cli.AutonomousEngineer.run", return_value=fake_result):
            result = CliRunner().invoke(cli_app, ["autonomous", "--retry-limit", "0"])
        self.assertEqual(result.exit_code, 0, msg=result.stderr)
        payload = json.loads(result.output)
        self.assertEqual(payload["retry_limit"], 0)
        self.assertTrue(payload["succeeded"])
        self.assertEqual(payload["stop_reason"], "tests_passed")
        self.assertEqual(len(payload["attempts"]), 0)
        self.assertIn("final_failure_summary", payload)


class PytestRunnerTestCase(unittest.TestCase):
    def test_detects_pytest_and_returns_structured_results(self) -> None:
        runner = PytestTestRunner(EVAL_REPOS_ROOT / "pytest_repo")

        self.assertEqual(runner.detect(), "pytest")

        result = runner.run()
        payload = result.to_dict()

        self.assertEqual(result.runner, "pytest")
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.success)
        self.assertIn("summary", payload)
        self.assertIn("cases", payload)
        self.assertEqual(payload["runner"], "pytest")
        self.assertEqual(payload["exit_code"], 0)
        self.assertGreaterEqual(payload["summary"]["passed"], 1)
        self.assertGreaterEqual(len(payload["cases"]), 1)


class LocalRepositoryTestCase(unittest.TestCase):
    def test_lists_files_and_ignores_virtualenv_and_cache_dirs(self) -> None:
        repo = LocalRepository(LOCAL_REPO_FIXTURE)

        files = repo.list_files()

        self.assertEqual(
            files,
            [
                Path("docs/guide.py"),
                Path("src/auth.py"),
                Path("src/graph_a.py"),
                Path("src/graph_b.py"),
                Path("src/module.py"),
                Path("src/notes.txt"),
            ],
        )

    def test_discovers_python_files_only(self) -> None:
        repo = LocalRepository(LOCAL_REPO_FIXTURE)

        python_files = repo.list_python_files()

        self.assertEqual(
            python_files,
            [
                Path("docs/guide.py"),
                Path("src/auth.py"),
                Path("src/graph_a.py"),
                Path("src/graph_b.py"),
                Path("src/module.py"),
            ],
        )

    def test_reads_file_contents(self) -> None:
        repo = LocalRepository(LOCAL_REPO_FIXTURE)

        contents = repo.read_file("src/module.py")

        self.assertTrue(contents.startswith('"""Toy module for AST parsing tests."""'))
        self.assertIn("class SampleWorker(BaseWorker):", contents)
        self.assertIn("@traced", contents)
        self.assertIn("def format_result(value: str) -> str:", contents)
        self.assertIn("def build_index() -> defaultdict[str, int]:", contents)
        self.assertIn("def authenticate_user(username: str, password: str) -> bool:", (LOCAL_REPO_FIXTURE / "src" / "auth.py").read_text())

    def test_rejects_non_git_directory(self) -> None:
        with self.assertRaises(ValueError):
            LocalRepository(NON_REPO_FIXTURE)
