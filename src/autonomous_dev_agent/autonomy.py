"""Autonomous edit-test-analyze-retry loop for repository repair."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, Sequence

from .editing import EditPreview, EditRequest, EditResult, SafeEditingEngine
from .planning import ExecutionPlan, PlanningModule
from .repository import Repository
from .scanner import RepositoryScanner
from .symbol_index import RepositoryIndex
from .tester import FailureSummary, PytestTestRunner, TestRunResult


class EditStrategy(Protocol):
    """Callable interface for proposing edits after a failed test run."""

    def __call__(self, context: "AutonomousEditContext") -> Sequence[EditRequest]:
        """Return the edits to attempt for the current failure context."""


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

    def to_dict(self) -> dict[str, object]:
        return {
            "objective": self.objective,
            "retry_limit": self.retry_limit,
            "succeeded": self.succeeded,
            "stop_reason": self.stop_reason,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "final_test_result": self.final_test_result.to_dict(),
            "final_failure_summary": self.final_failure_summary.to_dict(),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


class AutonomousEngineer:
    """Run an edit-test-analyze-retry loop against a repository."""

    def __init__(
        self,
        repository: Repository,
        *,
        retry_limit: int = 2,
        edit_strategy: EditStrategy | None = None,
        scanner: RepositoryScanner | None = None,
        tester: PytestTestRunner | None = None,
    ) -> None:
        self._repository = repository
        self._retry_limit = retry_limit
        self._edit_strategy = edit_strategy
        self._scanner = scanner or RepositoryScanner(repository)
        self._tester = tester or PytestTestRunner(repository.root)

    def run(
        self,
        objective: str,
        *,
        retry_limit: int | None = None,
        top_k: int = 5,
        edit_strategy: EditStrategy | None = None,
    ) -> AutonomousRunResult:
        active_retry_limit = self._retry_limit if retry_limit is None else retry_limit
        attempts: list[AutonomousAttempt] = []
        final_test_result: TestRunResult | None = None
        final_failure_summary: FailureSummary | None = None
        stop_reason = "retry_limit_reached"

        for attempt_number in range(1, active_retry_limit + 2):
            repository_index = self._scanner.scan()
            planner = PlanningModule(repository_index)
            plan = planner.draft_execution_plan(objective, top_k=top_k)
            test_result = self._tester.run()
            failure_summary = self._tester.summarize(test_result)
            final_test_result = test_result
            final_failure_summary = failure_summary

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
            )
            edits = tuple(strategy(context))
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

        if final_test_result is None or final_failure_summary is None:
            final_index = self._scanner.scan()
            final_plan = PlanningModule(final_index).draft_execution_plan(objective, top_k=top_k)
            final_result = self._tester.run()
            final_summary = self._tester.summarize(final_result)
            attempts.append(
                AutonomousAttempt(
                    attempt_number=1,
                    repository_scanned_at=final_index.scanned_at,
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

        return AutonomousRunResult(
            objective=objective,
            retry_limit=active_retry_limit,
            succeeded=final_test_result.success if final_test_result else False,
            stop_reason=stop_reason,
            attempts=tuple(attempts),
            final_test_result=final_test_result,
            final_failure_summary=final_failure_summary,
        )
