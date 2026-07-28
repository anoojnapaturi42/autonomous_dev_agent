from __future__ import annotations

import unittest
from datetime import timezone
from pathlib import Path

from autonomous_dev_agent.repository import LocalRepository
from autonomous_dev_agent.scanner import RepositoryScanner


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_REPO_FIXTURE = REPO_ROOT / "eval_repos" / "toy"


class RepositoryScannerTestCase(unittest.TestCase):
    def test_scans_python_files_into_structured_metadata(self) -> None:
        repository = LocalRepository(LOCAL_REPO_FIXTURE)
        scanner = RepositoryScanner(repository)

        index = scanner.scan()

        self.assertEqual(index.root, LOCAL_REPO_FIXTURE.resolve())
        self.assertEqual([file.path for file in index.python_files], [Path("docs/guide.py"), Path("src/module.py")])
        self.assertEqual(index.python_files[0].imports, ("from pathlib import Path",))
        self.assertEqual(index.python_files[0].classes, ())
        self.assertEqual(index.python_files[0].functions, ("guide_root",))
        self.assertIsNone(index.python_files[0].parse_error)
        self.assertEqual(
            index.python_files[1].imports,
            ("import os", "from collections import defaultdict"),
        )
        self.assertEqual(index.python_files[1].classes, ("SampleWorker",))
        self.assertEqual(index.python_files[1].functions, ("build_index",))
        self.assertIsNone(index.python_files[1].parse_error)
        self.assertEqual(index.python_files[0].modified_at.tzinfo, timezone.utc)
        self.assertEqual(index.python_files[1].modified_at.tzinfo, timezone.utc)
        self.assertGreater(index.python_files[0].size, 0)
        self.assertGreater(index.python_files[1].size, 0)

