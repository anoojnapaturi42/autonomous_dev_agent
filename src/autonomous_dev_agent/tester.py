"""Test execution helpers for detecting and running repository tests."""

from __future__ import annotations

import importlib.util
import json
import os
import xml.etree.ElementTree as ET
from uuid import uuid4
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .sandbox import CommandExecutor, LocalCommandExecutor


@dataclass(frozen=True, slots=True)
class TestCaseResult:
    """Structured result for a single executed test case."""

    nodeid: str
    outcome: str
    file: str | None
    line: int | None
    duration: float
    classname: str | None = None
    name: str | None = None
    message: str | None = None
    failure_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodeid": self.nodeid,
            "outcome": self.outcome,
            "file": self.file,
            "line": self.line,
            "duration": self.duration,
            "classname": self.classname,
            "name": self.name,
            "message": self.message,
            "failure_type": self.failure_type,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TestCaseResult":
        return cls(
            nodeid=str(payload.get("nodeid", "unknown")),
            outcome=str(payload.get("outcome", "unknown")),
            file=payload.get("file") if payload.get("file") is None else str(payload.get("file")),
            line=payload.get("line"),
            duration=float(payload.get("duration", 0.0)),
            classname=payload.get("classname") if payload.get("classname") is None else str(payload.get("classname")),
            name=payload.get("name") if payload.get("name") is None else str(payload.get("name")),
            message=payload.get("message") if payload.get("message") is None else str(payload.get("message")),
            failure_type=payload.get("failure_type") if payload.get("failure_type") is None else str(payload.get("failure_type")),
        )


@dataclass(frozen=True, slots=True)
class FailureAnalysis:
    """Structured explanation of a pytest failure."""

    test_name: str
    failure_type: str
    root_cause: str
    summary: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_name": self.test_name,
            "failure_type": self.failure_type,
            "root_cause": self.root_cause,
            "summary": self.summary,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FailureAnalysis":
        return cls(
            test_name=str(payload.get("test_name", "")),
            failure_type=str(payload.get("failure_type", "unknown")),
            root_cause=str(payload.get("root_cause", "unknown")),
            summary=str(payload.get("summary", "")),
            detail=str(payload.get("detail", "")),
        )


