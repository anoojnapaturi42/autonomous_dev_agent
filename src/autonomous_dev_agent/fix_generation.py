"""An LLM-backed edit strategy that proposes code fixes for failing tests.

This module implements the `EditStrategy` protocol from `orchestrator.py`
using a language model to reason about a test failure and produce whole-file
replacements. It is deliberately isolated from the orchestration loop itself:
the orchestrator only knows it received a callable that returns edits, not
that the edits came from an LLM.

The language model client is a small pluggable interface (mirroring the
pattern already used by `embeddings.py`) so tests can supply a fake client
without making real network calls, and so the underlying provider/model can
change later without touching the strategy logic.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .editing import EditRequest, FileEdit
from .orchestrator import AutonomousEditContext

logger = logging.getLogger(__name__)

_MAX_FILE_CHARS = 20_000
_MAX_TEST_OUTPUT_CHARS = 4_000
_MAX_TARGET_FILES = 5


class LanguageModelClient(Protocol):
    """Minimal interface for a language model call used to propose fixes."""

    def complete(self, *, system: str, user: str) -> str:
        """Return the model's raw text response for a single-turn prompt."""


@dataclass(slots=True)
class AnthropicLanguageModelClient:
    """LanguageModelClient backed by the Anthropic Messages API."""

    api_key: str
    model: str = "claude-sonnet-4-6"
    max_output_tokens: int = 8000

    def complete(self, *, system: str, user: str) -> str:
        # Imported lazily so the `anthropic` package is only required when
        # this client is actually used, not for the whole package.
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_output_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )


_SYSTEM_PROMPT = """You are an autonomous software engineering agent fixing a failing test suite.

You will be given the failing test output, a structured failure analysis, an execution plan \
naming the files most likely responsible, and the current full contents of those files.

Respond with ONLY a single JSON object (no markdown fences, no commentary) matching this schema:
{
  "edits": [
    {"path": "relative/path/from/repo/root.ext", "content": "the complete new contents of the file"}
  ],
  "explanation": "one or two sentences on what you changed and why"
}

Rules:
- "path" must exactly match one of the file paths you were given.
- "content" must be the COMPLETE new file, not a diff or a snippet.
- Only include files you are actually changing.
- Make the smallest change that plausibly fixes the failure. Do not refactor unrelated code.
- If you cannot determine a fix from the given information, return {"edits": [], "explanation": "..."} \
explaining what additional information you would need.
"""


class LLMEditStrategy:
    """Edit strategy that asks a language model to propose whole-file fixes."""

    def __init__(self, client: LanguageModelClient) -> None:
        self._client = client

    def __call__(self, context: AutonomousEditContext) -> tuple[EditRequest, ...]:
        target_files = context.plan.target_files[:_MAX_TARGET_FILES]
        if not target_files:
            logger.info("LLM edit strategy skipped: the plan named no target files.")
            return ()

        allowed_paths = {path.as_posix() for path in target_files}
        file_contents = self._read_files(context.repository_index.root, target_files)
        if not file_contents:
            logger.warning("LLM edit strategy skipped: none of the planned target files could be read.")
            return ()

        user_prompt = self._build_user_prompt(context, file_contents)

        try:
            raw_response = self._client.complete(system=_SYSTEM_PROMPT, user=user_prompt)
        except Exception:  # noqa: BLE001 - any provider failure should not crash the loop
            logger.exception("LLM edit strategy call failed; declining to propose edits.")
            return ()

        proposed = self._parse_response(raw_response)
        if proposed is None:
            return ()

        edits: list[EditRequest] = []
        for item in proposed:
            path = str(item.get("path", "")).strip()
            content = item.get("content")
            if path not in allowed_paths:
                logger.warning(
                    "Ignoring proposed edit to '%s': not one of the planned target files.", path
                )
                continue
            if not isinstance(content, str):
                logger.warning("Ignoring proposed edit to '%s': content was not a string.", path)
                continue
            edits.append(FileEdit(path=Path(path), replacement_text=content))

        return tuple(edits)

    def _read_files(self, root: Path, target_files: tuple[Path, ...]) -> dict[str, str]:
        file_contents: dict[str, str] = {}
        for relative_path in target_files:
            absolute_path = (root / relative_path).resolve()
            try:
                if not absolute_path.is_relative_to(root.resolve()):
                    continue
                text = absolute_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if len(text) > _MAX_FILE_CHARS:
                text = text[:_MAX_FILE_CHARS] + "\n... (truncated)\n"
            file_contents[relative_path.as_posix()] = text
        return file_contents

    def _build_user_prompt(
        self,
        context: AutonomousEditContext,
        file_contents: dict[str, str],
    ) -> str:
        failure_summary = context.failure_summary.to_dict()
        test_output = (context.test_result.stdout or "") + "\n" + (context.test_result.stderr or "")
        if len(test_output) > _MAX_TEST_OUTPUT_CHARS:
            test_output = test_output[-_MAX_TEST_OUTPUT_CHARS:]

        plan_steps = "\n".join(
            f"- {step.target_file.as_posix()}: {step.rationale}"
            for step in context.plan.steps
        )

        files_section = "\n\n".join(
            f"--- FILE: {path} ---\n{text}" for path, text in file_contents.items()
        )

        return (
            f"Objective: {context.objective}\n\n"
            f"Structured failure analysis (JSON):\n{json.dumps(failure_summary, indent=2)}\n\n"
            f"Relevant test output (tail):\n{test_output}\n\n"
            f"Plan steps:\n{plan_steps}\n\n"
            f"Current contents of the planned target files:\n{files_section}\n"
        )

    def _parse_response(self, raw_response: str) -> list[dict[str, object]] | None:
        text = raw_response.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[len("json"):]
        text = text.strip()

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM edit strategy response was not valid JSON; declining to propose edits.")
            return None

        if not isinstance(payload, dict):
            logger.warning("LLM edit strategy response was not a JSON object; declining to propose edits.")
            return None

        edits = payload.get("edits")
        if not isinstance(edits, list):
            logger.warning("LLM edit strategy response had no 'edits' list; declining to propose edits.")
            return None

        return [item for item in edits if isinstance(item, dict)]
