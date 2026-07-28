"""Configuration management for the agent scaffold."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    app_name: str
    environment: str
    log_level: str
    embedding_provider: str
    embedding_dimension: int
    project_root: Path
    debug: bool


def _get_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(
    environ: Mapping[str, str] | None = None,
    project_root: Path | None = None,
) -> Settings:
    """Load settings from the environment with sensible defaults."""

    env = os.environ if environ is None else environ
    root = project_root or Path(env.get("AUTONOMOUS_DEV_AGENT_ROOT", Path.cwd()))

    return Settings(
        app_name=env.get("AUTONOMOUS_DEV_AGENT_APP_NAME", "autonomous-dev-agent"),
        environment=env.get("AUTONOMOUS_DEV_AGENT_ENV", "development"),
        log_level=env.get("AUTONOMOUS_DEV_AGENT_LOG_LEVEL", "INFO").upper(),
        embedding_provider=env.get("AUTONOMOUS_DEV_AGENT_EMBEDDING_PROVIDER", "simple"),
        embedding_dimension=int(env.get("AUTONOMOUS_DEV_AGENT_EMBEDDING_DIMENSION", "128")),
        project_root=root.resolve(),
        debug=_get_bool(env.get("AUTONOMOUS_DEV_AGENT_DEBUG")),
    )