@dataclass(frozen=True, slots=True)
class FailureAnalysisResult:
    """Structured result of analyzing pytest failures."""

    total_failures: int
    failures: tuple[FailureAnalysis, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_failures": self.total_failures,
            "failures": [failure.to_dict() for failure in self.failures],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FailureAnalysisResult":
        return cls(
            total_failures=int(payload.get("total_failures", 0)),
            failures=tuple(FailureAnalysis.from_dict(item) for item in payload.get("failures", ())),
        )


@dataclass(frozen=True, slots=True)
class FailureCauseSummary:
    """Grouped root-cause summary for a set of pytest failures."""

    root_cause: str
    summary: str
    count: int
    confidence: float
    test_names: tuple[str, ...]
    failure_types: tuple[str, ...]
    details: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_cause": self.root_cause,
            "summary": self.summary,
            "count": self.count,
            "confidence": self.confidence,
            "test_names": list(self.test_names),
            "failure_types": list(self.failure_types),
            "details": list(self.details),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FailureCauseSummary":
        return cls(
            root_cause=str(payload.get("root_cause", "unknown")),
            summary=str(payload.get("summary", "")),
            count=int(payload.get("count", 0)),
            confidence=float(payload.get("confidence", 0.0)),
            test_names=tuple(str(item) for item in payload.get("test_names", ())),
            failure_types=tuple(str(item) for item in payload.get("failure_types", ())),
            details=tuple(str(item) for item in payload.get("details", ())),
        )


@dataclass(frozen=True, slots=True)
class FailureSummary:
    """Structured reasoning summary for a test run."""

    total_failures: int
    root_causes: tuple[FailureCauseSummary, ...]
    failures: tuple[FailureAnalysis, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_failures": self.total_failures,
            "root_causes": [cause.to_dict() for cause in self.root_causes],
            "failures": [failure.to_dict() for failure in self.failures],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FailureSummary":
        return cls(
            total_failures=int(payload.get("total_failures", 0)),
            root_causes=tuple(FailureCauseSummary.from_dict(item) for item in payload.get("root_causes", ())),
            failures=tuple(FailureAnalysis.from_dict(item) for item in payload.get("failures", ())),
        )


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
    cases: tuple[TestCaseResult, ...] = ()
    analysis: FailureAnalysisResult | None = None
    failure_summary: FailureSummary | None = None

    def to_dict(self) -> dict[str, Any]:
        summary = self._summary_from_cases()
        if summary is None:
            summary = self._parse_summary(self.stdout, self.stderr)
        payload: dict[str, Any] = {
            "runner": self.runner,
            "exit_code": self.exit_code,
            "success": self.success,
            "command": list(self.command),
            "cwd": self.cwd.as_posix(),
            "summary": summary,
            "cases": [case.to_dict() for case in self.cases],
        }
        if self.analysis is not None:
            payload["analysis"] = self.analysis.to_dict()
        if self.failure_summary is not None:
            payload["failure_summary"] = self.failure_summary.to_dict()
        return payload

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TestRunResult":
        return cls(
            runner=str(payload.get("runner", "unknown")),
            exit_code=int(payload.get("exit_code", 0)),
            success=bool(payload.get("success", False)),
            stdout=str(payload.get("stdout", "")),
            stderr=str(payload.get("stderr", "")),
            command=tuple(str(item) for item in payload.get("command", ())),
            cwd=Path(str(payload.get("cwd", "."))),
            cases=tuple(TestCaseResult.from_dict(item) for item in payload.get("cases", ())),
            analysis=FailureAnalysisResult.from_dict(payload["analysis"]) if payload.get("analysis") else None,
            failure_summary=FailureSummary.from_dict(payload["failure_summary"]) if payload.get("failure_summary") else None,
        )

    def _summary_from_cases(self) -> dict[str, int] | None:
        if not self.cases:
            return None
        summary: dict[str, int] = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0, "total": 0}
        for case in self.cases:
            summary["total"] += 1
            if case.outcome == "passed":
                summary["passed"] += 1
            elif case.outcome == "failed":
                summary["failed"] += 1
            elif case.outcome == "error":
                summary["errors"] += 1
            elif case.outcome == "skipped":
                summary["skipped"] += 1
        return summary

    def _parse_summary(self, stdout: str, stderr: str) -> dict[str, int]:
        summary: dict[str, int] = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0, "total": 0}
        for line in (stdout + "\n" + stderr).splitlines():
            if "passed" in line and "failed" in line:
                for part in line.replace("=", " ").replace(",", " ").split():
                    if part.endswith("passed") and part[:-6].isdigit():
                        summary["passed"] = int(part[:-6])
                    elif part.endswith("failed") and part[:-6].isdigit():
                        summary["failed"] = int(part[:-6])
                    elif part.endswith("skipped") and part[:-7].isdigit():
                        summary["skipped"] = int(part[:-7])
                    elif part.endswith("error") and part[:-5].isdigit():
                        summary["errors"] = int(part[:-5])
                    elif part.endswith("errors") and part[:-6].isdigit():
                        summary["errors"] = int(part[:-6])
        summary["total"] = summary["passed"] + summary["failed"] + summary["skipped"] + summary["errors"]
        return summary


