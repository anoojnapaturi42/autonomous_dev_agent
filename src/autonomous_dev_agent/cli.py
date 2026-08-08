"""Typer-based command line interface for the scaffold."""

from __future__ import annotations

import json

import typer

from .autonomy import AutonomousEngineer
from .config import Settings, load_settings
from .repository import LocalRepository
from .logging_config import configure_logging
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


@app.command("test")
def test_command() -> None:
    """Detect pytest and run the repository test suite, returning structured JSON."""

    runner = PytestTestRunner(load_settings().project_root)
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
    engineer = AutonomousEngineer(repository, retry_limit=retry_limit)
    result = engineer.run(objective, retry_limit=retry_limit)
    typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))


def main() -> None:
    """Entry point used by `python -m autonomous_dev_agent`."""

    app()
