"""Ties together GitHub issue fetching, the autonomous fix loop, and PR creation.

This is orchestration glue: it does not talk to GitHub's HTTP API directly
(that's `github_api.py`) and it does not run the edit-test-retry loop itself
(that's `orchestrator.py`). It just sequences them:

    fetch issue -> run autonomous loop with the issue as the objective
    -> if it succeeded, push the branch and open a pull request

Kept as its own module (rather than folded into cli.py) so the sequencing
logic can be unit-tested with fakes for the GitHub client, the orchestrator,
and the workspace manager, without invoking Typer or a real subprocess.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .github_api import GitHubClient, GitHubIssue, PullRequestResult
from .orchestrator import AutonomousOrchestrator, AutonomousRunResult, EditStrategy
from .repository import Repository
from .workspace import GitWorkspaceManager


@dataclass(frozen=True, slots=True)
class IssueFixResult:
    """Structured outcome of attempting to fix a single GitHub issue."""

    issue: GitHubIssue
    run_result: AutonomousRunResult
    pull_request: PullRequestResult | None
    pushed: bool
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "issue": self.issue.to_dict(),
            "run_result": self.run_result.to_dict(),
            "pull_request": self.pull_request.to_dict() if self.pull_request is not None else None,
            "pushed": self.pushed,
            "message": self.message,
        }


class _OrchestratorFactory(Protocol):
    def __call__(
        self,
        repository: Repository,
        *,
        retry_limit: int,
        edit_strategy: EditStrategy | None,
        workspace_manager: GitWorkspaceManager,
    ) -> AutonomousOrchestrator: ...


def _default_orchestrator_factory(
    repository: Repository,
    *,
    retry_limit: int,
    edit_strategy: EditStrategy | None,
    workspace_manager: GitWorkspaceManager,
) -> AutonomousOrchestrator:
    return AutonomousOrchestrator(
        repository,
        retry_limit=retry_limit,
        edit_strategy=edit_strategy,
        workspace_manager=workspace_manager,
    )


class IssueFixWorkflow:
    """Fetches a GitHub issue, attempts to fix it, and opens a PR on success."""

    def __init__(
        self,
        repository: Repository,
        github_client: GitHubClient,
        *,
        edit_strategy: EditStrategy | None = None,
        retry_limit: int = 2,
        github_token: str | None = None,
        workspace_manager: GitWorkspaceManager | None = None,
        orchestrator_factory: _OrchestratorFactory = _default_orchestrator_factory,
        default_base_branch: str = "main",
    ) -> None:
        self._repository = repository
        self._github_client = github_client
        self._edit_strategy = edit_strategy
        self._retry_limit = retry_limit
        self._github_token = github_token
        self._workspace_manager = workspace_manager or GitWorkspaceManager(repository.root)
        self._orchestrator_factory = orchestrator_factory
        self._default_base_branch = default_base_branch

    def run(self, owner: str, repository_name: str, issue_number: int) -> IssueFixResult:
        issue = self._github_client.fetch_issue(owner, repository_name, issue_number)

        orchestrator = self._orchestrator_factory(
            self._repository,
            retry_limit=self._retry_limit,
            edit_strategy=self._edit_strategy,
            workspace_manager=self._workspace_manager,
        )
        run_result = orchestrator.run(issue.objective, retry_limit=self._retry_limit)

        if not run_result.succeeded:
            return IssueFixResult(
                issue=issue,
                run_result=run_result,
                pull_request=None,
                pushed=False,
                message=(
                    f"Autonomous run did not succeed (stop reason: {run_result.stop_reason}); "
                    "no branch was pushed and no pull request was opened."
                ),
            )

        state = self._workspace_manager.load_state()
        if state is None or not state.temporary_branch:
            return IssueFixResult(
                issue=issue,
                run_result=run_result,
                pull_request=None,
                pushed=False,
                message=(
                    "The fix succeeded but no git workspace branch was prepared "
                    "(is this repository a git checkout?); nothing was pushed."
                ),
            )

        pushed = self._workspace_manager.push(
            branch=state.temporary_branch, token=self._github_token
        )
        if not pushed:
            return IssueFixResult(
                issue=issue,
                run_result=run_result,
                pull_request=None,
                pushed=False,
                message=(
                    f"The fix succeeded locally on branch '{state.temporary_branch}' but pushing "
                    "it to the remote failed. Push manually and open a pull request by hand."
                ),
            )

        pull_request = self._github_client.create_pull_request(
            owner,
            repository_name,
            head=state.temporary_branch,
            base=state.original_branch or self._default_base_branch,
            title=f"Fix #{issue.number}: {issue.title}",
            body=self._build_pr_body(issue, run_result),
        )
        return IssueFixResult(
            issue=issue,
            run_result=run_result,
            pull_request=pull_request,
            pushed=True,
            message="Pull request opened.",
        )

    def _build_pr_body(self, issue: GitHubIssue, run_result: AutonomousRunResult) -> str:
        attempt_count = len(run_result.attempts)
        return (
            f"Closes #{issue.number}.\n\n"
            f"{issue.body.strip()}\n\n"
            "---\n"
            f"Opened automatically by autonomous-dev-agent after {attempt_count} attempt(s). "
            "Please review the diff carefully before merging."
        )
