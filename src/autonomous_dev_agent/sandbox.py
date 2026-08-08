"""Command execution abstractions, including Docker-sandboxed execution.

This module keeps "where a command runs" separate from "what command to run
and how to interpret its output" (that logic stays in tester.py). Both
executors expose the same run() signature so PytestTestRunner can use either
one interchangeably.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, Sequence


class CommandExecutor(Protocol):
    """Common interface for running a command against a repository checkout."""

    python_executable: str

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a command rooted at cwd and return the completed process."""


@dataclass(slots=True)
class LocalCommandExecutor:
    """Runs commands directly on the host, inheriting the current environment."""

    python_executable: str = field(default="python")

    def __post_init__(self) -> None:
        if self.python_executable == "python":
            import sys

            self.python_executable = sys.executable

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        merged_env = {**os.environ, **(env or {})}
        return subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=merged_env,
            timeout=timeout,
        )


class DockerNotAvailableError(RuntimeError):
    """Raised when the Docker CLI cannot be reached."""


@dataclass(slots=True)
class DockerSandboxRunner:
    """Runs commands inside an isolated, disposable Docker container.

    The repository root is bind-mounted into the container so file changes
    (e.g. test report files) are visible on the host after the run. The
    container has no network access by default and runs with a
    memory/CPU ceiling so a runaway or malicious repository cannot affect
    the host or other work.
    """

    image: str = "python:3.11-slim"
    docker_executable: str = "docker"
    memory_limit: str = "512m"
    cpu_limit: str = "1"
    network_disabled: bool = True
    python_executable: str = "python"
    workdir: str = "/workspace"
    extra_run_args: tuple[str, ...] = ()

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                [self.docker_executable, "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        docker_command = self.build_command(command, cwd=cwd, env=env)
        try:
            return subprocess.run(
                docker_command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise DockerNotAvailableError(
                f"Docker executable '{self.docker_executable}' was not found. "
                "Install Docker Desktop or the Docker Engine CLI to use the sandbox."
            ) from exc

    def build_command(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
    ) -> list[str]:
        """Build the full `docker run` argument list for inspection or execution."""

        docker_command: list[str] = [
            self.docker_executable,
            "run",
            "--rm",
            "-v",
            f"{cwd}:{self.workdir}",
            "-w",
            self.workdir,
            "--memory",
            self.memory_limit,
            "--cpus",
            self.cpu_limit,
        ]
        if self.network_disabled:
            docker_command.extend(["--network", "none"])
        for key, value in (env or {}).items():
            docker_command.extend(["-e", f"{key}={value}"])
        docker_command.extend(self.extra_run_args)
        docker_command.append(self.image)
        docker_command.extend(command)
        return docker_command
