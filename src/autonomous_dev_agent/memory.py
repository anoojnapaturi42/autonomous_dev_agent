"""Persistent memory for reusing prior work across sessions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_MEMORY_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if token}


def _score_text(query: str, *fields: str) -> float:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    haystack = " ".join(fields).lower()
    hay_tokens = _tokenize(haystack)
    if not hay_tokens:
        return 0.0
    overlap = sum(1 for token in query_tokens if token in hay_tokens or token in haystack)
    if overlap == 0:
        return 0.0
    coverage = overlap / len(query_tokens)
    density = overlap / len(hay_tokens)
    return round((coverage * 0.7) + (density * 0.3), 3)


@dataclass(frozen=True, slots=True)
class TaskMemoryRecord:
    """A persisted summary of one orchestration task."""

    objective: str
    repository_root: str
    retry_limit: int
    succeeded: bool
    stop_reason: str
    attempt_count: int
    recorded_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "repository_root": self.repository_root,
            "retry_limit": self.retry_limit,
            "succeeded": self.succeeded,
            "stop_reason": self.stop_reason,
            "attempt_count": self.attempt_count,
            "recorded_at": _isoformat(self.recorded_at),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskMemoryRecord":
        return cls(
            objective=str(payload.get("objective", "")),
            repository_root=str(payload.get("repository_root", "")),
            retry_limit=int(payload.get("retry_limit", 0)),
            succeeded=bool(payload.get("succeeded", False)),
            stop_reason=str(payload.get("stop_reason", "unknown")),
            attempt_count=int(payload.get("attempt_count", 0)),
            recorded_at=_parse_datetime(str(payload.get("recorded_at", _isoformat(_utc_now())))),
        )


@dataclass(frozen=True, slots=True)
class SuccessfulFixRecord:
    """A persisted successful repair that can be reused later."""

    objective: str
    repository_root: str
    summary: str
    fixed_paths: tuple[str, ...]
    root_causes: tuple[str, ...]
    test_summary: str
    recorded_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "repository_root": self.repository_root,
            "summary": self.summary,
            "fixed_paths": list(self.fixed_paths),
            "root_causes": list(self.root_causes),
            "test_summary": self.test_summary,
            "recorded_at": _isoformat(self.recorded_at),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SuccessfulFixRecord":
        return cls(
            objective=str(payload.get("objective", "")),
            repository_root=str(payload.get("repository_root", "")),
            summary=str(payload.get("summary", "")),
            fixed_paths=tuple(str(item) for item in payload.get("fixed_paths", ())),
            root_causes=tuple(str(item) for item in payload.get("root_causes", ())),
            test_summary=str(payload.get("test_summary", "")),
            recorded_at=_parse_datetime(str(payload.get("recorded_at", _isoformat(_utc_now())))),
        )


@dataclass(frozen=True, slots=True)
class FailureMemoryRecord:
    """A persisted failure extracted from test analysis."""

    objective: str
    repository_root: str
    test_name: str
    failure_type: str
    root_cause: str
    summary: str
    detail: str
    attempt_number: int
    recorded_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "repository_root": self.repository_root,
            "test_name": self.test_name,
            "failure_type": self.failure_type,
            "root_cause": self.root_cause,
            "summary": self.summary,
            "detail": self.detail,
            "attempt_number": self.attempt_number,
            "recorded_at": _isoformat(self.recorded_at),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FailureMemoryRecord":
        return cls(
            objective=str(payload.get("objective", "")),
            repository_root=str(payload.get("repository_root", "")),
            test_name=str(payload.get("test_name", "")),
            failure_type=str(payload.get("failure_type", "unknown")),
            root_cause=str(payload.get("root_cause", "unknown")),
            summary=str(payload.get("summary", "")),
            detail=str(payload.get("detail", "")),
            attempt_number=int(payload.get("attempt_number", 0)),
            recorded_at=_parse_datetime(str(payload.get("recorded_at", _isoformat(_utc_now())))),
        )


@dataclass(frozen=True, slots=True)
class RepositorySummaryRecord:
    """A persisted summary of the repository state."""

    repository_root: str
    summary: str
    python_file_count: int
    symbol_count: int
    top_files: tuple[str, ...]
    recorded_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_root": self.repository_root,
            "summary": self.summary,
            "python_file_count": self.python_file_count,
            "symbol_count": self.symbol_count,
            "top_files": list(self.top_files),
            "recorded_at": _isoformat(self.recorded_at),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RepositorySummaryRecord":
        return cls(
            repository_root=str(payload.get("repository_root", "")),
            summary=str(payload.get("summary", "")),
            python_file_count=int(payload.get("python_file_count", 0)),
            symbol_count=int(payload.get("symbol_count", 0)),
            top_files=tuple(str(item) for item in payload.get("top_files", ())),
            recorded_at=_parse_datetime(str(payload.get("recorded_at", _isoformat(_utc_now())))),
        )


@dataclass(frozen=True, slots=True)
class MemoryState:
    """Full persisted memory payload."""

    tasks: tuple[TaskMemoryRecord, ...] = ()
    successful_fixes: tuple[SuccessfulFixRecord, ...] = ()
    failures: tuple[FailureMemoryRecord, ...] = ()
    repository_summaries: tuple[RepositorySummaryRecord, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": _MEMORY_VERSION,
            "tasks": [record.to_dict() for record in self.tasks],
            "successful_fixes": [record.to_dict() for record in self.successful_fixes],
            "failures": [record.to_dict() for record in self.failures],
            "repository_summaries": [record.to_dict() for record in self.repository_summaries],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryState":
        return cls(
            tasks=tuple(TaskMemoryRecord.from_dict(item) for item in payload.get("tasks", ())),
            successful_fixes=tuple(
                SuccessfulFixRecord.from_dict(item) for item in payload.get("successful_fixes", ())
            ),
            failures=tuple(FailureMemoryRecord.from_dict(item) for item in payload.get("failures", ())),
            repository_summaries=tuple(
                RepositorySummaryRecord.from_dict(item) for item in payload.get("repository_summaries", ())
            ),
        )


@dataclass(frozen=True, slots=True)
class MemoryRecall:
    """Relevant prior memory grouped for reuse during orchestration."""

    query: str
    repository_root: str
    tasks: tuple[TaskMemoryRecord, ...]
    successful_fixes: tuple[SuccessfulFixRecord, ...]
    failures: tuple[FailureMemoryRecord, ...]
    repository_summaries: tuple[RepositorySummaryRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "repository_root": self.repository_root,
            "tasks": [record.to_dict() for record in self.tasks],
            "successful_fixes": [record.to_dict() for record in self.successful_fixes],
            "failures": [record.to_dict() for record in self.failures],
            "repository_summaries": [record.to_dict() for record in self.repository_summaries],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryRecall":
        return cls(
            query=str(payload.get("query", "")),
            repository_root=str(payload.get("repository_root", "")),
            tasks=tuple(TaskMemoryRecord.from_dict(item) for item in payload.get("tasks", ())),
            successful_fixes=tuple(SuccessfulFixRecord.from_dict(item) for item in payload.get("successful_fixes", ())),
            failures=tuple(FailureMemoryRecord.from_dict(item) for item in payload.get("failures", ())),
            repository_summaries=tuple(
                RepositorySummaryRecord.from_dict(item) for item in payload.get("repository_summaries", ())
            ),
        )


class PersistentMemoryStore:
    """Load and save durable orchestration memory as JSON."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    def load(self) -> MemoryState:
        if not self.path.exists():
            return MemoryState()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return MemoryState()
        if not isinstance(payload, dict):
            return MemoryState()
        return MemoryState.from_dict(payload)

    def save(self, state: MemoryState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def record_task(self, record: TaskMemoryRecord) -> None:
        state = self.load()
        self.save(
            MemoryState(
                tasks=(*state.tasks, record),
                successful_fixes=state.successful_fixes,
                failures=state.failures,
                repository_summaries=state.repository_summaries,
            )
        )

    def record_successful_fix(self, record: SuccessfulFixRecord) -> None:
        state = self.load()
        self.save(
            MemoryState(
                tasks=state.tasks,
                successful_fixes=(*state.successful_fixes, record),
                failures=state.failures,
                repository_summaries=state.repository_summaries,
            )
        )

    def record_failure(self, record: FailureMemoryRecord) -> None:
        state = self.load()
        self.save(
            MemoryState(
                tasks=state.tasks,
                successful_fixes=state.successful_fixes,
                failures=(*state.failures, record),
                repository_summaries=state.repository_summaries,
            )
        )

    def record_repository_summary(self, record: RepositorySummaryRecord) -> None:
        state = self.load()
        self.save(
            MemoryState(
                tasks=state.tasks,
                successful_fixes=state.successful_fixes,
                failures=state.failures,
                repository_summaries=(*state.repository_summaries, record),
            )
        )

    def recall(self, query: str, repository_root: str | Path, *, limit: int = 5) -> MemoryRecall:
        state = self.load()
        repository_root_text = Path(repository_root).resolve().as_posix()

        tasks = _best_matches(
            state.tasks,
            query,
            limit,
            lambda record: " ".join(
                [record.objective, record.stop_reason, str(record.retry_limit), str(record.attempt_count)]
            ),
            repository_root_text,
            lambda record: record.repository_root,
        )
        successful_fixes = _best_matches(
            state.successful_fixes,
            query,
            limit,
            lambda record: " ".join(
                [record.objective, record.summary, record.test_summary, " ".join(record.root_causes), " ".join(record.fixed_paths)]
            ),
            repository_root_text,
            lambda record: record.repository_root,
        )
        failures = _best_matches(
            state.failures,
            query,
            limit,
            lambda record: " ".join(
                [
                    record.objective,
                    record.test_name,
                    record.failure_type,
                    record.root_cause,
                    record.summary,
                    record.detail,
                ]
            ),
            repository_root_text,
            lambda record: record.repository_root,
        )
        repository_summaries = _best_matches(
            state.repository_summaries,
            query,
            limit,
            lambda record: " ".join(
                [
                    record.repository_root,
                    record.summary,
                    str(record.python_file_count),
                    str(record.symbol_count),
                    " ".join(record.top_files),
                ]
            ),
            repository_root_text,
            lambda record: record.repository_root,
        )

        return MemoryRecall(
            query=query,
            repository_root=repository_root_text,
            tasks=tasks,
            successful_fixes=successful_fixes,
            failures=failures,
            repository_summaries=repository_summaries,
        )


def _best_matches(
    records: tuple[Any, ...],
    query: str,
    limit: int,
    text_factory,
    repository_root: str,
    repository_root_getter,
) -> tuple[Any, ...]:
    scored: list[tuple[float, datetime, Any]] = []
    for record in records:
        if repository_root and repository_root_getter(record) != repository_root:
            continue
        score = _score_text(query, text_factory(record))
        if score <= 0:
            continue
        scored.append((score, record.recorded_at, record))
    scored.sort(key=lambda item: (-item[0], item[1], getattr(item[2], "summary", "")))
    return tuple(item[2] for item in scored[:limit])
