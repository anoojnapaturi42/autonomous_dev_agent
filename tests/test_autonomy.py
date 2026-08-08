from __future__ import annotations

from pathlib import Path

from autonomous_dev_agent.autonomy import AutonomousEngineer
from autonomous_dev_agent.editing import SymbolEdit
from autonomous_dev_agent.repository import LocalRepository


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTONOMY_REPO = REPO_ROOT / "eval_repos" / "autonomy_repo"


def test_autonomous_engine_retries_until_the_failure_is_fixed() -> None:
    core_path = AUTONOMY_REPO / "app_pkg" / "core.py"
    baseline_text = "def answer() -> int:\n    return 41\n"
    core_path.write_text(baseline_text, encoding="utf-8")

    def strategy(context):
        assert context.failure_summary.total_failures == 1
        assert context.failure_summary.root_causes[0].root_cause == "assertion_mismatch"
        return (
            SymbolEdit(
                path=Path("app_pkg/core.py"),
                symbol_name="answer",
                qualified_name="answer",
                replacement_text="def answer() -> int:\n    return 42\n",
            ),
        )

    try:
        repo = LocalRepository(AUTONOMY_REPO)
        engineer = AutonomousEngineer(repo, retry_limit=1, edit_strategy=strategy)
        result = engineer.run("Make the test suite pass", retry_limit=1)

        assert result.succeeded is True
        assert result.stop_reason == "tests_passed"
        assert len(result.attempts) == 2
        assert result.attempts[0].status == "edited"
        assert result.attempts[0].failure_summary.root_causes[0].root_cause == "assertion_mismatch"
        assert result.attempts[1].status == "passed"
        assert result.final_failure_summary.total_failures == 0
    finally:
        core_path.write_text(baseline_text, encoding="utf-8")
