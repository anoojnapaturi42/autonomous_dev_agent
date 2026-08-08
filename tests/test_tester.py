from __future__ import annotations

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
