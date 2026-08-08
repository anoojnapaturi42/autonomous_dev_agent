from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from datetime import datetime, timezone
from pathlib import Path

from autonomous_dev_agent.editing import SymbolEdit
from autonomous_dev_agent.checkpoint import OrchestrationCheckpointStore
from autonomous_dev_agent.memory import (
    FailureMemoryRecord,
    PersistentMemoryStore,
    RepositorySummaryRecord,
    SuccessfulFixRecord,
    TaskMemoryRecord,
)
from autonomous_dev_agent.orchestrator import AutonomousOrchestrator, AutonomousAttempt
from autonomous_dev_agent.planning import ExecutionPlan, PlanStep
from autonomous_dev_agent.repository import LocalRepository
from autonomous_dev_agent.tester import FailureAnalysis, FailureCauseSummary, FailureSummary, TestCaseResult, TestRunResult
from autonomous_dev_agent.workspace import GitWorkspaceManager


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTONOMY_REPO = REPO_ROOT / "eval_repos" / "autonomy_repo"


class MemoryStoreTestCase(unittest.TestCase):
    def test_memory_store_round_trips_and_recalls(self) -> None:
        store_path = REPO_ROOT / ".tmp_memory_store.json"
        store = PersistentMemoryStore(store_path)
        repository_root = AUTONOMY_REPO.as_posix()
        timestamp = datetime(2026, 8, 8, tzinfo=timezone.utc)

        try:
            store.record_task(
                TaskMemoryRecord(
                    objective="Fix the failing authentication test",
                    repository_root=repository_root,
                    retry_limit=2,
                    succeeded=True,
                    stop_reason="tests_passed",
                    attempt_count=2,
                    recorded_at=timestamp,
                )
            )
            store.record_failure(
                FailureMemoryRecord(
                    objective="Fix the failing authentication test",
                    repository_root=repository_root,
                    test_name="tests.test_core::test_answer",
                    failure_type="AssertionError",
                    root_cause="assertion_mismatch",
                    summary="An assertion failed, indicating the observed value did not match the expected behavior.",
                    detail="assert 41 == 42",
                    attempt_number=1,
                    recorded_at=timestamp,
                )
            )
            store.record_successful_fix(
                SuccessfulFixRecord(
                    objective="Fix the failing authentication test",
                    repository_root=repository_root,
                    summary="Resolved prior failure root causes: assertion_mismatch.",
                    fixed_paths=("app_pkg/core.py",),
                    root_causes=("assertion_mismatch",),
                    test_summary="1 passed, 0 failed, 0 errors, 0 skipped across 1 cases.",
                    recorded_at=timestamp,
                )
            )
            store.record_repository_summary(
                RepositorySummaryRecord(
                    repository_root=repository_root,
                    summary="Authentication test repository with 1 Python files and 2 symbols.",
                    python_file_count=1,
                    symbol_count=2,
                    top_files=("app_pkg/core.py",),
                    recorded_at=timestamp,
                )
            )

            reloaded = store.load()
            recall = store.recall("authentication test", AUTONOMY_REPO, limit=5)

            self.assertEqual(len(reloaded.tasks), 1)
            self.assertEqual(len(reloaded.failures), 1)
            self.assertEqual(len(reloaded.successful_fixes), 1)
            self.assertEqual(len(reloaded.repository_summaries), 1)
            self.assertEqual(len(recall.tasks), 1)
            self.assertEqual(len(recall.failures), 1)
            self.assertEqual(len(recall.successful_fixes), 1)
            self.assertEqual(len(recall.repository_summaries), 1)
        finally:
            store_path.unlink(missing_ok=True)


