"""Embedding provider abstractions for semantic search."""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from typing import Iterable


_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SYNONYMS = {
    "authentication": "auth",
    "authenticate": "auth",
    "authenticated": "auth",
    "authenticating": "auth",
    "authorization": "authz",
    "authorize": "authz",
    "handled": "handle",
    "handling": "handle",
    "handler": "handle",
    "login": "auth",
    "signin": "auth",
    "sign": "auth",
    "user": "user",
    "users": "user",
}


class EmbeddingProvider(ABC):
    """Abstract provider interface for text embeddings."""

    @abstractmethod
    def embed(self, text: str) -> tuple[float, ...]:
        """Convert text into an embedding vector."""


@dataclass(slots=True)
class SimpleEmbeddingProvider(EmbeddingProvider):
    """Deterministic local embedding provider for semantic search."""

    dimension: int = 128

    def embed(self, text: str) -> tuple[float, ...]:
        counts = Counter(_normalize_token(token) for token in _TOKEN_PATTERN.findall(text))
        vector = [0.0] * self.dimension
        for token, weight in counts.items():
            if not token:
                continue
            index = _stable_bucket(token, self.dimension)
            vector[index] += float(weight)
        return _normalize_vector(vector)


@dataclass(frozen=True, slots=True)
class EmbeddingProviderConfig:
    """Configuration for semantic embedding generation."""

    provider: str = "simple"
    dimension: int = 128


def create_embedding_provider(config: EmbeddingProviderConfig | None = None) -> EmbeddingProvider:
    """Create an embedding provider from configuration."""

    active_config = config or EmbeddingProviderConfig()
    if active_config.provider in {"simple", "hash", "hashed"}:
        return SimpleEmbeddingProvider(dimension=active_config.dimension)
    raise ValueError(f"Unknown embedding provider: {active_config.provider}")


def _normalize_token(token: str) -> str:
    token = token.lower()
    token = _SYNONYMS.get(token, token)
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > 4 and token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    return token


def _stable_bucket(token: str, dimension: int) -> int:
    value = 0
    for char in token:
        value = (value * 33 + ord(char)) & 0xFFFFFFFF
    return value % dimension


def _normalize_vector(vector: Iterable[float]) -> tuple[float, ...]:
    materialized = list(vector)
    norm = math.sqrt(sum(value * value for value in materialized))
    if not norm:
        return tuple(0.0 for _ in materialized)
    return tuple(value / norm for value in materialized)

