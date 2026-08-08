"""Autonomous Dev Agent package."""

from .config import Settings, load_settings
from .autonomy import AutonomousAttempt, AutonomousEditContext, AutonomousEngineer, AutonomousRunResult
from .checkpoint import OrchestrationCheckpoint, OrchestrationCheckpointStore
from .orchestrator import AutonomousOrchestrator, OrchestrationProgressEvent, ProgressReporter
from .memory import (
    FailureMemoryRecord,
    MemoryRecall,
    MemoryState,
    PersistentMemoryStore,
    RepositorySummaryRecord,
    SuccessfulFixRecord,
    TaskMemoryRecord,
)
from .workspace import GitWorkspaceManager, GitWorkspaceState
from .logging_config import configure_logging
from .ast_parser import AstPythonParser, ParsedPythonFile
from .graphs import CallGraph, ModuleDependencyGraph
from .embeddings import EmbeddingProvider, EmbeddingProviderConfig, SimpleEmbeddingProvider, create_embedding_provider
from .editing import EditPreview, EditResult, FileEdit, SafeEditingEngine, SpanEdit, SymbolEdit
from .repository import LocalRepository, Repository
from .planning import ExecutionPlan, PlanStep, PlanningModule
from .scanner import RepositoryScanner
from .semantic import SemanticChunk, SemanticIndex, SemanticSearchResult
from .symbol_index import PythonFileIndex, PythonImport, PythonSymbol, RepositoryIndex, SymbolIndex
from .tester import PytestTestRunner, TestCaseResult, TestRunResult
from .tester import FailureAnalysis, FailureAnalysisResult, FailureCauseSummary, FailureSummary

__all__ = [
    "AstPythonParser",
    "AutonomousAttempt",
    "AutonomousEditContext",
    "AutonomousEngineer",
    "AutonomousRunResult",
    "AutonomousOrchestrator",
    "CallGraph",
    "create_embedding_provider",
    "EmbeddingProvider",
    "EmbeddingProviderConfig",
    "EditPreview",
    "EditResult",
    "FileEdit",
    "ExecutionPlan",
    "FailureAnalysis",
    "FailureAnalysisResult",
    "FailureCauseSummary",
    "FailureMemoryRecord",
    "FailureSummary",
    "LocalRepository",
    "MemoryRecall",
    "MemoryState",
    "GitWorkspaceManager",
    "GitWorkspaceState",
    "ModuleDependencyGraph",
    "PlanStep",
    "PlanningModule",
    "PythonFileIndex",
    "PythonImport",
    "PythonSymbol",
    "ParsedPythonFile",
    "Repository",
    "RepositoryIndex",
    "RepositoryScanner",
    "RepositorySummaryRecord",
    "SafeEditingEngine",
    "SemanticChunk",
    "SemanticIndex",
    "SemanticSearchResult",
    "SpanEdit",
    "SimpleEmbeddingProvider",
    "SuccessfulFixRecord",
    "SymbolIndex",
    "SymbolEdit",
    "Settings",
    "OrchestrationProgressEvent",
    "PersistentMemoryStore",
    "ProgressReporter",
    "OrchestrationCheckpoint",
    "OrchestrationCheckpointStore",
    "TaskMemoryRecord",
    "PytestTestRunner",
    "TestCaseResult",
    "TestRunResult",
    "configure_logging",
    "load_settings",
]

__version__ = "0.1.0"
