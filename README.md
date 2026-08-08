# Autonomous Dev Agent

An experimental autonomous software engineering agent scaffold built as a modern Python package.

The project currently focuses on repository understanding and safe code modification:

- repository abstraction for local Git checkouts
- recursive Python file scanning
- safe AST parsing without executing repository code
- symbol indexing by name and file location
- module dependency and call graphs
- semantic chunking and search
- execution planning before edits
- diff-first file editing with Git-style unified diffs
- an autonomous edit-test-analyze-retry loop with configurable retry limits
- Typer-based CLI entry point

## Status

The repository analysis, planning, safe editing, and autonomous retry loop are in place. The `agent` command is still a placeholder, but the `test` and `autonomous` commands now expose the structured test execution and repair loop.

## Quickstart

```bash
python -m autonomous_dev_agent --help
python -m autonomous_dev_agent agent
python -m autonomous_dev_agent autonomous
```

If you install the package, the console script is also available:

```bash
autonomous-dev-agent agent
```

## What It Does

### Repository handling

`LocalRepository` provides a safe interface for local Git repositories. It:

- validates that the target path exists and looks like a Git checkout
- lists repository files recursively
- ignores common cache, virtual environment, and build directories
- reads file contents through a controlled interface

### Python scanning and AST parsing

`RepositoryScanner` walks every Python file in the repository and builds structured metadata for each file.

The parser uses Python's built-in `ast` module only, so repository code is never executed. It extracts:

- imports
- classes
- functions
- methods
- variables
- decorators
- docstrings
- inheritance
- line numbers and source spans

### Symbol indexing

The repository index exposes a `SymbolIndex` that supports lookups by:

- symbol name
- file location
- file path

### Graphs

The scan result also includes:

- a module dependency graph derived from imports
- cycle detection for module dependencies
- an approximate call graph derived from AST call expressions
- JSON export for graph visualization or downstream tools

### Semantic search

Python code is chunked into logical units such as classes and functions and embedded with a pluggable embedding provider.

Semantic search returns ranked results for natural-language queries such as:

```text
Where is authentication handled?
```

### Planning

`PlanningModule` drafts an execution plan before edits are made. Plans include:

- target files
- rationale
- expected modifications
- risks
- confidence

### Safe editing

`SafeEditingEngine` applies changes through a preview-first workflow:

- emits Git-style unified diffs before writing
- prefers AST-aware symbol edits where possible
- falls back to explicit file-range edits when needed
- preserves surrounding comments and formatting as much as possible

## Project Layout

```text
src/autonomous_dev_agent/
  ast_parser.py       # Safe AST parsing and symbol extraction
  cli.py              # Typer command line interface
  config.py           # Environment-based configuration
  editing.py          # Diff-first safe editing engine
  embeddings.py       # Embedding provider abstraction
  graphs.py           # Module dependency and call graphs
  logging_config.py   # Logging setup
  planning.py         # Execution plan generation
  repository.py       # Repository abstractions and local provider
  scanner.py          # Repository-wide Python indexing
  semantic.py         # Semantic chunking and search
  symbol_index.py     # Structured symbols and file indexes
```

## Configuration

Settings are loaded from environment variables:

- `AUTONOMOUS_DEV_AGENT_APP_NAME`
- `AUTONOMOUS_DEV_AGENT_ENV`
- `AUTONOMOUS_DEV_AGENT_LOG_LEVEL`
- `AUTONOMOUS_DEV_AGENT_DEBUG`
- `AUTONOMOUS_DEV_AGENT_ROOT`
- `AUTONOMOUS_DEV_AGENT_EMBEDDING_PROVIDER`
- `AUTONOMOUS_DEV_AGENT_EMBEDDING_DIMENSION`

Defaults are chosen so the project works locally without extra setup.

## Development

Install dependencies with your preferred workflow, then run the tests:

```bash
python -m unittest discover -s tests -v
```

The test suite covers:

- CLI startup
- repository discovery and file reading
- repository scanning and AST metadata
- semantic search and planning
- safe diff-first editing

## Package Entry Points

- `python -m autonomous_dev_agent`
- `python -m autonomous_dev_agent agent`
- `python -m autonomous_dev_agent autonomous`
- `python -m autonomous_dev_agent test`
- `autonomous-dev-agent`

## Notes

The project is intentionally structured to keep the repository analysis layer separate from the future agent execution layer. That makes it easier to add new repository providers, embedding backends, and edit strategies later.
