from __future__ import annotations

import subprocess
from pathlib import Path

from autonomous_dev_agent.tester import PytestTestRunner, TestRunResult


def test_parses_structured_failure_analysis_from_pytest_output() -> None:
    runner = PytestTestRunner(Path(__file__).resolve().parents[1])
    result = TestRunResult(
        runner="pytest",
        exit_code=1,
        success=False,
        stdout=(
            "============================= test session starts ==============================\n"
            "FAILED tests/test_example.py::test_addition - AssertionError: assert 2 == 3\n"
            "E   assert 2 == 3\n"
            "ERROR tests/test_example.py::test_import - ModuleNotFoundError: No module named 'missing_mod'\n"
            "E   ModuleNotFoundError: No module named 'missing_mod'\n"
        ),
        stderr="",
        command=("python", "-m", "pytest", "-q"),
        cwd=Path(__file__).resolve().parents[1],
    )

    analysis = runner.analyze(result)
    payload = analysis.to_dict()

    assert payload["total_failures"] == 2
    assert payload["failures"][0]["failure_type"] == "AssertionError"
    assert payload["failures"][0]["root_cause"] == "assertion_mismatch"
    assert "assertion" in payload["failures"][0]["summary"].lower()
    assert payload["failures"][1]["failure_type"] == "ModuleNotFoundError"
    assert payload["failures"][1]["root_cause"] == "missing_dependency"


class _FakeExecutor:
    """Minimal CommandExecutor stand-in used to verify PytestTestRunner
    delegates execution instead of calling subprocess directly, and to
    simulate a sandboxed (e.g. Docker) python executable name."""

    python_executable = "python"

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Path]] = []

    def run(self, command, *, cwd, env=None, timeout=None):  # noqa: ANN001
        self.calls.append((list(command), Path(cwd)))
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="1 passed", stderr="")


def test_runner_delegates_execution_to_injected_executor() -> None:
    executor = _FakeExecutor()
    runner = PytestTestRunner(Path(__file__).resolve().parents[1], executor=executor)

    result = runner.run()

    assert len(executor.calls) == 1
    called_command, called_cwd = executor.calls[0]
    assert called_command[0] == "python"
    assert "pytest" in called_command
    assert called_cwd == Path(__file__).resolve().parents[1]
    assert result.exit_code == 0
    assert result.success is True


def test_runner_writes_junit_report_inside_repository_for_sandbox_visibility() -> None:
    executor = _FakeExecutor()
    repo_root = Path(__file__).resolve().parents[1]
    runner = PytestTestRunner(repo_root, executor=executor)

    runner.run()

    called_command, _ = executor.calls[0]
    junitxml_arg = next(arg for arg in called_command if arg.startswith("--junitxml="))
    report_relative_path = junitxml_arg.removeprefix("--junitxml=")
    # Must be a relative path inside the repo (not an absolute host temp
    # path) so a bind-mounted sandbox container can also write to it.
    assert not Path(report_relative_path).is_absolute()
    assert report_relative_path.startswith(".autonomous_dev_agent")