class CheckpointStoreTestCase(unittest.TestCase):
    def test_checkpoint_round_trips_saved_stage_and_attempts(self) -> None:
        store_path = REPO_ROOT / ".tmp_orchestration_checkpoint.json"
        store = OrchestrationCheckpointStore(store_path)
        plan = ExecutionPlan(
            objective="Fix the test",
            target_files=(Path("app_pkg/core.py"),),
            steps=(
                PlanStep(
                    target_file=Path("app_pkg/core.py"),
                    rationale="Exercise resume support.",
                    expected_modifications=("Inspect answer()",),
                    risks=("Mock risk",),
                    confidence=0.5,
                ),
            ),
            overall_confidence=0.5,
            created_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )
        test_result = TestRunResult(
            runner="pytest",
            exit_code=1,
            success=False,
            stdout="",
            stderr="",
            command=("pytest", "-q"),
            cwd=AUTONOMY_REPO,
            cases=(
                TestCaseResult(
                    nodeid="tests.test_core::test_answer",
                    outcome="failed",
                    file="tests/test_core.py",
                    line=5,
                    duration=0.1,
                    message="AssertionError: assert 41 == 42",
                    failure_type="AssertionError",
                ),
            ),
            analysis=None,
            failure_summary=None,
        )
        failure_summary = FailureSummary(
            total_failures=1,
            root_causes=(
                FailureCauseSummary(
                    root_cause="assertion_mismatch",
                    summary="An assertion failed, indicating the observed value did not match the expected behavior.",
                    count=1,
                    confidence=1.0,
                    test_names=("tests.test_core::test_answer",),
                    failure_types=("AssertionError",),
                    details=("AssertionError: assert 41 == 42",),
                ),
            ),
            failures=(
                FailureAnalysis(
                    test_name="tests.test_core::test_answer",
                    failure_type="AssertionError",
                    root_cause="assertion_mismatch",
                    summary="An assertion failed, indicating the observed value did not match the expected behavior.",
                    detail="AssertionError: assert 41 == 42",
                ),
            ),
        )
        attempt = AutonomousAttempt(
            attempt_number=1,
            repository_scanned_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
            test_result=test_result,
            failure_summary=failure_summary,
            plan=plan,
            proposed_edits=(),
            applied_paths=(),
            status="edited",
            note="Saved for resume testing.",
        )

        try:
            checkpoint = store.new(
                objective="Fix the test",
                retry_limit=1,
                attempts=(attempt,),
                stage="tests_completed",
                attempt_number=1,
                current_plan=plan,
                current_test_result=test_result,
                current_failure_summary=failure_summary,
            )
            store.save(checkpoint)

            reloaded = store.load()

            self.assertIsNotNone(reloaded)
            assert reloaded is not None
            self.assertEqual(reloaded.stage, "tests_completed")
            self.assertEqual(reloaded.attempt_number, 1)
            self.assertEqual(len(reloaded.attempts), 1)
            self.assertEqual(reloaded.current_plan.objective, "Fix the test")
            self.assertFalse(reloaded.current_test_result.success)
            self.assertEqual(reloaded.current_failure_summary.total_failures, 1)
        finally:
            store_path.unlink(missing_ok=True)


class GitWorkspaceTestCase(unittest.TestCase):
    def test_creates_temporary_branch_and_rolls_back(self) -> None:
        repo_dir = REPO_ROOT / ".tmp_git_workspace_repo"
        if repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)
        repo_dir.mkdir(parents=True, exist_ok=True)

        def run_git(*args: str) -> subprocess.CompletedProcess[str]:
            env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "Codex",
                "GIT_AUTHOR_EMAIL": "codex@example.com",
                "GIT_COMMITTER_NAME": "Codex",
                "GIT_COMMITTER_EMAIL": "codex@example.com",
            }
            return subprocess.run(
                ["git", "-C", str(repo_dir), *args],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )

        try:
            run_git("init")
            (repo_dir / "app.py").write_text("value = 1\n", encoding="utf-8")
            run_git("add", "app.py")
            run_git("commit", "-m", "initial commit")
            original_head = run_git("rev-parse", "HEAD").stdout.strip()

            manager = GitWorkspaceManager(repo_dir)
            state = manager.prepare()
            self.assertIsNotNone(state)
            assert state is not None
            self.assertIsNotNone(state.temporary_branch)
            self.assertEqual(run_git("branch", "--show-current").stdout.strip(), state.temporary_branch)

            (repo_dir / "app.py").write_text("value = 2\n", encoding="utf-8")
            self.assertTrue(manager.rollback())

            self.assertEqual(run_git("rev-parse", "HEAD").stdout.strip(), original_head)
            self.assertEqual((repo_dir / "app.py").read_text(encoding="utf-8"), "value = 1\n")
        finally:
            shutil.rmtree(repo_dir, ignore_errors=True)


