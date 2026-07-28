from __future__ import annotations

import json
import unittest
from pathlib import Path

from autonomous_dev_agent.planning import PlanningModule
from autonomous_dev_agent.repository import LocalRepository
from autonomous_dev_agent.scanner import RepositoryScanner


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_REPO_FIXTURE = REPO_ROOT / "eval_repos" / "toy"


class PlanningModuleTestCase(unittest.TestCase):
    def test_drafts_execution_plan_from_semantic_search(self) -> None:
        repository = LocalRepository(LOCAL_REPO_FIXTURE)
        repository_index = RepositoryScanner(repository).scan()
        planner = PlanningModule(repository_index)

        plan = planner.draft_execution_plan("Where is authentication handled?", top_k=5)

        self.assertEqual(plan.objective, "Where is authentication handled?")
        self.assertGreaterEqual(len(plan.steps), 1)
        self.assertEqual(plan.target_files[0], Path("src/auth.py"))
        self.assertEqual(plan.steps[0].target_file, Path("src/auth.py"))
        self.assertIn("authenticate_user", plan.steps[0].rationale)
        self.assertTrue(plan.steps[0].expected_modifications)
        self.assertTrue(plan.steps[0].risks)
        self.assertGreater(plan.steps[0].confidence, 0.0)
        self.assertLessEqual(plan.steps[0].confidence, 1.0)

        plan_json = json.loads(plan.to_json(indent=2))
        self.assertEqual(plan_json["objective"], "Where is authentication handled?")
        self.assertEqual(plan_json["target_files"][0], "src/auth.py")
        self.assertEqual(plan_json["steps"][0]["target_file"], "src/auth.py")
        self.assertIn("rationale", plan_json["steps"][0])
        self.assertIn("expected_modifications", plan_json["steps"][0])
        self.assertIn("risks", plan_json["steps"][0])
        self.assertIn("confidence", plan_json["steps"][0])
        self.assertGreater(plan_json["overall_confidence"], 0.0)

