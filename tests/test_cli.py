from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class CLITestCase(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        src_path = str(REPO_ROOT / "src")
        env["PYTHONPATH"] = (
            src_path if not env.get("PYTHONPATH") else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
        )
        return subprocess.run(
            [sys.executable, "-m", "autonomous_dev_agent", *args],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_help_starts_successfully(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Usage", result.stdout)

    def test_placeholder_agent_command_runs(self) -> None:
        result = self.run_cli("agent")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("agent logic is not implemented yet", result.stdout.lower())

