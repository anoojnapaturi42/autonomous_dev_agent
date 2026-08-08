from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from autonomous_dev_agent.github_api import GitHubIssue, PullRequestResult
from autonomous_dev_agent.issue_fix import IssueFixWorkflow
from autonomous_dev_agent.orchestrator import AutonomousRunResult
from autonomous_dev_agent.tester import FailureSummary, TestRunResult
from autonomous_dev_agent.workspace import GitWorkspaceState


REPO_ROOT = Path(__file__).resolve().parents[1]


class _FakeRepository:
    root = REPO_ROOT


class _FakeGitHubClient:
    def __init__(self, issue: GitHubIssue, pull_request: PullRequestResult | None = None) -> None:
        self._issue = issue
        self._pull_request = pull_request
        self.create_pull_request_calls: list[dict[str, object]] = []

    def fetch_issue(self, owner: str, repository: str, number: int) -> GitHubIssue:
        return self._issue

    def create_pull_request(self, owner, repository, *, head, base, title, body):  # noqa: ANN001
        self.create_pull_request_calls.append(
            {"owner": owner, "repository": repository, "head": head, "base": base, "title": title, "body": body}
        )
        assert self._pull_request is not None
        return self._pull_request


class _FakeOrchestrator:
    def __init__(self, run_result: AutonomousRunResult) -> None:
        self._run_result = run_result
        self.run_calls: list[dict[str, object]] = []

    def run(self, objective: str, *, retry_limit: int) -> AutonomousRunResult:
        self.run_calls.append({"objective": objective, "retry_limit": retry_limit})
        return self._run_result


class _FakeWorkspaceManager:
    def __init__(self, state: GitWorkspaceState | None, push_result: bool = True) -> None:
        self._state = state
        self._push_result = push_result
        self.push_calls: list[dict[str, object]] = []

    def load_state(self) -> GitWorkspaceState | None:
        return self._state

    def push(self, *, branch: str, remote: str = "origin", token: str | None = None) -> bool:
        self.push_calls.append({"branch": branch, "remote": remote, "token": token})
        return self._push_result


def _make_issue(number: int = 42) -> GitHubIssue:
    return GitHubIssue(
        owner="octocat",
        repository="Hello-World",
        number=number,
        title="Crash on startup",
        body="Steps to reproduce...",
        html_url=f"https://github.com/octocat/Hello-World/issues/{number}",
        labels=("bug",),
    )


def _make_run_result(*, succeeded: bool, stop_reason: str = "tests_passed") -> AutonomousRunResult:
    test_result = TestRunResult(
        runner="pytest",
        exit_code=0 if succeeded else 1,
        success=succeeded,
        stdout="",
        stderr="",
        command=("python", "-m", "pytest"),
        cwd=REPO_ROOT,
    )
    return AutonomousRunResult(
        objective="Fix issue #42",
        retry_limit=2,
        succeeded=succeeded,
        stop_reason=stop_reason,
        attempts=(),
        final_test_result=test_result,
        final_failure_summary=FailureSummary(total_failures=0, root_causes=(), failures=()),
    )


class IssueFixWorkflowTestCase(unittest.TestCase):
    def test_opens_pull_request_when_fix_succeeds(self) -> None:
        issue = _make_issue()
        pull_request = PullRequestResult(number=99, html_url="https://github.com/o/r/pull/99", title="Fix #42")
        github_client = _FakeGitHubClient(issue, pull_request)
        run_result = _make_run_result(succeeded=True)
        orchestrator = _FakeOrchestrator(run_result)
        state = GitWorkspaceState(
            repository_root=REPO_ROOT,
            original_branch="main",
            original_head="abc123",
            temporary_branch="autonomous-dev-agent/fix-42",
            prepared_at=datetime.now(timezone.utc),
        )
        workspace_manager = _FakeWorkspaceManager(state)

        workflow = IssueFixWorkflow(
            _FakeRepository(),
            github_client,
            github_token="tok",
            workspace_manager=workspace_manager,
            orchestrator_factory=lambda *a, **k: orchestrator,
        )

        result = workflow.run("octocat", "Hello-World", 42)

        self.assertTrue(result.pushed)
        self.assertIsNotNone(result.pull_request)
        self.assertEqual(result.pull_request.number, 99)
        self.assertEqual(workspace_manager.push_calls[0]["branch"], "autonomous-dev-agent/fix-42")
        self.assertEqual(workspace_manager.push_calls[0]["token"], "tok")
        pr_call = github_client.create_pull_request_calls[0]
        self.assertEqual(pr_call["head"], "autonomous-dev-agent/fix-42")
        self.assertEqual(pr_call["base"], "main")
        self.assertIn("Closes #42", pr_call["body"])
        # The orchestrator must receive the issue's title/body as its objective.
        self.assertIn("Crash on startup", orchestrator.run_calls[0]["objective"])

    def test_does_not_push_or_open_pr_when_run_fails(self) -> None:
        issue = _make_issue()
        github_client = _FakeGitHubClient(issue)
        run_result = _make_run_result(succeeded=False, stop_reason="retry_limit_exhausted")
        orchestrator = _FakeOrchestrator(run_result)
        workspace_manager = _FakeWorkspaceManager(state=None)

        workflow = IssueFixWorkflow(
            _FakeRepository(),
            github_client,
            workspace_manager=workspace_manager,
            orchestrator_factory=lambda *a, **k: orchestrator,
        )

        result = workflow.run("octocat", "Hello-World", 42)

        self.assertFalse(result.pushed)
        self.assertIsNone(result.pull_request)
        self.assertEqual(workspace_manager.push_calls, [])
        self.assertIn("retry_limit_exhausted", result.message)

    def test_reports_clearly_when_no_workspace_branch_was_prepared(self) -> None:
        issue = _make_issue()
        github_client = _FakeGitHubClient(issue)
        run_result = _make_run_result(succeeded=True)
        orchestrator = _FakeOrchestrator(run_result)
        workspace_manager = _FakeWorkspaceManager(state=None)

        workflow = IssueFixWorkflow(
            _FakeRepository(),
            github_client,
            workspace_manager=workspace_manager,
            orchestrator_factory=lambda *a, **k: orchestrator,
        )

        result = workflow.run("octocat", "Hello-World", 42)

        self.assertFalse(result.pushed)
        self.assertIsNone(result.pull_request)
        self.assertIn("no git workspace branch", result.message)

    def test_reports_clearly_when_push_fails(self) -> None:
        issue = _make_issue()
        github_client = _FakeGitHubClient(issue)
        run_result = _make_run_result(succeeded=True)
        orchestrator = _FakeOrchestrator(run_result)
        state = GitWorkspaceState(
            repository_root=REPO_ROOT,
            original_branch="main",
            original_head="abc123",
            temporary_branch="autonomous-dev-agent/fix-42",
            prepared_at=datetime.now(timezone.utc),
        )
        workspace_manager = _FakeWorkspaceManager(state, push_result=False)

        workflow = IssueFixWorkflow(
            _FakeRepository(),
            github_client,
            workspace_manager=workspace_manager,
            orchestrator_factory=lambda *a, **k: orchestrator,
        )

        result = workflow.run("octocat", "Hello-World", 42)

        self.assertFalse(result.pushed)
        self.assertIsNone(result.pull_request)
        self.assertEqual(github_client.create_pull_request_calls, [])
        self.assertIn("pushing", result.message)


if __name__ == "__main__":
    unittest.main()
