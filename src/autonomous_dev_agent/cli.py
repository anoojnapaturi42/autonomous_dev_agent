"""Typer-based command line interface for the scaffold."""

from __future__ import annotations

import json

import typer

from .autonomy import AutonomousEngineer
from .cloning import GitRepositoryCloner
from .config import Settings, load_settings
from .fix_generation import AnthropicLanguageModelClient, LLMEditStrategy
from .github_api import GitHubClient, parse_issue_reference
from .issue_fix import IssueFixWorkflow
from .memory import PersistentMemoryStore
from .repository import LocalRepository
from .logging_config import configure_logging
from .sandbox import DockerSandboxRunner, DockerNotAvailableError
from .tester import PytestTestRunner

app = typer.Typer(
    help="Autonomous Dev Agent command line interface.",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def _initialize(
    ctx: typer.Context,
) -> None:
    """Initialize shared runtime state for the CLI."""

    settings = configure_logging(load_settings())
    ctx.obj = settings
    if ctx.invoked_subcommand is None:
        typer.echo("Use `agent` to run the placeholder agent command.")


@app.command("agent")
def agent_command(ctx: typer.Context) -> None:
    """Placeholder agent command for the initial scaffold."""

    settings = ctx.obj if isinstance(ctx.obj, Settings) else load_settings()
    typer.echo(
        f"Agent scaffold ready for {settings.app_name} "
        f"in {settings.environment} mode."
    )
    typer.echo("Agent logic is not implemented yet.")


@app.command("clone")
def clone_command(
    source: str = typer.Argument(
        ..., help="A GitHub URL, owner/repo shorthand, SSH URL, or local path to clone."
    ),
    destination: str = typer.Option(
        None, help="Destination directory. Defaults to ./clones/<repo-name>-<id>."
    ),
    branch: str = typer.Option(None, help="Branch to check out instead of the default."),
) -> None:
    """Clone a repository (including private GitHub repos via GITHUB_TOKEN) and print its location."""

    settings = load_settings()
    cloner = GitRepositoryCloner(github_token=settings.github_token)
    result = cloner.clone(source, destination, branch=branch)
    typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))


@app.command("test")
def test_command(
    sandbox: bool = typer.Option(
        False,
        "--sandbox/--no-sandbox",
        help="Run the test suite inside an isolated Docker container instead of on the host.",
    ),
) -> None:
    """Detect pytest and run the repository test suite, returning structured JSON."""

    settings = load_settings()
    executor = None
    if sandbox:
        sandbox_runner = DockerSandboxRunner(
            image=settings.sandbox_image,
            memory_limit=settings.sandbox_memory_limit,
            cpu_limit=settings.sandbox_cpu_limit,
        )
        if not sandbox_runner.is_available():
            raise DockerNotAvailableError(
                "Docker is not available. Install Docker and ensure the daemon is running, "
                "or omit --sandbox to run tests on the host."
            )
        executor = sandbox_runner

    runner = PytestTestRunner(settings.project_root, executor=executor)
    result = runner.run()
    typer.echo(result.to_json())


@app.command("autonomous")
def autonomous_command(
    objective: str = typer.Option(
        "Improve the repository based on failed tests",
        help="The objective for the autonomous engineer to work toward.",
    ),
    retry_limit: int = typer.Option(
        2,
        min=0,
        help="Maximum number of edit retries after the initial test run.",
    ),
) -> None:
    """Run the autonomous edit-test-analyze-retry loop and emit structured JSON."""

    settings = load_settings()
    repository = LocalRepository(settings.project_root)
    edit_strategy = None
    if settings.anthropic_api_key:
        edit_strategy = LLMEditStrategy(
            AnthropicLanguageModelClient(
                api_key=settings.anthropic_api_key,
                model=settings.llm_model,
                max_output_tokens=settings.llm_max_output_tokens,
            )
        )
    else:
        typer.echo(
            "Warning: ANTHROPIC_API_KEY is not set, so no edit strategy is available. "
            "The loop will run once, report failures, and stop.",
            err=True,
        )
    engineer = AutonomousEngineer(
        repository,
        retry_limit=retry_limit,
        edit_strategy=edit_strategy,
        memory_store=PersistentMemoryStore(settings.memory_path),
    )
    result = engineer.run(objective, retry_limit=retry_limit)
    typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))


@app.command("rollback")
def rollback_command() -> None:
    """Restore the repository to the original checkout captured before edits."""

    settings = load_settings()
    repository = LocalRepository(settings.project_root)
    engineer = AutonomousEngineer(
        repository,
        memory_store=PersistentMemoryStore(settings.memory_path),
    )
    if engineer.rollback_workspace():
        typer.echo("Restored the original repository state.")
    else:
        typer.echo("No prepared Git workspace state was found to roll back.")


@app.command("fix-issue")
def fix_issue_command(
    issue: str = typer.Argument(
        ...,
        help="A GitHub issue URL, e.g. https://github.com/owner/repo/issues/123.",
    ),
    retry_limit: int = typer.Option(
        2, min=0, help="Maximum number of edit retries after the initial test run."
    ),
) -> None:
    """Fetch a GitHub issue, attempt to fix it, and open a pull request on success.

    Operates on the local repository checkout at the configured project root
    (see `clone` to obtain one). Requires ANTHROPIC_API_KEY to generate fixes
    and GITHUB_TOKEN with push/PR permissions on the target repository.
    """

    settings = load_settings()
    parsed = parse_issue_reference(issue)
    if parsed is None:
        typer.echo(
            f"Could not parse a GitHub issue reference from '{issue}'. "
            "Expected a URL like https://github.com/owner/repo/issues/123.",
            err=True,
        )
        raise typer.Exit(code=1)
    owner, repository_name, issue_number = parsed

    if not settings.anthropic_api_key:
        typer.echo(
            "Error: ANTHROPIC_API_KEY is required to generate fixes for an issue.", err=True
        )
        raise typer.Exit(code=1)
    if not settings.github_token:
        typer.echo(
            "Warning: GITHUB_TOKEN is not set. Fetching the issue may be rate-limited and "
            "pushing/opening a pull request will fail without it.",
            err=True,
        )

    repository = LocalRepository(settings.project_root)
    edit_strategy = LLMEditStrategy(
        AnthropicLanguageModelClient(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    )
    github_client = GitHubClient(token=settings.github_token)
    workflow = IssueFixWorkflow(
        repository,
        github_client,
        edit_strategy=edit_strategy,
        retry_limit=retry_limit,
        github_token=settings.github_token,
    )
    result = workflow.run(owner, repository_name, issue_number)
    typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if result.pull_request is None:
        raise typer.Exit(code=1)


def main() -> None:
    """Entry point used by `python -m autonomous_dev_agent`."""

    app()
