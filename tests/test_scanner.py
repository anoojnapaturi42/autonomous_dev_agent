from __future__ import annotations

import json
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
        files = {file.path: file for file in index.python_files}

        self.assertEqual(index.root, LOCAL_REPO_FIXTURE.resolve())
        self.assertEqual(
            list(files),
            [
                Path("docs/guide.py"),
                Path("src/auth.py"),
                Path("src/graph_a.py"),
                Path("src/graph_b.py"),
                Path("src/module.py"),
            ],
        )

        guide = files[Path("docs/guide.py")]
        auth = files[Path("src/auth.py")]
        module = files[Path("src/module.py")]
        graph_a = files[Path("src/graph_a.py")]
        graph_b = files[Path("src/graph_b.py")]

        self.assertEqual(guide.module_docstring, None)
        self.assertEqual(guide.imports[0].statement, "from pathlib import Path")
        self.assertEqual(guide.imports[0].module, "pathlib")
        self.assertEqual(guide.imports[0].names, ("Path",))
        self.assertEqual(guide.imports[0].targets, ("pathlib.Path",))
        self.assertEqual(guide.functions, ("guide_root",))
        self.assertEqual(guide.symbols[0].docstring, "Return the root path for the guide.")
        self.assertIsNone(guide.parse_error)

        self.assertEqual(auth.module_docstring, "Authentication helpers for the toy repository.")
        self.assertEqual(auth.functions, ("authenticate_user",))
        self.assertEqual(auth.symbols[0].docstring, "Handle authentication for sign-in requests.")
        self.assertEqual(auth.symbols[0].kind, "function")
        self.assertIsNone(auth.parse_error)

        self.assertEqual(module.module_docstring, "Toy module for AST parsing tests.")
        self.assertEqual(
            [imp.statement for imp in module.imports],
            ["import os", "from collections import defaultdict"],
        )
        self.assertEqual(module.imports[0].targets, ("os",))
        self.assertEqual(module.imports[1].targets, ("collections.defaultdict",))
        self.assertEqual(module.classes, ("BaseWorker", "SampleWorker"))
        self.assertEqual(module.functions, ("traced", "format_result", "build_index"))
        self.assertEqual(module.methods, ("run",))
        self.assertEqual(module.variables, ("MODULE_LEVEL", "base_kind", "base_role", "result", "index", "label"))
        self.assertIsNone(module.parse_error)

        sample_worker = index.symbol_index.find_by_name("SampleWorker")
        self.assertEqual(len(sample_worker), 1)
        self.assertEqual(sample_worker[0].kind, "class")
        self.assertEqual(sample_worker[0].decorators, ("traced",))
        self.assertEqual(sample_worker[0].bases, ("BaseWorker",))
        self.assertEqual(sample_worker[0].docstring, "Sample worker implementation.")

        run_symbols = index.symbol_index.find_by_name("run")
        self.assertEqual(len(run_symbols), 1)
        self.assertEqual(run_symbols[0].kind, "method")
        self.assertEqual(run_symbols[0].decorators, ("traced",))
        self.assertEqual(run_symbols[0].docstring, "Return the basename of a known file.")
        self.assertEqual(run_symbols[0].calls, ("format_result", "basename"))

        format_result = index.symbol_index.find_by_name("format_result")
        self.assertEqual(len(format_result), 1)
        self.assertEqual(format_result[0].kind, "function")
        self.assertEqual(format_result[0].docstring, "Format a result string.")
        self.assertEqual(format_result[0].calls, ("upper",))

        build_index = index.symbol_index.find_by_name("build_index")
        self.assertEqual(len(build_index), 1)
        self.assertEqual(build_index[0].kind, "function")
        self.assertEqual(build_index[0].decorators, ("traced",))
        self.assertEqual(build_index[0].docstring, "Build a tiny in-memory index.")
        self.assertEqual(build_index[0].calls, ("defaultdict", "format_result"))

        location_matches = index.symbol_index.find_by_location(Path("src/module.py"), 38)
        self.assertEqual({symbol.name for symbol in location_matches}, {"SampleWorker", "run", "result"})
        function_location_matches = index.symbol_index.find_by_location(Path("src/module.py"), 46)
        self.assertEqual({symbol.name for symbol in function_location_matches}, {"build_index", "index"})

        absolute_location_matches = index.symbol_index.find_by_location(LOCAL_REPO_FIXTURE / "src" / "module.py", 38)
        self.assertEqual({symbol.name for symbol in absolute_location_matches}, {"SampleWorker", "run", "result"})
        absolute_file_matches = index.symbol_index.find_in_file(LOCAL_REPO_FIXTURE / "src" / "module.py")
        self.assertTrue(any(symbol.name == "SampleWorker" for symbol in absolute_file_matches))

        self.assertEqual(index.module_graph.dependencies_of("src.graph_a"), ("src.graph_b",))
        self.assertEqual(index.module_graph.dependencies_of("src.graph_b"), ("src.graph_a",))
        self.assertEqual(index.module_graph.dependencies_of("src.auth"), ())
        self.assertEqual(index.module_graph.cycles(), (("src.graph_a", "src.graph_b"),))
        self.assertEqual(index.module_graph.dependents_of("src.graph_a"), ("src.graph_b",))

        call_graph = index.call_graph
        self.assertEqual(call_graph.callees_of("build_index"), ("defaultdict", "format_result"))
        self.assertEqual(call_graph.callees_of("SampleWorker.run"), ("format_result", "basename"))
        self.assertEqual(call_graph.callees_of("get_name"), ("describe",))
        self.assertEqual(call_graph.callers_of("format_result"), ("SampleWorker.run", "build_index"))
        self.assertEqual(call_graph.callers_of("get_name"), ("describe",))

        module_graph_json = json.loads(index.module_graph.to_json(indent=2))
        self.assertEqual(module_graph_json["cycles"], [["src.graph_a", "src.graph_b"]])
        self.assertIn({"from": "src.graph_a", "to": "src.graph_b"}, module_graph_json["edges"])

        call_graph_json = json.loads(call_graph.to_json(indent=2))
        self.assertIn({"from": "build_index", "to": "format_result"}, call_graph_json["edges"])
        self.assertIn({"from": "SampleWorker.run", "to": "format_result"}, call_graph_json["edges"])

        semantic_results = index.semantic_index.search("Where is authentication handled?", top_k=3)
        self.assertGreaterEqual(semantic_results[0].score, semantic_results[-1].score)
        self.assertEqual(semantic_results[0].chunk.path, Path("src/auth.py"))
        self.assertEqual(semantic_results[0].chunk.symbol_name, "authenticate_user")

        semantic_json = json.loads(index.semantic_index.to_json("Where is authentication handled?", top_k=3))
        self.assertEqual(semantic_json["query"], "Where is authentication handled?")
        self.assertEqual(semantic_json["results"][0]["chunk"]["path"], "src/auth.py")
        self.assertEqual(semantic_json["results"][0]["chunk"]["symbol_name"], "authenticate_user")

        self.assertEqual(guide.modified_at.tzinfo, timezone.utc)
        self.assertEqual(auth.modified_at.tzinfo, timezone.utc)
        self.assertEqual(module.modified_at.tzinfo, timezone.utc)
        self.assertEqual(graph_a.modified_at.tzinfo, timezone.utc)
        self.assertEqual(graph_b.modified_at.tzinfo, timezone.utc)
        self.assertGreater(guide.size, 0)
        self.assertGreater(auth.size, 0)
        self.assertGreater(module.size, 0)
        self.assertGreater(graph_a.size, 0)
        self.assertGreater(graph_b.size, 0)
