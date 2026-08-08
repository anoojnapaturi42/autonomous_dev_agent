from __future__ import annotations

import json
import unittest
from pathlib import Path

from autonomous_dev_agent.editing import FileEdit
from autonomous_dev_agent.fix_generation import (
    AnthropicLanguageModelClient,
    LLMEditStrategy,
)
from autonomous_dev_agent.orchestrator import AutonomousEditContext
from autonomous_dev_agent.planning import ExecutionPlan, PlanStep
from autonomous_dev_agent.repository import LocalRepository
from autonomous_dev_agent.scanner import RepositoryScanner
from autonomous_dev_agent.tester import FailureSummary, TestRunResult
from datetime import datetime, timezone


REPO_ROOT = Path(__file__).resolve().parents[1]
EDITING_REPO = REPO_ROOT / "eval_repos" / "editing_repo"


class _FakeLanguageModelClient:
    """Records the prompt it was given and returns a canned response."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.last_system: str | None = None
        self.last_user: str | None = None

    def complete(self, *, system: str, user: str) -> str:
        self.last_system = system
        self.last_user = user
        return self.response


class _RaisingLanguageModelClient:
    def complete(self, *, system: str, user: str) -> str:
        raise RuntimeError("simulated provider outage")


class LLMEditStrategyTestCase(unittest.TestCase):
    def _build_context(self) -> AutonomousEditContext:
        sample_path = EDITING_REPO / "sample.py"
        original_text = sample_path.read_text(encoding="utf-8")
        self.addCleanup(sample_path.write_text, original_text, encoding="utf-8")

        repo = LocalRepository(EDITING_REPO)
        repository_index = RepositoryScanner(repo).scan()

        plan = ExecutionPlan(
            objective="Fix the failing test",
            target_files=(Path("sample.py"),),
            steps=(
                PlanStep(
                    target_file=Path("sample.py"),
                    rationale="This file contains the function under test.",
                    expected_modifications=("Fix the return value",),
                    risks=(),
                    confidence=0.8,
                ),
            ),
            overall_confidence=0.8,
            created_at=datetime.now(timezone.utc),
        )
        test_result = TestRunResult(
            runner="pytest",
            exit_code=1,
            success=False,
            stdout="FAILED tests/test_sample.py::test_target - AssertionError",
            stderr="",
            command=("python", "-m", "pytest"),
            cwd=EDITING_REPO,
        )
        failure_summary = FailureSummary(total_failures=1, root_causes=(), failures=())

        return AutonomousEditContext(
            objective="Fix the failing test",
            attempt_number=1,
            retry_limit=2,
            repository_index=repository_index,
            test_result=test_result,
            failure_summary=failure_summary,
            plan=plan,
        )

    def test_returns_file_edit_for_valid_model_response(self) -> None:
        context = self._build_context()
        response = json.dumps(
            {
                "edits": [{"path": "sample.py", "content": "def target():\n    return 'fixed'\n"}],
                "explanation": "Fixed the return value.",
            }
        )
        client = _FakeLanguageModelClient(response)
        strategy = LLMEditStrategy(client)

        edits = strategy(context)

        self.assertEqual(len(edits), 1)
        self.assertIsInstance(edits[0], FileEdit)
        self.assertEqual(edits[0].path, Path("sample.py"))
        self.assertIn("fixed", edits[0].replacement_text)
        # The prompt should have been grounded in the actual failing test output.
        assert client.last_user is not None
        self.assertIn("AssertionError", client.last_user)
        self.assertIn("sample.py", client.last_user)

    def test_strips_markdown_fences_from_response(self) -> None:
        context = self._build_context()
        response = "```json\n" + json.dumps(
            {"edits": [{"path": "sample.py", "content": "x = 1\n"}]}
        ) + "\n```"
        strategy = LLMEditStrategy(_FakeLanguageModelClient(response))

        edits = strategy(context)

        self.assertEqual(len(edits), 1)

    def test_ignores_edits_to_files_outside_the_plan(self) -> None:
        context = self._build_context()
        response = json.dumps(
            {
                "edits": [
                    {"path": "sample.py", "content": "x = 1\n"},
                    {"path": "../outside.py", "content": "malicious = True\n"},
                ]
            }
        )
        strategy = LLMEditStrategy(_FakeLanguageModelClient(response))

        edits = strategy(context)

        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].path, Path("sample.py"))

    def test_returns_no_edits_on_malformed_json(self) -> None:
        context = self._build_context()
        strategy = LLMEditStrategy(_FakeLanguageModelClient("not valid json"))

        edits = strategy(context)

        self.assertEqual(edits, ())

    def test_returns_no_edits_when_edits_key_is_missing(self) -> None:
        context = self._build_context()
        strategy = LLMEditStrategy(_FakeLanguageModelClient(json.dumps({"explanation": "nothing to do"})))

        edits = strategy(context)

        self.assertEqual(edits, ())

    def test_returns_no_edits_when_model_declines(self) -> None:
        context = self._build_context()
        strategy = LLMEditStrategy(
            _FakeLanguageModelClient(json.dumps({"edits": [], "explanation": "need more info"}))
        )

        edits = strategy(context)

        self.assertEqual(edits, ())

    def test_returns_no_edits_and_does_not_raise_when_provider_fails(self) -> None:
        context = self._build_context()
        strategy = LLMEditStrategy(_RaisingLanguageModelClient())

        edits = strategy(context)

        self.assertEqual(edits, ())

    def test_returns_no_edits_when_plan_has_no_target_files(self) -> None:
        context = self._build_context()
        empty_plan = ExecutionPlan(
            objective=context.objective,
            target_files=(),
            steps=(),
            overall_confidence=0.0,
            created_at=datetime.now(timezone.utc),
        )
        context = AutonomousEditContext(
            objective=context.objective,
            attempt_number=context.attempt_number,
            retry_limit=context.retry_limit,
            repository_index=context.repository_index,
            test_result=context.test_result,
            failure_summary=context.failure_summary,
            plan=empty_plan,
        )
        strategy = LLMEditStrategy(_FakeLanguageModelClient(json.dumps({"edits": []})))

        edits = strategy(context)

        self.assertEqual(edits, ())


class AnthropicLanguageModelClientTestCase(unittest.TestCase):
    def test_complete_extracts_text_blocks_from_response(self) -> None:
        class _FakeTextBlock:
            def __init__(self, text: str) -> None:
                self.type = "text"
                self.text = text

        class _FakeMessages:
            def create(self, **kwargs):  # noqa: ANN003
                self.last_kwargs = kwargs

                class _Response:
                    content = [_FakeTextBlock("hello "), _FakeTextBlock("world")]

                return _Response()

        class _FakeAnthropicClient:
            def __init__(self, api_key: str) -> None:
                self.api_key = api_key
                self.messages = _FakeMessages()

        import sys
        import types

        fake_module = types.ModuleType("anthropic")
        fake_module.Anthropic = _FakeAnthropicClient  # type: ignore[attr-defined]
        sys.modules["anthropic"] = fake_module
        self.addCleanup(sys.modules.pop, "anthropic", None)

        client = AnthropicLanguageModelClient(api_key="test-key", model="claude-sonnet-4-6")
        result = client.complete(system="sys", user="user")

        self.assertEqual(result, "hello world")


if __name__ == "__main__":
    unittest.main()
