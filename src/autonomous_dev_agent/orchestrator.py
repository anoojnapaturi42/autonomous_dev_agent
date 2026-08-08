"""Central orchestration for planning, editing, testing, and memory reuse."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, Sequence

from .editing import EditPreview, EditRequest, EditResult, SafeEditingEngine
from .checkpoint import OrchestrationCheckpoint, OrchestrationCheckpointStore
from .memory import (
    FailureMemoryRecord,
    MemoryRecall,
    PersistentMemoryStore,
    RepositorySummaryRecord,
    SuccessfulFixRecord,
    TaskMemoryRecord,
)
from .planning import ExecutionPlan, PlanningModule
from .repository import Repository
from .scanner import RepositoryScanner
from .symbol_index import RepositoryIndex
from .workspace import GitWorkspaceManager, GitWorkspaceState
from .tester import FailureSummary, PytestTestRunner, TestRunResult


class EditStrategy(Protocol):
    """Callable interface for proposing edits after a failed test run."""

    def __call__(self, context: "AutonomousEditContext") -> Sequence[EditRequest]:
        """Return the edits to attempt for the current failure context."""


class ProgressReporter(Protocol):
    """Callback interface for structured orchestration progress events."""

    def __call__(self, event: "OrchestrationProgressEvent") -> None:
        """Handle a single progress event."""


@dataclass(frozen=True, slots=True)
class OrchestrationProgressEvent:
    """Structured progress information emitted by the orchestrator."""

    stage: str
    message: str
    attempt_number: int | None = None
    details: dict[str, object] = field(default_factory=dict)
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "message": self.message,
            "attempt_number": self.attempt_number,
            "details": self.details,
            "recorded_at": self.recorded_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class AutonomousEditContext:
    """Structured context passed into the edit strategy."""

    objective: str
    attempt_number: int
    retry_limit: int
    repository_index: RepositoryIndex
    test_result: TestRunResult
    failure_summary: FailureSummary
    plan: ExecutionPlan
    memory_recall: MemoryRecall | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "objective": self.objective,
            "attempt_number": self.attempt_number,
            "retry_limit": self.retry_limit,
            "repository_index": {
                "root": self.repository_index.root.as_posix(),
                "scanned_at": self.repository_index.scanned_at.isoformat(),
            },
            "test_result": self.test_result.to_dict(),
            "failure_summary": self.failure_summary.to_dict(),
            "plan": self.plan.to_dict(),
            "memory_recall": self.memory_recall.to_dict() if self.memory_recall is not None else None,
        }


@dataclass(frozen=True, slots=True)
class AutonomousAttempt:
    """A single test-analyze-edit cycle."""

    attempt_number: int
    repository_scanned_at: datetime
    test_result: TestRunResult
    failure_summary: FailureSummary
    plan: ExecutionPlan
    proposed_edits: tuple[EditPreview, ...]
    applied_paths: tuple[Path, ...]
    status: str
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt_number": self.attempt_number,
            "repository_scanned_at": self.repository_scanned_at.isoformat(),
            "test_result": self.test_result.to_dict(),
            "failure_summary": self.failure_summary.to_dict(),
            "plan": self.plan.to_dict(),
            "proposed_edits": [preview.to_dict() for preview in self.proposed_edits],
            "applied_paths": [path.as_posix() for path in self.applied_paths],
            "status": self.status,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "AutonomousAttempt":
        return cls(
            attempt_number=int(payload.get("attempt_number", 0)),
            repository_scanned_at=datetime.fromisoformat(str(payload.get("repository_scanned_at", datetime.now(timezone.utc).isoformat()))),
            test_result=TestRunResult.from_dict(payload["test_result"]) if payload.get("test_result") else TestRunResult(
                runner="unknown",
                exit_code=0,
                success=True,
                stdout="",
                stderr="",
                command=(),
                cwd=Path("."),
            ),
            failure_summary=FailureSummary.from_dict(payload["failure_summary"]) if payload.get("failure_summary") else FailureSummary(
                total_failures=0,
                root_causes=(),
                failures=(),
            ),
            plan=ExecutionPlan.from_dict(payload["plan"]) if payload.get("plan") else ExecutionPlan(
                objective="",
                target_files=(),
                steps=(),
                overall_confidence=0.0,
                created_at=datetime.now(timezone.utc),
            ),
            proposed_edits=tuple(
                EditPreview.from_dict(item) for item in payload.get("proposed_edits", ())
            ),
            applied_paths=tuple(Path(str(item)) for item in payload.get("applied_paths", ())),
            status=str(payload.get("status", "unknown")),
            note=payload.get("note") if payload.get("note") is None else str(payload.get("note")),
        )


@dataclass(frozen=True, slots=True)
class AutonomousRunResult:
    """Structured output from the autonomous engineer loop."""

    objective: str
    retry_limit: int
    succeeded: bool
    stop_reason: str
    attempts: tuple[AutonomousAttempt, ...]
    final_test_result: TestRunResult
    final_failure_summary: FailureSummary
    memory_recall: MemoryRecall | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "objective": self.objective,
            "retry_limit": self.retry_limit,
            "succeeded": self.succeeded,
            "stop_reason": self.stop_reason,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "final_test_result": self.final_test_result.to_dict(),
            "final_failure_summary": self.final_failure_summary.to_dict(),
            "memory_recall": self.memory_recall.to_dict() if self.memory_recall is not None else None,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "AutonomousRunResult":
        return cls(
            objective=str(payload.get("objective", "")),
            retry_limit=int(payload.get("retry_limit", 0)),
            succeeded=bool(payload.get("succeeded", False)),
            stop_reason=str(payload.get("stop_reason", "unknown")),
            attempts=tuple(AutonomousAttempt.from_dict(item) for item in payload.get("attempts", ())),
            final_test_result=TestRunResult.from_dict(payload["final_test_result"]) if payload.get("final_test_result") else TestRunResult(
                runner="unknown",
                exit_code=0,
                success=True,
                stdout="",
                stderr="",
                command=(),
                cwd=Path("."),
            ),
            final_failure_summary=FailureSummary.from_dict(payload["final_failure_summary"]) if payload.get("final_failure_summary") else FailureSummary(
                total_failures=0,
                root_causes=(),
                failures=(),
            ),
            memory_recall=MemoryRecall.from_dict(payload["memory_recall"]) if payload.get("memory_recall") else None,
        )


class AutonomousOrchestrator:
    """Coordinate planning, testing, editing, retries, logging, and memory."""

    def __init__(
        self,
        repository: Repository,
        *,
        retry_limit: int = 2,
        edit_strategy: EditStrategy | None = None,
        scanner: RepositoryScanner | None = None,
        tester: PytestTestRunner | None = None,
        memory_store: PersistentMemoryStore | None = None,
        checkpoint_store: OrchestrationCheckpointStore | None = None,
        workspace_manager: GitWorkspaceManager | None = None,
        progress_reporter: ProgressReporter | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._repository = repository
        self._retry_limit = retry_limit
        self._edit_strategy = edit_strategy
        self._scanner = scanner or RepositoryScanner(repository)
        self._tester = tester or PytestTestRunner(repository.root)
        self._memory_store = memory_store or PersistentMemoryStore(
            repository.root / ".autonomous_dev_agent" / "memory.json"
        )
        self._checkpoint_store = checkpoint_store or OrchestrationCheckpointStore(
            repository.root / ".autonomous_dev_agent" / "run_state.json"
        )
        self._workspace_manager = workspace_manager or GitWorkspaceManager(repository.root)
        self._progress_reporter = progress_reporter
        self._logger = logger or logging.getLogger(__name__)

    def run(
        self,
        objective: str,
        *,
        retry_limit: int | None = None,
        top_k: int = 5,
        edit_strategy: EditStrategy | None = None,
    ) -> AutonomousRunResult:
        active_retry_limit = self._retry_limit if retry_limit is None else retry_limit
        memory_recall = self._memory_store.recall(objective, self._repository.root)
        workspace_state = self._workspace_manager.prepare()
        if workspace_state is not None:
            self._emit(
                "workspace_prepared",
                "Git workspace prepared for autonomous edits.",
                details={
                    "temporary_branch": workspace_state.temporary_branch,
                    "original_branch": workspace_state.original_branch,
                    "original_head": workspace_state.original_head,
                },
            )

        checkpoint = self._checkpoint_store.load()
        attempts: list[AutonomousAttempt]
        start_attempt_number = 1
        if (
            checkpoint is not None
            and checkpoint.objective == objective
            and checkpoint.retry_limit == active_retry_limit
        ):
            attempts = list(checkpoint.attempts)
            start_attempt_number = checkpoint.attempt_number + (1 if checkpoint.stage == "edits_applied" else 0)
            memory_recall = checkpoint.memory_recall or memory_recall
            self._emit(
                "resumed",
                "Resuming from a saved orchestration checkpoint.",
                details={
                    "stage": checkpoint.stage,
                    "attempt_number": checkpoint.attempt_number,
                    "attempts": len(attempts),
                },
            )
        else:
            attempts = []
            checkpoint = self._checkpoint_store.new(
                objective=objective,
                retry_limit=active_retry_limit,
                attempts=(),
                stage="started",
                attempt_number=1,
                memory_recall=memory_recall,
            )
            self._checkpoint_store.save(checkpoint)
            self._emit(
                "started",
                "Starting autonomous orchestration run.",
                details={
                    "objective": objective,
                    "retry_limit": active_retry_limit,
                    "memory_task_matches": len(memory_recall.tasks),
                    "memory_fix_matches": len(memory_recall.successful_fixes),
                    "memory_failure_matches": len(memory_recall.failures),
                    "memory_repository_matches": len(memory_recall.repository_summaries),
                },
            )

        final_test_result: TestRunResult | None = None
        final_failure_summary: FailureSummary | None = None
        final_repository_index: RepositoryIndex | None = None
        stop_reason = checkpoint.stop_reason if checkpoint is not None and checkpoint.stop_reason else "retry_limit_reached"

        for attempt_number in range(start_attempt_number, active_retry_limit + 2):
            repository_index = self._scanner.scan()
            final_repository_index = repository_index
            self._record_repository_summary(repository_index)
            self._checkpoint_store.save(
                self._checkpoint_store.new(
                    objective=objective,
                    retry_limit=active_retry_limit,
                    attempts=tuple(attempts),
                    stage="repository_scanned",
                    attempt_number=attempt_number,
                    memory_recall=memory_recall,
                    stop_reason=stop_reason,
                )
            )
            self._emit(
                "repository_scanned",
                "Repository scan completed.",
                attempt_number=attempt_number,
                details={
                    "python_files": len(repository_index.python_files),
                    "symbols": len(repository_index.symbol_index.symbols),
                    "scanned_at": repository_index.scanned_at.isoformat(),
                },
            )

            planner = PlanningModule(repository_index)
            plan = planner.draft_execution_plan(objective, top_k=top_k)
            self._checkpoint_store.save(
                self._checkpoint_store.new(
                    objective=objective,
                    retry_limit=active_retry_limit,
                    attempts=tuple(attempts),
                    stage="plan_created",
                    attempt_number=attempt_number,
                    current_plan=plan,
                    memory_recall=memory_recall,
                    stop_reason=stop_reason,
                )
            )
            self._emit(
                "plan_created",
                "Planning pass completed.",
                attempt_number=attempt_number,
                details={
                    "target_files": [path.as_posix() for path in plan.target_files],
                    "overall_confidence": plan.overall_confidence,
                },
            )

            test_result = self._tester.run()
            failure_summary = self._tester.summarize(test_result)
            final_test_result = test_result
            final_failure_summary = failure_summary
            self._checkpoint_store.save(
                self._checkpoint_store.new(
                    objective=objective,
                    retry_limit=active_retry_limit,
                    attempts=tuple(attempts),
                    stage="tests_completed",
                    attempt_number=attempt_number,
                    current_plan=plan,
                    current_test_result=test_result,
                    current_failure_summary=failure_summary,
                    memory_recall=memory_recall,
                    stop_reason=stop_reason,
                )
            )
            self._emit(
                "tests_completed",
                "Repository tests completed.",
                attempt_number=attempt_number,
                details={
                    "success": test_result.success,
                    "exit_code": test_result.exit_code,
                    "failures": failure_summary.total_failures,
                },
            )

            if not test_result.success:
                self._record_failures(objective, attempt_number, failure_summary)
                self._checkpoint_store.save(
                    self._checkpoint_store.new(
                        objective=objective,
                        retry_limit=active_retry_limit,
                        attempts=tuple(attempts),
                        stage="failures_summarized",
                        attempt_number=attempt_number,
                        current_plan=plan,
                        current_test_result=test_result,
                        current_failure_summary=failure_summary,
                        memory_recall=memory_recall,
                        stop_reason=stop_reason,
                    )
                )
                self._emit(
                    "failures_summarized",
                    "Structured failure analysis is available.",
                    attempt_number=attempt_number,
                    details={
                        "root_causes": [cause.root_cause for cause in failure_summary.root_causes],
                    },
                )

            if test_result.success:
                attempts.append(
                    AutonomousAttempt(
                        attempt_number=attempt_number,
                        repository_scanned_at=repository_index.scanned_at,
                        test_result=test_result,
                        failure_summary=failure_summary,
                        plan=plan,
                        proposed_edits=(),
                        applied_paths=(),
                        status="passed",
                        note="Repository tests passed.",
                    )
                )
                stop_reason = "tests_passed"
                break

            if attempt_number > active_retry_limit:
                attempts.append(
                    AutonomousAttempt(
                        attempt_number=attempt_number,
                        repository_scanned_at=repository_index.scanned_at,
                        test_result=test_result,
                        failure_summary=failure_summary,
                        plan=plan,
                        proposed_edits=(),
                        applied_paths=(),
                        status="retry_limit_reached",
                        note="Reached the configured retry limit before applying another edit.",
                    )
                )
                stop_reason = "retry_limit_reached"
                break

            strategy = edit_strategy or self._edit_strategy
            if strategy is None:
                attempts.append(
                    AutonomousAttempt(
                        attempt_number=attempt_number,
                        repository_scanned_at=repository_index.scanned_at,
                        test_result=test_result,
                        failure_summary=failure_summary,
                        plan=plan,
                        proposed_edits=(),
                        applied_paths=(),
                        status="no_edit_strategy",
                        note="No edit strategy was provided, so the loop could not repair the failure.",
                    )
                )
                stop_reason = "no_edit_strategy"
                break

            context = AutonomousEditContext(
                objective=objective,
                attempt_number=attempt_number,
                retry_limit=active_retry_limit,
                repository_index=repository_index,
                test_result=test_result,
                failure_summary=failure_summary,
                plan=plan,
                memory_recall=memory_recall,
            )
            edits = tuple(strategy(context))
            self._checkpoint_store.save(
                self._checkpoint_store.new(
                    objective=objective,
                    retry_limit=active_retry_limit,
                    attempts=tuple(attempts),
                    stage="edits_proposed",
                    attempt_number=attempt_number,
                    current_plan=plan,
                    current_test_result=test_result,
                    current_failure_summary=failure_summary,
                    memory_recall=memory_recall,
                    stop_reason=stop_reason,
                )
            )
            self._emit(
                "edits_proposed",
                "Edit strategy returned candidate modifications.",
                attempt_number=attempt_number,
                details={"edit_count": len(edits)},
            )
            if not edits:
                attempts.append(
                    AutonomousAttempt(
                        attempt_number=attempt_number,
                        repository_scanned_at=repository_index.scanned_at,
                        test_result=test_result,
                        failure_summary=failure_summary,
                        plan=plan,
                        proposed_edits=(),
                        applied_paths=(),
                        status="no_edits_proposed",
                        note="The edit strategy declined to make a change.",
                    )
                )
                stop_reason = "no_edits_proposed"
                break

            editor = SafeEditingEngine(self._repository, repository_index=repository_index)
            previews = editor.preview(edits)
            self._checkpoint_store.save(
                self._checkpoint_store.new(
                    objective=objective,
                    retry_limit=active_retry_limit,
                    attempts=tuple(attempts),
                    stage="edits_previewed",
                    attempt_number=attempt_number,
                    current_plan=plan,
                    current_test_result=test_result,
                    current_failure_summary=failure_summary,
                    memory_recall=memory_recall,
                    stop_reason=stop_reason,
                )
            )
            self._emit(
                "edits_previewed",
                "Generated unified diffs for proposed edits.",
                attempt_number=attempt_number,
                details={"preview_count": len(previews)},
            )
            try:
                edit_result: EditResult = editor.apply(edits)
            except Exception as exc:  # pragma: no cover - defensive stop path
                attempts.append(
                    AutonomousAttempt(
                        attempt_number=attempt_number,
                        repository_scanned_at=repository_index.scanned_at,
                        test_result=test_result,
                        failure_summary=failure_summary,
                        plan=plan,
                        proposed_edits=previews,
                        applied_paths=(),
                        status="edit_failed",
                        note=str(exc),
                    )
                )
                stop_reason = "edit_failed"
                self._checkpoint_store.save(
                    self._checkpoint_store.new(
                        objective=objective,
                        retry_limit=active_retry_limit,
                        attempts=tuple(attempts),
                        stage="edit_failed",
                        attempt_number=attempt_number,
                        current_plan=plan,
                        current_test_result=test_result,
                        current_failure_summary=failure_summary,
                        memory_recall=memory_recall,
                        stop_reason=stop_reason,
                    )
                )
                self._emit(
                    "edit_failed",
                    "The edit engine rejected the proposed changes.",
                    attempt_number=attempt_number,
                    details={"error": str(exc)},
                )
                break

            attempts.append(
                AutonomousAttempt(
                    attempt_number=attempt_number,
                    repository_scanned_at=repository_index.scanned_at,
                    test_result=test_result,
                    failure_summary=failure_summary,
                    plan=plan,
                    proposed_edits=previews,
                    applied_paths=edit_result.written_paths,
                    status="edited",
                    note="Applied proposed edits and scheduled another test run.",
                )
            )
            self._checkpoint_store.save(
                self._checkpoint_store.new(
                    objective=objective,
                    retry_limit=active_retry_limit,
                    attempts=tuple(attempts),
                    stage="edits_applied",
                    attempt_number=attempt_number,
                    current_plan=plan,
                    current_test_result=test_result,
                    current_failure_summary=failure_summary,
                    memory_recall=memory_recall,
                    stop_reason=stop_reason,
                )
            )
            self._emit(
                "edits_applied",
                "Applied proposed edits.",
                attempt_number=attempt_number,
                details={"applied_paths": [path.as_posix() for path in edit_result.written_paths]},
            )

        if final_test_result is None or final_failure_summary is None:
            final_repository_index = final_repository_index or self._scanner.scan()
            final_plan = PlanningModule(final_repository_index).draft_execution_plan(objective, top_k=top_k)
            final_result = self._tester.run()
            final_summary = self._tester.summarize(final_result)
            attempts.append(
                AutonomousAttempt(
                    attempt_number=1,
                    repository_scanned_at=final_repository_index.scanned_at,
                    test_result=final_result,
                    failure_summary=final_summary,
                    plan=final_plan,
                    proposed_edits=(),
                    applied_paths=(),
                    status="no_result",
                    note="The autonomous loop did not produce a run result.",
                )
            )
            final_test_result = final_result
            final_failure_summary = final_summary

        self._persist_memory(
            objective=objective,
            retry_limit=active_retry_limit,
            attempts=attempts,
            final_test_result=final_test_result,
            final_failure_summary=final_failure_summary,
            repository_index=final_repository_index,
            memory_recall=memory_recall,
            stop_reason=stop_reason,
        )

        result = AutonomousRunResult(
            objective=objective,
            retry_limit=active_retry_limit,
            succeeded=final_test_result.success if final_test_result else False,
            stop_reason=stop_reason,
            attempts=tuple(attempts),
            final_test_result=final_test_result,
            final_failure_summary=final_failure_summary,
            memory_recall=memory_recall,
        )
        self._checkpoint_store.clear()
        self._emit(
            "completed",
            "Autonomous orchestration run completed.",
            details={
                "succeeded": result.succeeded,
                "stop_reason": result.stop_reason,
                "attempt_count": len(result.attempts),
            },
        )
        return result

    def _persist_memory(
        self,
        *,
        objective: str,
        retry_limit: int,
        attempts: Sequence[AutonomousAttempt],
        final_test_result: TestRunResult,
        final_failure_summary: FailureSummary,
        repository_index: RepositoryIndex | None,
        memory_recall: MemoryRecall,
        stop_reason: str,
    ) -> None:
        try:
            self._memory_store.record_task(
                TaskMemoryRecord(
                    objective=objective,
                    repository_root=self._repository.root.as_posix(),
                    retry_limit=retry_limit,
                    succeeded=final_test_result.success,
                    stop_reason=stop_reason,
                    attempt_count=len(attempts),
                    recorded_at=datetime.now(timezone.utc),
                )
            )
            if repository_index is not None:
                self._record_repository_summary(repository_index)
            if final_test_result.success:
                fixed_attempt = next((attempt for attempt in reversed(attempts) if attempt.status == "edited"), None)
                if fixed_attempt is not None:
                    self._memory_store.record_successful_fix(
                        SuccessfulFixRecord(
                            objective=objective,
                            repository_root=self._repository.root.as_posix(),
                            summary=_success_summary(final_failure_summary),
                            fixed_paths=tuple(path.as_posix() for path in fixed_attempt.applied_paths),
                            root_causes=tuple(cause.root_cause for cause in final_failure_summary.root_causes),
                            test_summary=_test_summary(final_test_result),
                            recorded_at=datetime.now(timezone.utc),
                        )
                    )
        except OSError as exc:  # pragma: no cover - persistence failures are logged, not fatal
            self._logger.warning("Failed to persist orchestration memory: %s", exc)
            self._emit(
                "memory_persistence_failed",
                "Orchestration memory could not be saved.",
                details={"error": str(exc)},
            )

    def _record_failures(
        self,
        objective: str,
        attempt_number: int,
        failure_summary: FailureSummary,
    ) -> None:
        for failure in failure_summary.failures:
            self._memory_store.record_failure(
                FailureMemoryRecord(
                    objective=objective,
                    repository_root=self._repository.root.as_posix(),
                    test_name=failure.test_name,
                    failure_type=failure.failure_type,
                    root_cause=failure.root_cause,
                    summary=failure.summary,
                    detail=failure.detail,
                    attempt_number=attempt_number,
                    recorded_at=datetime.now(timezone.utc),
                )
            )

    def _record_repository_summary(self, repository_index: RepositoryIndex) -> None:
        top_files = tuple(path.as_posix() for path in (file_index.path for file_index in repository_index.python_files[:5]))
        summary = (
            f"Indexed {len(repository_index.python_files)} Python files and "
            f"{len(repository_index.symbol_index.symbols)} symbols."
        )
        self._memory_store.record_repository_summary(
            RepositorySummaryRecord(
                repository_root=self._repository.root.as_posix(),
                summary=summary,
                python_file_count=len(repository_index.python_files),
                symbol_count=len(repository_index.symbol_index.symbols),
                top_files=top_files,
                recorded_at=datetime.now(timezone.utc),
            )
        )

    def _emit(
        self,
        stage: str,
        message: str,
        *,
        attempt_number: int | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        event = OrchestrationProgressEvent(
            stage=stage,
            message=message,
            attempt_number=attempt_number,
            details=details or {},
        )
        self._logger.info("orchestration_event=%s", json.dumps(event.to_dict(), sort_keys=True))
        if self._progress_reporter is not None:
            try:
                self._progress_reporter(event)
            except Exception as exc:  # pragma: no cover - progress hooks should not break runs
                self._logger.warning("Progress reporter failed: %s", exc)

    def rollback_workspace(self) -> bool:
        """Restore the original repository checkout if a temporary branch was prepared."""

        rolled_back = self._workspace_manager.rollback()
        if rolled_back:
            self._checkpoint_store.clear()
            self._emit(
                "workspace_rolled_back",
                "Restored the original repository state.",
                details={"repository_root": self._repository.root.as_posix()},
            )
        return rolled_back


def _success_summary(failure_summary: FailureSummary) -> str:
    if not failure_summary.root_causes:
        return "The repository tests passed after applying the planned edits."
    root_causes = ", ".join(cause.root_cause for cause in failure_summary.root_causes)
    return f"Resolved prior failure root causes: {root_causes}."


def _test_summary(result: TestRunResult) -> str:
    total = len(result.cases)
    passed = sum(1 for case in result.cases if case.outcome == "passed")
    failed = sum(1 for case in result.cases if case.outcome == "failed")
    errors = sum(1 for case in result.cases if case.outcome == "error")
    skipped = sum(1 for case in result.cases if case.outcome == "skipped")
    if total == 0:
        return f"{result.runner} completed with exit code {result.exit_code}."
    return f"{passed} passed, {failed} failed, {errors} errors, {skipped} skipped across {total} cases."
