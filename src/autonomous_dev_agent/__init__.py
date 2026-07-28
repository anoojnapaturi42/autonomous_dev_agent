"""Autonomous Dev Agent package."""

from .config import Settings, load_settings
from .logging_config import configure_logging
from .ast_parser import AstPythonParser, ParsedPythonFile
from .graphs import CallGraph, ModuleDependencyGraph
from .embeddings import EmbeddingProvider, EmbeddingProviderConfig, SimpleEmbeddingProvider, create_embedding_provider
from .repository import LocalRepository, Repository
from .scanner import RepositoryScanner
from .semantic import SemanticChunk, SemanticIndex, SemanticSearchResult
from .symbol_index import PythonFileIndex, PythonImport, PythonSymbol, RepositoryIndex, SymbolIndex

__all__ = [
    "AstPythonParser",
    "CallGraph",
    "create_embedding_provider",
    "EmbeddingProvider",
    "EmbeddingProviderConfig",
    "LocalRepository",
    "ModuleDependencyGraph",
    "PythonFileIndex",
    "PythonImport",
    "PythonSymbol",
    "ParsedPythonFile",
    "Repository",
    "RepositoryIndex",
    "RepositoryScanner",
    "SemanticChunk",
    "SemanticIndex",
    "SemanticSearchResult",
    "SimpleEmbeddingProvider",
    "SymbolIndex",
    "Settings",
    "configure_logging",
    "load_settings",
]

__version__ = "0.1.0"
