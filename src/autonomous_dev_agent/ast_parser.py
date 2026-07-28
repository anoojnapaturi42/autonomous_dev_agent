"""AST-based parsing of Python files without executing repository code."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .symbol_index import PythonFileIndex, PythonImport, PythonSymbol


@dataclass(slots=True)
class ParsedPythonFile:
    """Raw AST parse result before repository-level aggregation."""

    file_index: PythonFileIndex


class AstPythonParser:
    """Parse Python source into structured symbols and imports."""

    def parse(
        self,
        path: Path,
        source: str,
        *,
        size: int,
        modified_at: datetime,
    ) -> ParsedPythonFile:
        try:
            module = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            file_index = PythonFileIndex(
                path=path,
                size=size,
                modified_at=modified_at,
                module_docstring=None,
                imports=(),
                symbols=(),
                parse_error=str(exc),
            )
            return ParsedPythonFile(file_index=file_index)

        collector = _AstCollector(path)
        collector.collect_module(module)

        file_index = PythonFileIndex(
            path=path,
            size=size,
            modified_at=modified_at,
            module_docstring=ast.get_docstring(module),
            imports=tuple(collector.imports),
            symbols=tuple(collector.symbols),
            parse_error=None,
        )
        return ParsedPythonFile(file_index=file_index)


class _AstCollector:
    """Collect symbols from the AST without executing code."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self.imports: list[PythonImport] = []
        self.symbols: list[PythonSymbol] = []

    def collect_module(self, module: ast.Module) -> None:
        self._collect_body(module.body, scope_parts=(), container_kind="module")

    def _collect_body(
        self,
        body: Iterable[ast.stmt],
        *,
        scope_parts: tuple[str, ...],
        container_kind: str,
    ) -> None:
        for node in body:
            self._collect_statement(node, scope_parts=scope_parts, container_kind=container_kind)

    def _collect_statement(
        self,
        node: ast.stmt,
        *,
        scope_parts: tuple[str, ...],
        container_kind: str,
    ) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self.imports.append(self._build_import(node))
            return

        if isinstance(node, ast.ClassDef):
            self._record_class(node, scope_parts=scope_parts)
            self._collect_body(node.body, scope_parts=scope_parts + (node.name,), container_kind="class")
            return

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._record_function(node, scope_parts=scope_parts, container_kind=container_kind)
            self._collect_body(node.body, scope_parts=scope_parts + (node.name,), container_kind="function")
            return

        if isinstance(node, ast.Assign):
            self._record_assignment_targets(node.targets, scope_parts=scope_parts, line=node.lineno, end_line=node.end_lineno)
            return

        if isinstance(node, ast.AnnAssign):
            self._record_assignment_targets([node.target], scope_parts=scope_parts, line=node.lineno, end_line=node.end_lineno)
            return

        if isinstance(node, ast.AugAssign):
            self._record_assignment_targets([node.target], scope_parts=scope_parts, line=node.lineno, end_line=node.end_lineno)
            return

        if isinstance(node, (ast.For, ast.AsyncFor)):
            self._record_assignment_targets([node.target], scope_parts=scope_parts, line=node.lineno, end_line=node.end_lineno)
            self._collect_body(node.body, scope_parts=scope_parts, container_kind=container_kind)
            self._collect_body(node.orelse, scope_parts=scope_parts, container_kind=container_kind)
            return

        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    self._record_assignment_targets([item.optional_vars], scope_parts=scope_parts, line=node.lineno, end_line=node.end_lineno)
            self._collect_body(node.body, scope_parts=scope_parts, container_kind=container_kind)
            return

        if isinstance(node, ast.ExceptHandler):
            if isinstance(node.name, str):
                self._record_symbol(
                    name=node.name,
                    kind="variable",
                    scope_parts=scope_parts,
                    line=node.lineno,
                    end_line=_end_line(node),
                )
            self._collect_body(node.body, scope_parts=scope_parts, container_kind=container_kind)
            return

        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                self._collect_statement(child, scope_parts=scope_parts, container_kind=container_kind)

    def _record_class(self, node: ast.ClassDef, *, scope_parts: tuple[str, ...]) -> None:
        self.symbols.append(
            PythonSymbol(
                name=node.name,
                qualified_name=self._qualified_name(scope_parts, node.name),
                kind="class",
                path=self._path,
                line=node.lineno,
                end_line=_end_line(node),
                decorators=tuple(_decorator_name(decorator) for decorator in node.decorator_list),
                docstring=ast.get_docstring(node),
                bases=tuple(_expression_name(base) for base in node.bases),
            )
        )

    def _record_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        scope_parts: tuple[str, ...],
        container_kind: str,
    ) -> None:
        kind = "method" if container_kind == "class" else "function"
        calls = _collect_calls(node.body)
        self.symbols.append(
            PythonSymbol(
                name=node.name,
                qualified_name=self._qualified_name(scope_parts, node.name),
                kind=kind,
                path=self._path,
                line=node.lineno,
                end_line=_end_line(node),
                decorators=tuple(_decorator_name(decorator) for decorator in node.decorator_list),
                docstring=ast.get_docstring(node),
                calls=calls,
            )
        )

    def _record_assignment_targets(
        self,
        targets: Iterable[ast.expr],
        *,
        scope_parts: tuple[str, ...],
        line: int,
        end_line: int | None,
    ) -> None:
        for target in targets:
            for name in _extract_target_names(target):
                self._record_symbol(
                    name=name,
                    kind="variable",
                    scope_parts=scope_parts,
                    line=line,
                    end_line=end_line or line,
                )

    def _record_symbol(
        self,
        *,
        name: str,
        kind: str,
        scope_parts: tuple[str, ...],
        line: int,
        end_line: int,
    ) -> None:
        self.symbols.append(
            PythonSymbol(
                name=name,
                qualified_name=self._qualified_name(scope_parts, name),
                kind=kind,
                path=self._path,
                line=line,
                end_line=end_line,
            )
        )

    def _qualified_name(self, scope_parts: tuple[str, ...], name: str) -> str:
        parts = (*scope_parts, name)
        return ".".join(part for part in parts if part)

    def _build_import(self, node: ast.Import | ast.ImportFrom) -> PythonImport:
        targets = _import_targets(node)
        return PythonImport(
            statement=ast.unparse(node).strip(),
            module=node.module if isinstance(node, ast.ImportFrom) else None,
            names=tuple(alias.asname or alias.name for alias in node.names),
            line=node.lineno,
            end_line=_end_line(node),
            targets=targets,
        )


