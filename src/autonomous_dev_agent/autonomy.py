"""Compatibility wrapper around the central orchestration engine."""

from __future__ import annotations

from .editing import EditRequest
from .memory import MemoryRecall, PersistentMemoryStore
from .orchestrator import (
    AutonomousAttempt,
    AutonomousEditContext,
    AutonomousOrchestrator,
    AutonomousRunResult,
    EditStrategy,
    OrchestrationProgressEvent,
    ProgressReporter,
)
from .checkpoint import OrchestrationCheckpointStore
from .repository import Repository
from .scanner import RepositoryScanner
from .tester import PytestTestRunner
from .workspace import GitWorkspaceManager


class AutonomousEngineer:
    """Compatibility facade that delegates to the central orchestrator."""

    def __init__(
        self,
        repository: Repository,
        *,
        retry_limit: int = 2,
        edit_strategy: EditStrategy | None = None,
        scanner: RepositoryScanner | None = None,
        tester: PytestTestRunner | None = None,
        memory_store: PersistentMemoryStore | None = None,
        checkpoint_store: OrchestrationCheckpointStore | None = None,
        workspace_manager: GitWorkspaceManager | None = None,
        progress_reporter: ProgressReporter | None = None,
        logger=None,
    ) -> None:
        self._orchestrator = AutonomousOrchestrator(
            repository,
            retry_limit=retry_limit,
            edit_strategy=edit_strategy,
            scanner=scanner,
            tester=tester,
            memory_store=memory_store,
            checkpoint_store=checkpoint_store,
            workspace_manager=workspace_manager,
            progress_reporter=progress_reporter,
            logger=logger,
        )

    def run(
        self,
        objective: str,
        *,
        retry_limit: int | None = None,
        top_k: int = 5,
        edit_strategy: EditStrategy | None = None,
    ) -> AutonomousRunResult:
        return self._orchestrator.run(
            objective,
            retry_limit=retry_limit,
            top_k=top_k,
            edit_strategy=edit_strategy,
        )

    def rollback_workspace(self) -> bool:
        return self._orchestrator.rollback_workspace()


__all__ = [
    "AutonomousAttempt",
    "AutonomousEditContext",
    "AutonomousEngineer",
    "AutonomousRunResult",
    "EditStrategy",
    "EditRequest",
    "MemoryRecall",
    "OrchestrationProgressEvent",
    "PersistentMemoryStore",
    "ProgressReporter",
]
