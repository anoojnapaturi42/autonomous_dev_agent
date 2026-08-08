"""Autonomous Dev Agent package."""

from .config import Settings, load_settings
from .autonomy import AutonomousAttempt, AutonomousEditContext, AutonomousEngineer, AutonomousRunResult
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
    "FailureSummary",
    "LocalRepository",
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
    "SafeEditingEngine",
    "SemanticChunk",
    "SemanticIndex",
    "SemanticSearchResult",
    "SpanEdit",
    "SimpleEmbeddingProvider",
    "SymbolIndex",
    "SymbolEdit",
    "Settings",
    "PytestTestRunner",
    "TestCaseResult",
    "TestRunResult",
    "configure_logging",
    "load_settings",
]

__version__ = "0.1.0"
