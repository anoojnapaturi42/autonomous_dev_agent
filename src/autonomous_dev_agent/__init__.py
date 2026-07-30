"""Autonomous Dev Agent package."""

from .config import Settings, load_settings
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
from .tester import PytestTestRunner, TestRunResult

__all__ = [
    "AstPythonParser",
    "CallGraph",
    "create_embedding_provider",
    "EmbeddingProvider",
    "EmbeddingProviderConfig",
    "EditPreview",
    "EditResult",
    "FileEdit",
    "ExecutionPlan",
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
    "TestRunResult",
    "configure_logging",
    "load_settings",
]

__version__ = "0.1.0"