class PytestTestRunner:
    """Detect pytest availability and run repository tests."""

    def __init__(
        self,
        repository_root: str | os.PathLike[str] | Path,
        *,
        executor: CommandExecutor | None = None,
    ) -> None:
        self._repository_root = Path(repository_root).resolve()
        self._executor = executor or LocalCommandExecutor()

    def detect(self) -> str:
        if not self._pytest_is_available():
            return "none"
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
                cases=(),
                analysis=None,
                failure_summary=None,
            )

        # The report file must live inside the repository root (not the host
        # temp dir) so it is visible on the host after a sandboxed/Docker
        # run, where only the mounted repository directory is shared back.
        report_dir = self._repository_root / ".autonomous_dev_agent" / "tmp"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"pytest-report-{uuid4().hex}.xml"
        command = [
            self._executor.python_executable,
            "-m",
            "pytest",
            "-q",
            f"--junitxml={report_path.relative_to(self._repository_root)}",
        ]
        if (self._repository_root / "eval_repos").exists():
            command.append("--ignore=eval_repos")
        completed = self._executor.run(
            command,
            cwd=self._repository_root,
            env={"AUTONOMOUS_DEV_AGENT_RUNNING_PYTEST": "1"},
        )
        cases = self._load_cases_from_junitxml(report_path)
        try:
            report_path.unlink(missing_ok=True)
        except OSError:
            pass
        result = TestRunResult(
            runner="pytest",
            exit_code=completed.returncode,
            success=completed.returncode == 0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            command=tuple(command),
            cwd=self._repository_root,
            cases=cases,
            analysis=None,
            failure_summary=None,
        )
        return TestRunResult(
            runner=result.runner,
            exit_code=result.exit_code,
            success=result.success,
            stdout=result.stdout,
            stderr=result.stderr,
            command=result.command,
            cwd=result.cwd,
            cases=result.cases,
            analysis=self.analyze(result),
            failure_summary=self.summarize(result),
        )

    def analyze(self, result: TestRunResult) -> FailureAnalysisResult:
        if result.exit_code == 0:
            return FailureAnalysisResult(total_failures=0, failures=())

        failures: list[FailureAnalysis] = []
        if result.cases:
            for case in result.cases:
                if case.outcome in {"failed", "error"}:
                    failures.append(
                        FailureAnalysis(
                            test_name=case.nodeid,
                            failure_type=case.failure_type or "unknown",
                            root_cause=_root_cause_from_failure_type(case.failure_type, case.message),
                            summary=_summary_from_case(case.failure_type, case.message),
                            detail=case.message or case.nodeid,
                        )
                    )
        else:
            combined_output = "\n".join(part for part in (result.stdout, result.stderr) if part)
            for line in combined_output.splitlines():
                if not line.strip():
                    continue
                if line.startswith("FAILED") or line.startswith("ERROR"):
                    failure = self._analyze_failure_line(line)
                    if failure is not None:
                        failures.append(failure)
        if not failures:
            failures.append(
                FailureAnalysis(
                    test_name="unknown",
                    failure_type="unknown",
                    root_cause="unknown",
                    summary="Pytest failed but no structured failure could be extracted.",
                    detail=result.stdout.strip() or result.stderr.strip(),
                )
            )
        return FailureAnalysisResult(total_failures=len(failures), failures=tuple(failures))

    def summarize(self, result: TestRunResult) -> FailureSummary:
        analysis = result.analysis or self.analyze(result)
        root_cause_groups: dict[str, list[FailureAnalysis]] = defaultdict(list)
        for failure in analysis.failures:
            root_cause_groups[failure.root_cause].append(failure)

        grouped: list[FailureCauseSummary] = []
        total = analysis.total_failures or len(analysis.failures)
        for root_cause, failures in sorted(
            root_cause_groups.items(),
            key=lambda item: (-len(item[1]), item[0]),
        ):
            summary = _most_common_summary(failures)
            grouped.append(
                FailureCauseSummary(
                    root_cause=root_cause,
                    summary=summary,
                    count=len(failures),
                    confidence=round(len(failures) / total, 3) if total else 0.0,
                    test_names=tuple(sorted({failure.test_name for failure in failures})),
                    failure_types=tuple(sorted({failure.failure_type for failure in failures})),
                    details=tuple(failure.detail for failure in failures),
                )
            )

        return FailureSummary(
            total_failures=analysis.total_failures,
            root_causes=tuple(grouped),
            failures=analysis.failures,
        )

    def _analyze_failure_line(self, line: str) -> FailureAnalysis | None:
        normalized = line.strip()
        if not normalized:
            return None

        marker = normalized.split(" ", 1)[0]
        remainder = normalized[len(marker) + 1 :] if marker in {"FAILED", "ERROR"} else normalized
        test_name = remainder.split(" - ", 1)[0].split(" -", 1)[0].strip() if " - " in remainder else remainder
        detail = remainder.split(" - ", 1)[1].strip() if " - " in remainder else ""
        failure_type = "unknown"
        root_cause = "unknown"
        summary = "Pytest reported a failure."

        if "AssertionError" in detail:
            failure_type = "AssertionError"
            root_cause = "assertion_mismatch"
            summary = "An assertion failed, indicating the observed value did not match the expected behavior."
        elif "ModuleNotFoundError" in detail or "No module named" in detail:
            failure_type = "ModuleNotFoundError"
            root_cause = "missing_dependency"
            summary = "A required dependency or import could not be resolved during test execution."
        elif "ImportError" in detail:
            failure_type = "ImportError"
            root_cause = "import_error"
            summary = "An expected import failed during the test run."
        elif "TypeError" in detail:
            failure_type = "TypeError"
            root_cause = "type_mismatch"
            summary = "The test encountered an unexpected type or argument shape."
        elif "ValueError" in detail:
            failure_type = "ValueError"
            root_cause = "invalid_value"
            summary = "The test hit an invalid value or state during execution."

        if not detail:
            detail = normalized
        return FailureAnalysis(
            test_name=test_name,
            failure_type=failure_type,
            root_cause=root_cause,
            summary=summary,
            detail=detail,
        )

    def _load_cases_from_junitxml(self, report_path: Path) -> tuple[TestCaseResult, ...]:
        if not report_path.exists():
            return ()
        try:
            tree = ET.parse(report_path)
        except ET.ParseError:
            return ()

        root = tree.getroot()
        cases: list[TestCaseResult] = []
        for node in root.iter("testcase"):
            outcome, failure_type, message = self._extract_case_outcome(node)
            file_name = node.attrib.get("file")
            line = _safe_int(node.attrib.get("line"))
            classname = node.attrib.get("classname")
            name = node.attrib.get("name")
            nodeid = _build_nodeid(file_name, classname, name)
            cases.append(
                TestCaseResult(
                    nodeid=nodeid,
                    outcome=outcome,
                    file=file_name,
                    line=line,
                    duration=float(node.attrib.get("time", "0") or 0),
                    classname=classname,
                    name=name,
                    message=message,
                    failure_type=failure_type,
                )
            )
        return tuple(cases)

    def _extract_case_outcome(self, node: ET.Element) -> tuple[str, str | None, str | None]:
        for child in node:
            if child.tag == "failure":
                return "failed", child.attrib.get("type"), _normalize_xml_text(child.text or child.attrib.get("message"))
            if child.tag == "error":
                return "error", child.attrib.get("type"), _normalize_xml_text(child.text or child.attrib.get("message"))
            if child.tag == "skipped":
                return "skipped", child.attrib.get("type"), _normalize_xml_text(child.text or child.attrib.get("message"))
        return "passed", None, None

    def _pytest_is_available(self) -> bool:
        return importlib.util.find_spec("pytest") is not None

    def _has_pytest_configuration(self) -> bool:
        return any((self._repository_root / name).exists() for name in ("pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg"))

    def _has_pytest_tests(self) -> bool:
        tests_dir = self._repository_root / "tests"
        if not tests_dir.exists():
            return False
        return any(path.suffix == ".py" for path in tests_dir.rglob("*.py"))


