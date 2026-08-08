from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from autonomous_dev_agent.sandbox import (
    DockerNotAvailableError,
    DockerSandboxRunner,
    LocalCommandExecutor,
)


class DockerSandboxRunnerTestCase(unittest.TestCase):
    def test_build_command_mounts_repo_and_disables_network_by_default(self) -> None:
        runner = DockerSandboxRunner(image="python:3.11-slim")

        command = runner.build_command(
            ["python", "-m", "pytest", "-q"],
            cwd=Path("/repo"),
            env={"AUTONOMOUS_DEV_AGENT_RUNNING_PYTEST": "1"},
        )

        self.assertEqual(command[0], "docker")
        self.assertIn("--rm", command)
        self.assertIn("-v", command)
        self.assertIn("/repo:/workspace", command)
        self.assertIn("-w", command)
        self.assertIn("/workspace", command)
        self.assertIn("--network", command)
        self.assertIn("none", command)
        self.assertIn("-e", command)
        self.assertIn("AUTONOMOUS_DEV_AGENT_RUNNING_PYTEST=1", command)
        self.assertEqual(command[-5:], ["python:3.11-slim", "python", "-m", "pytest", "-q"])

    def test_build_command_respects_memory_and_cpu_limits(self) -> None:
        runner = DockerSandboxRunner(memory_limit="256m", cpu_limit="2")

        command = runner.build_command(["python", "-m", "pytest"], cwd=Path("/repo"))

        self.assertIn("--memory", command)
        self.assertIn("256m", command)
        self.assertIn("--cpus", command)
        self.assertIn("2", command)

    def test_network_can_be_enabled(self) -> None:
        runner = DockerSandboxRunner(network_disabled=False)

        command = runner.build_command(["python", "-m", "pytest"], cwd=Path("/repo"))

        self.assertNotIn("--network", command)

    def test_run_invokes_subprocess_with_built_command(self) -> None:
        runner = DockerSandboxRunner()
        fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")

        with patch("autonomous_dev_agent.sandbox.subprocess.run", return_value=fake_result) as mock_run:
            result = runner.run(["python", "-m", "pytest"], cwd=Path("/repo"))

        self.assertEqual(result.returncode, 0)
        called_command = mock_run.call_args.args[0]
        self.assertEqual(called_command[0], "docker")

    def test_run_raises_clear_error_when_docker_executable_missing(self) -> None:
        runner = DockerSandboxRunner(docker_executable="docker-does-not-exist")

        with patch(
            "autonomous_dev_agent.sandbox.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            with self.assertRaises(DockerNotAvailableError):
                runner.run(["python", "-m", "pytest"], cwd=Path("/repo"))

    def test_is_available_reflects_docker_version_check(self) -> None:
        runner = DockerSandboxRunner()
        fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="24.0.0", stderr="")

        with patch("autonomous_dev_agent.sandbox.subprocess.run", return_value=fake_result):
            self.assertTrue(runner.is_available())

        with patch("autonomous_dev_agent.sandbox.subprocess.run", side_effect=FileNotFoundError):
            self.assertFalse(runner.is_available())


class LocalCommandExecutorTestCase(unittest.TestCase):
    def test_resolves_python_executable_when_default_requested(self) -> None:
        executor = LocalCommandExecutor()

        self.assertNotEqual(executor.python_executable, "python")
        self.assertTrue(Path(executor.python_executable).exists())

    def test_run_merges_extra_env_with_host_environment(self) -> None:
        executor = LocalCommandExecutor()
        fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("autonomous_dev_agent.sandbox.subprocess.run", return_value=fake_result) as mock_run:
            executor.run(["python", "--version"], cwd=Path("."), env={"EXTRA": "1"})

        passed_env = mock_run.call_args.kwargs["env"]
        self.assertEqual(passed_env.get("EXTRA"), "1")


if __name__ == "__main__":
    unittest.main()
