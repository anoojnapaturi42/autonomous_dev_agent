"""Typer-based command line interface for the scaffold."""

from __future__ import annotations

import typer

from .config import Settings, load_settings
from .logging_config import configure_logging

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


def main() -> None:
    """Entry point used by `python -m autonomous_dev_agent`."""

    app()