class OrchestratorTestCase(unittest.TestCase):
    def test_orchestrator_records_memory_and_progress(self) -> None:
        core_path = AUTONOMY_REPO / "app_pkg" / "core.py"
        baseline_text = "def answer() -> int:\n    return 41\n"
        core_path.write_text(baseline_text, encoding="utf-8")

        memory_store_path = REPO_ROOT / ".tmp_orchestrator_memory.json"
        checkpoint_path = REPO_ROOT / ".tmp_orchestrator_run_state.json"
        memory_store = PersistentMemoryStore(memory_store_path)
        checkpoint_store = OrchestrationCheckpointStore(checkpoint_path)
        progress_events: list[dict[str, object]] = []

        def reporter(event) -> None:
            progress_events.append(event.to_dict())

        def strategy(context):
            self.assertIsNotNone(context.memory_recall)
            return (
                SymbolEdit(
                    path=Path("app_pkg/core.py"),
                    symbol_name="answer",
                    qualified_name="answer",
                    replacement_text="def answer() -> int:\n    return 42\n",
                ),
            )

        try:
            checkpoint_store.save(
                checkpoint_store.new(
                    objective="Make the test suite pass",
                    retry_limit=1,
                    attempts=(),
                    stage="tests_completed",
                    attempt_number=1,
                    current_plan=ExecutionPlan(
                        objective="Make the test suite pass",
                        target_files=(Path("app_pkg/core.py"),),
                        steps=(),
                        overall_confidence=0.0,
                        created_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
                    ),
                    current_test_result=TestRunResult(
                        runner="pytest",
                        exit_code=1,
                        success=False,
                        stdout="",
                        stderr="",
                        command=("pytest", "-q"),
                        cwd=AUTONOMY_REPO,
                        cases=(),
                    ),
                    current_failure_summary=FailureSummary(
                        total_failures=1,
                        root_causes=(),
                        failures=(),
                    ),
                )
            )
            repo = LocalRepository(AUTONOMY_REPO)
            orchestrator = AutonomousOrchestrator(
                repo,
                retry_limit=1,
                edit_strategy=strategy,
                memory_store=memory_store,
                checkpoint_store=checkpoint_store,
                progress_reporter=reporter,
            )
            result = orchestrator.run("Make the test suite pass", retry_limit=1)

            self.assertTrue(result.succeeded)
            self.assertEqual(result.stop_reason, "tests_passed")
            self.assertEqual(len(result.attempts), 2)

            memory_state = memory_store.load()
            self.assertEqual(len(memory_state.tasks), 1)
            self.assertGreaterEqual(len(memory_state.failures), 1)
            self.assertEqual(len(memory_state.successful_fixes), 1)
            self.assertGreaterEqual(len(memory_state.repository_summaries), 1)

            stages = [event["stage"] for event in progress_events]
            self.assertIn("resumed", stages)
            self.assertIn("plan_created", stages)
            self.assertIn("tests_completed", stages)
            self.assertIn("edits_applied", stages)
            self.assertIn("resumed", stages)
            self.assertIn("completed", stages)
            self.assertFalse(checkpoint_path.exists())
        finally:
            core_path.write_text(baseline_text, encoding="utf-8")
            memory_store_path.unlink(missing_ok=True)
            checkpoint_path.unlink(missing_ok=True)
