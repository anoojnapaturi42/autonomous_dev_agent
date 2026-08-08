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
    memory_path: Path
    debug: bool
    github_token: str | None
    sandbox_enabled: bool
    sandbox_image: str
    sandbox_memory_limit: str
    sandbox_cpu_limit: str
    sandbox_timeout_seconds: int
    anthropic_api_key: str | None
    llm_model: str
    llm_max_output_tokens: int


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
        memory_path=_resolve_path(
            env.get("AUTONOMOUS_DEV_AGENT_MEMORY_PATH"),
            default=root / ".autonomous_dev_agent" / "memory.json",
            base=root,
        ),
        debug=_get_bool(env.get("AUTONOMOUS_DEV_AGENT_DEBUG")),
        github_token=env.get("GITHUB_TOKEN") or None,
        sandbox_enabled=_get_bool(env.get("AUTONOMOUS_DEV_AGENT_SANDBOX_ENABLED")),
        sandbox_image=env.get("AUTONOMOUS_DEV_AGENT_SANDBOX_IMAGE", "python:3.11-slim"),
        sandbox_memory_limit=env.get("AUTONOMOUS_DEV_AGENT_SANDBOX_MEMORY", "512m"),
        sandbox_cpu_limit=env.get("AUTONOMOUS_DEV_AGENT_SANDBOX_CPUS", "1"),
        sandbox_timeout_seconds=int(env.get("AUTONOMOUS_DEV_AGENT_SANDBOX_TIMEOUT", "300")),
        anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
        llm_model=env.get("AUTONOMOUS_DEV_AGENT_LLM_MODEL", "claude-sonnet-4-6"),
        llm_max_output_tokens=int(env.get("AUTONOMOUS_DEV_AGENT_LLM_MAX_TOKENS", "8000")),
    )


def _resolve_path(value: str | None, *, default: Path, base: Path) -> Path:
    candidate = Path(value).expanduser() if value else default
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()
