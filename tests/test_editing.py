from __future__ import annotations

import textwrap
import unittest
from pathlib import Path

from autonomous_dev_agent.editing import FileEdit, SafeEditingEngine, SymbolEdit
from autonomous_dev_agent.repository import LocalRepository
from autonomous_dev_agent.scanner import RepositoryScanner


REPO_ROOT = Path(__file__).resolve().parents[1]
EDITING_REPO = REPO_ROOT / "eval_repos" / "editing_repo"


class SafeEditingEngineTestCase(unittest.TestCase):
    def _build_repo(self) -> tuple[Path, LocalRepository, object]:
        root = EDITING_REPO
        sample_path = root / "sample.py"
        notes_path = root / "notes.txt"
        sample_before = sample_path.read_text(encoding="utf-8")
        notes_before = notes_path.read_text(encoding="utf-8")
        self.addCleanup(sample_path.write_text, sample_before, encoding="utf-8")
        self.addCleanup(notes_path.write_text, notes_before, encoding="utf-8")
        repo = LocalRepository(root)
        index = RepositoryScanner(repo).scan()
        return root, repo, index

    def test_symbol_edit_produces_diff_before_writing_and_preserves_surrounding_content(self) -> None:
        root, repo, index = self._build_repo()
        sample_path = root / "sample.py"
        before = sample_path.read_text(encoding="utf-8")
        engine = SafeEditingEngine(repo, repository_index=index)

        previews = engine.preview(
            [
                SymbolEdit(
                    path=Path("sample.py"),
                    symbol_name="target",
                    replacement_text=textwrap.dedent(
                        """
                        @logged
                        def target(value: str) -> str:
                            return value.upper()
                        """
                    ).strip("\n"),
                )
            ]
        )

        self.assertEqual(sample_path.read_text(encoding="utf-8"), before)
        self.assertEqual(len(previews), 1)
        preview = previews[0]
        self.assertEqual(preview.strategy, "symbol")
        self.assertEqual(preview.path, sample_path.resolve())
        self.assertIn("--- a/sample.py", preview.diff)
        self.assertIn("+++ b/sample.py", preview.diff)
        self.assertIn("-    return value.strip()", preview.diff)
        self.assertIn("+    return value.upper()", preview.diff)

        result = engine.apply(
            [
                SymbolEdit(
                    path=Path("sample.py"),
                    symbol_name="target",
                    replacement_text=textwrap.dedent(
                        """
                        @logged
                        def target(value: str) -> str:
                            return value.upper()
                        """
                    ).strip("\n"),
                )
            ]
        )

        self.assertEqual(result.written_paths, (sample_path.resolve(),))
        updated = sample_path.read_text(encoding="utf-8")
        self.assertIn("# leading comment", updated)
        self.assertIn("# trailing comment", updated)
        self.assertIn("return value.upper()", updated)
        self.assertNotIn("return value.strip()", updated)

    def test_full_file_edit_also_emits_git_style_diff(self) -> None:
        root, repo, index = self._build_repo()
        notes_path = root / "notes.txt"
        engine = SafeEditingEngine(repo, repository_index=index)

        previews = engine.preview(
            [
                FileEdit(
                    path=Path("notes.txt"),
                    replacement_text="alpha\ngamma\n",
                )
            ]
        )

        self.assertEqual(len(previews), 1)
        preview = previews[0]
        self.assertEqual(preview.strategy, "file")
        self.assertIn("--- a/notes.txt", preview.diff)
        self.assertIn("+++ b/notes.txt", preview.diff)
        self.assertIn("-beta", preview.diff)
        self.assertIn("+gamma", preview.diff)
        self.assertEqual(notes_path.read_text(encoding="utf-8"), "alpha\nbeta\n")

        engine.apply([FileEdit(path=Path("notes.txt"), replacement_text="alpha\ngamma\n")])
        self.assertEqual(notes_path.read_text(encoding="utf-8"), "alpha\ngamma\n")
