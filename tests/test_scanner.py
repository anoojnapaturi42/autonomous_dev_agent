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
        self.assertEqual(index.python_files[0].module_docstring, None)
        self.assertEqual(index.python_files[0].imports[0].statement, "from pathlib import Path")
        self.assertEqual(index.python_files[0].imports[0].module, "pathlib")
        self.assertEqual(index.python_files[0].imports[0].names, ("Path",))
        self.assertEqual(index.python_files[0].classes, ())
        self.assertEqual(index.python_files[0].functions, ("guide_root",))
        self.assertEqual(index.python_files[0].symbols[0].docstring, "Return the root path for the guide.")
        self.assertIsNone(index.python_files[0].parse_error)
        self.assertEqual(index.python_files[1].module_docstring, "Toy module for AST parsing tests.")
        self.assertEqual([imp.statement for imp in index.python_files[1].imports], ["import os", "from collections import defaultdict"])
        self.assertEqual(index.python_files[1].classes, ("BaseWorker", "SampleWorker"))
        self.assertEqual(index.python_files[1].functions, ("traced", "build_index"))
        self.assertEqual(index.python_files[1].methods, ("run",))
        self.assertEqual(index.python_files[1].variables, ("MODULE_LEVEL", "base_kind", "base_role", "result", "index"))
        sample_worker = index.symbol_index.find_by_name("SampleWorker")
        self.assertEqual(len(sample_worker), 1)
        self.assertEqual(sample_worker[0].kind, "class")
        self.assertEqual(sample_worker[0].decorators, ("traced",))
        self.assertEqual(sample_worker[0].bases, ("BaseWorker",))
        run_symbols = index.symbol_index.find_by_name("run")
        self.assertEqual(len(run_symbols), 1)
        self.assertEqual(run_symbols[0].kind, "method")
        self.assertEqual(run_symbols[0].decorators, ("traced",))
        self.assertEqual(run_symbols[0].docstring, "Return the basename of a known file.")
        build_index = index.symbol_index.find_by_name("build_index")
        self.assertEqual(len(build_index), 1)
        self.assertEqual(build_index[0].kind, "function")
        self.assertEqual(build_index[0].decorators, ("traced",))
        self.assertEqual(build_index[0].docstring, "Build a tiny in-memory index.")
        location_matches = index.symbol_index.find_by_location(Path("src/module.py"), 32)
        self.assertEqual({symbol.name for symbol in location_matches}, {"SampleWorker", "run", "result"})
        function_location_matches = index.symbol_index.find_by_location(Path("src/module.py"), 40)
        self.assertEqual({symbol.name for symbol in function_location_matches}, {"build_index", "index"})
        self.assertIsNone(index.python_files[1].parse_error)
        self.assertEqual(index.python_files[0].modified_at.tzinfo, timezone.utc)
        self.assertEqual(index.python_files[1].modified_at.tzinfo, timezone.utc)
        self.assertGreater(index.python_files[0].size, 0)
        self.assertGreater(index.python_files[1].size, 0)
