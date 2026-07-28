"""Execution planning before code edits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .graphs import module_name_from_path
from .semantic import SemanticSearchResult
from .symbol_index import RepositoryIndex


@dataclass(frozen=True, slots=True)
class PlanStep:
    """A single planned repository change target."""

    target_file: Path
    rationale: str
    expected_modifications: tuple[str, ...]
    risks: tuple[str, ...]
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "target_file": self.target_file.as_posix(),
            "rationale": self.rationale,
            "expected_modifications": list(self.expected_modifications),
            "risks": list(self.risks),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """A structured execution plan generated before editing code."""

    objective: str
    target_files: tuple[Path, ...]
    steps: tuple[PlanStep, ...]
    overall_confidence: float
    created_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "objective": self.objective,
            "target_files": [path.as_posix() for path in self.target_files],
            "steps": [step.to_dict() for step in self.steps],
            "overall_confidence": self.overall_confidence,
            "created_at": self.created_at.isoformat(),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


class PlanningModule:
    """Generate an execution plan from repository analysis."""

    def __init__(self, repository_index: RepositoryIndex) -> None:
        self._repository_index = repository_index

    def draft_execution_plan(self, objective: str, *, top_k: int = 5) -> ExecutionPlan:
        results = self._repository_index.semantic_index.search(objective, top_k=top_k)
        if not results:
            return ExecutionPlan(
                objective=objective,
                target_files=(),
                steps=(),
                overall_confidence=0.0,
                created_at=datetime.now(timezone.utc),
            )

        grouped: dict[Path, list[SemanticSearchResult]] = {}
        for result in results:
            grouped.setdefault(result.chunk.path, []).append(result)

        steps = tuple(
            self._build_step(objective, path, matches)
            for path, matches in sorted(
                grouped.items(),
                key=lambda item: (-max(match.score for match in item[1]), item[0].as_posix()),
            )
        )
        target_files = tuple(step.target_file for step in steps)
        overall_confidence = round(sum(step.confidence for step in steps) / len(steps), 3)
        return ExecutionPlan(
            objective=objective,
            target_files=target_files,
            steps=steps,
            overall_confidence=overall_confidence,
            created_at=datetime.now(timezone.utc),
        )

    def _build_step(
        self,
        objective: str,
        path: Path,
        matches: list[SemanticSearchResult],
    ) -> PlanStep:
        file_index = self._file_index_for(path)
        matched_symbols = ", ".join(match.chunk.symbol_name for match in matches[:3])
        rationale = (
            f"Semantic search for '{objective}' ranked {path.as_posix()} as relevant "
            f"via {matched_symbols}."
        )
        expected_modifications = self._expected_modifications(matches)
        risks = self._risks_for(path)
        confidence = round(min(1.0, max(match.score for match in matches)), 3)
        if file_index is not None and file_index.parse_error:
            risks = (*risks, "The file already has a parse error, so edits may be harder to verify.")
            confidence = round(max(0.0, confidence - 0.2), 3)
        return PlanStep(
            target_file=path,
            rationale=rationale,
            expected_modifications=expected_modifications,
            risks=risks,
            confidence=confidence,
        )

    def _expected_modifications(self, matches: list[SemanticSearchResult]) -> tuple[str, ...]:
        modifications: list[str] = []
        for match in matches:
            chunk = match.chunk
            if chunk.kind == "class":
                modifications.append(f"Review class `{chunk.qualified_name}` and its methods.")
            elif chunk.kind == "method":
                modifications.append(f"Inspect method `{chunk.qualified_name}` and related call sites.")
            else:
                modifications.append(f"Inspect function `{chunk.qualified_name}` and adjust its implementation if needed.")
        return tuple(dict.fromkeys(modifications))

    def _risks_for(self, path: Path) -> tuple[str, ...]:
        module_name = module_name_from_path(path)
        dependents = self._repository_index.module_graph.dependents_of(module_name)
        risks = ["Semantic ranking is approximate and may include adjacent code."]
        if dependents:
            risks.append(
                "Changes may affect dependent modules: "
                + ", ".join(dependent for dependent in dependents)
            )
        else:
            risks.append("The file has no known module dependents in the current index.")
        return tuple(risks)

    def _file_index_for(self, path: Path):
        for file_index in self._repository_index.python_files:
            if file_index.path == path:
                return file_index
        return None