def _build_nodeid(file_name: str | None, classname: str | None, name: str | None) -> str:
    parts = [part for part in (file_name, classname, name) if part]
    return "::".join(parts) if parts else "unknown"


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _normalize_xml_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = text.strip()
    return normalized or None


def _root_cause_from_failure_type(failure_type: str | None, detail: str | None) -> str:
    combined = " ".join(part for part in (failure_type or "", detail or "") if part)
    if "AssertionError" in combined:
        return "assertion_mismatch"
    if "ModuleNotFoundError" in combined or "No module named" in combined:
        return "missing_dependency"
    if "ImportError" in combined:
        return "import_error"
    if "TypeError" in combined:
        return "type_mismatch"
    if "ValueError" in combined:
        return "invalid_value"
    return "unknown"


def _summary_from_case(failure_type: str | None, detail: str | None) -> str:
    combined = " ".join(part for part in (failure_type or "", detail or "") if part)
    if "AssertionError" in combined:
        return "An assertion failed, indicating the observed value did not match the expected behavior."
    if "ModuleNotFoundError" in combined or "No module named" in combined:
        return "A required dependency or import could not be resolved during test execution."
    if "ImportError" in combined:
        return "An expected import failed during the test run."
    if "TypeError" in combined:
        return "The test encountered an unexpected type or argument shape."
    if "ValueError" in combined:
        return "The test hit an invalid value or state during execution."
    return "Pytest reported a failure."


def _most_common_summary(failures: list[FailureAnalysis]) -> str:
    summaries: dict[str, int] = defaultdict(int)
    for failure in failures:
        summaries[failure.summary] += 1
    if not summaries:
        return "Pytest reported a failure."
    return max(summaries.items(), key=lambda item: (item[1], item[0]))[0]