def _extract_target_names(target: ast.expr) -> tuple[str, ...]:
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, ast.Starred):
        return _extract_target_names(target.value)
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in target.elts:
            names.extend(_extract_target_names(element))
        return tuple(names)
    return ()


def _decorator_name(node: ast.expr) -> str:
    return ast.unparse(node).strip()


def _expression_name(node: ast.expr) -> str:
    return ast.unparse(node).strip()


def _import_targets(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)

    base = "." * node.level + (node.module or "")
    targets: list[str] = []
    for alias in node.names:
        if alias.name == "*":
            targets.append(base)
        elif base:
            targets.append(f"{base}.{alias.name}")
        else:
            targets.append(alias.name)
    return tuple(targets)


def _collect_calls(body: Iterable[ast.stmt]) -> tuple[str, ...]:
    collector = _CallCollector()
    collector.collect(body)
    return tuple(collector.calls)


class _CallCollector(ast.NodeVisitor):
    """Collect approximate call targets from a function body."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._seen: set[str] = set()

    def collect(self, body: Iterable[ast.stmt]) -> None:
        for statement in body:
            self.visit(statement)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_target_name(node.func)
        if name and name not in self._seen:
            self.calls.append(name)
            self._seen.add(name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        return


def _call_target_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ast.unparse(node).strip()


def _end_line(node: ast.AST) -> int:
    end_line = getattr(node, "end_lineno", None)
    return int(end_line) if end_line is not None else int(getattr(node, "lineno", 0))
