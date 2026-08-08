"""Persistent orchestration checkpoints for resuming interrupted runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator import AutonomousAttempt

from .memory import MemoryRecall
from .planning import ExecutionPlan
from .tester import FailureSummary, TestRunResult


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class OrchestrationCheckpoint:
    """Serializable execution snapshot for interrupted runs."""

    run_id: str
    objective: str
    retry_limit: int
    stage: str
    attempt_number: int
    attempts: tuple[Any, ...] = ()
    current_plan: ExecutionPlan | None = None
    current_test_result: TestRunResult | None = None
    current_failure_summary: FailureSummary | None = None
    memory_recall: MemoryRecall | None = None
    stop_reason: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "objective": self.objective,
            "retry_limit": self.retry_limit,
            "stage": self.stage,
            "attempt_number": self.attempt_number,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "current_plan": self.current_plan.to_dict() if self.current_plan is not None else None,
            "current_test_result": self.current_test_result.to_dict() if self.current_test_result is not None else None,
            "current_failure_summary": self.current_failure_summary.to_dict() if self.current_failure_summary is not None else None,
            "memory_recall": self.memory_recall.to_dict() if self.memory_recall is not None else None,
            "stop_reason": self.stop_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "OrchestrationCheckpoint":
        return cls(
            run_id=str(payload.get("run_id", uuid4().hex)),
            objective=str(payload.get("objective", "")),
            retry_limit=int(payload.get("retry_limit", 0)),
            stage=str(payload.get("stage", "started")),
            attempt_number=int(payload.get("attempt_number", 1)),
            attempts=tuple(_load_attempt(item) for item in payload.get("attempts", ())),
            current_plan=ExecutionPlan.from_dict(payload["current_plan"]) if payload.get("current_plan") else None,
            current_test_result=TestRunResult.from_dict(payload["current_test_result"]) if payload.get("current_test_result") else None,
            current_failure_summary=FailureSummary.from_dict(payload["current_failure_summary"]) if payload.get("current_failure_summary") else None,
            memory_recall=MemoryRecall.from_dict(payload["memory_recall"]) if payload.get("memory_recall") else None,
            stop_reason=payload.get("stop_reason") if payload.get("stop_reason") is None else str(payload.get("stop_reason")),
            created_at=datetime.fromisoformat(str(payload.get("created_at", _now().isoformat()))),
            updated_at=datetime.fromisoformat(str(payload.get("updated_at", _now().isoformat()))),
        )


class OrchestrationCheckpointStore:
    """Read and write orchestration checkpoints."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    def load(self) -> OrchestrationCheckpoint | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return OrchestrationCheckpoint.from_dict(payload)

    def save(self, checkpoint: OrchestrationCheckpoint) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(checkpoint.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    def new(
        self,
        *,
        objective: str,
        retry_limit: int,
        attempts: tuple[Any, ...] = (),
        stage: str = "started",
        attempt_number: int = 1,
        current_plan: ExecutionPlan | None = None,
        current_test_result: TestRunResult | None = None,
        current_failure_summary: FailureSummary | None = None,
        memory_recall: MemoryRecall | None = None,
        stop_reason: str | None = None,
        run_id: str | None = None,
    ) -> OrchestrationCheckpoint:
        now = _now()
        return OrchestrationCheckpoint(
            run_id=run_id or uuid4().hex,
            objective=objective,
            retry_limit=retry_limit,
            stage=stage,
            attempt_number=attempt_number,
            attempts=attempts,
            current_plan=current_plan,
            current_test_result=current_test_result,
            current_failure_summary=current_failure_summary,
            memory_recall=memory_recall,
            stop_reason=stop_reason,
            created_at=now,
            updated_at=now,
        )


def _load_attempt(payload: dict[str, object]) -> Any:
    from .orchestrator import AutonomousAttempt

    return AutonomousAttempt.from_dict(payload)
