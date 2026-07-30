"""Test execution helpers for detecting and running repository tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class TestRunResult:
    """Structured result from running repository tests."""

    runner: str
    exit_code: int
    success: bool
    stdout: str
    stderr: str
    command: tuple[str, ...]
    cwd: Path

    def to_dict(self) -> dict[str, Any]:
        summary = self._parse_summary(self.stdout)
        return {
            "runner": self.runner,
            "exit_code": self.exit_code,
            "success": self.success,
            "command": list(self.command),
            "cwd": self.cwd.as_posix(),
            "summary": summary,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def _parse_summary(self, output: str) -> dict[str, int]:
        summary: dict[str, int] = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        for line in output.splitlines():
            if "passed" in line and "failed" in line and "skipped" in line:
                parts = line.split()
                for token in parts:
                    if token.startswith("passed"):
                        summary["passed"] = int(token.split("=")[0].replace("passed", "")) if "=" in token else 0
                    elif token.startswith("failed"):
                        summary["failed"] = int(token.split("=")[0].replace("failed", "")) if "=" in token else 0
                    elif token.startswith("skipped"):
                        summary["skipped"] = int(token.split("=")[0].replace("skipped", "")) if "=" in token else 0
                    elif token.startswith("errors"):
                        summary["errors"] = int(token.split("=")[0].replace("errors", "")) if "=" in token else 0
        if summary == {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}:
            for line in output.splitlines():
                if line.strip().startswith("==") and "passed" in line:
                    break
        return summary


class PytestTestRunner:
    """Detect pytest availability and run repository tests."""

    def __init__(self, repository_root: str | os.PathLike[str] | Path) -> None:
        self._repository_root = Path(repository_root).resolve()

    def detect(self) -> str:
        if self._has_pytest_configuration() or self._has_pytest_tests():
            return "pytest"
        return "none"

    def run(self) -> TestRunResult:
        if self.detect() != "pytest":
            return TestRunResult(
                runner="none",
                exit_code=0,
                success=True,
                stdout="",
                stderr="",
                command=(),
                cwd=self._repository_root,
            )

        command = [sys.executable, "-m", "pytest", "-q"]
        completed = subprocess.run(
            command,
            cwd=self._repository_root,
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
        return TestRunResult(
            runner="pytest",
            exit_code=completed.returncode,
            success=completed.returncode == 0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            command=tuple(command),
            cwd=self._repository_root,
        )

    def _has_pytest_configuration(self) -> bool:
        return any((self._repository_root / name).exists() for name in ("pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg"))

    def _has_pytest_tests(self) -> bool:
        tests_dir = self._repository_root / "tests"
        if not tests_dir.exists():
            return False
        return any(path.suffix == ".py" for path in tests_dir.rglob("*.py"))
