"""Logging configuration helpers for the scaffold."""

from __future__ import annotations

import logging
from logging.config import dictConfig
import sys
from typing import Any

from .config import Settings, load_settings


def build_logging_config(settings: Settings) -> dict[str, Any]:
    """Return a standard library logging configuration dictionary."""

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": settings.log_level,
                "stream": sys.__stderr__,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": settings.log_level,
        },
    }


def configure_logging(settings: Settings | None = None) -> Settings:
    """Configure process logging and return the active settings."""

    active_settings = settings or load_settings()
    dictConfig(build_logging_config(active_settings))
    logging.getLogger(__name__).debug(
        "Logging configured for %s", active_settings.app_name
    )
    return active_settings
