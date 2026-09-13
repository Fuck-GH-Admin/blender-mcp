# SPDX-License-Identifier: GPL-3.0-or-later
"""A deliberately conservative AST guard for fallback Blender Python.

This is a policy check, not an operating-system sandbox.  Structured tools are
trusted project code; only code supplied to ``execute_blender_code`` is checked.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

__all__ = ("SafeCodeViolation", "validate_blender_code")


_BLOCKED_IMPORT_ROOTS = frozenset({
    "builtins", "ctypes", "http", "importlib", "marshal", "os", "pathlib",
    "pickle", "requests", "runpy", "shlex", "shutil", "socket", "subprocess",
    "sys", "tempfile", "urllib",
})
_ALLOWED_IMPORT_ROOTS = frozenset({"bmesh", "bpy", "collections", "itertools", "json", "math", "mathutils", "typing"})
_BLOCKED_CALLS = frozenset({"__import__", "compile", "delattr", "eval", "exec", "getattr", "input", "open", "setattr"})
_BLOCKED_ATTRS = frozenset({
    "driver_add", "handlers", "register_class", "register_cli_command", "timers",
    "unregister_class", "unregister_cli_command",
})
_BLOCKED_BPY_OPS = frozenset({
    "wm.addon_disable", "wm.addon_enable", "wm.addon_install", "wm.addon_remove",
    "wm.quit_blender", "wm.read_factory_settings", "wm.read_factory_userpref",
    "wm.read_userpref", "script.python_file_run",
})


@dataclass(frozen=True)
class SafeCodeViolation(ValueError):
    """A source location and short reason for rejected fallback code."""

    line: int
    reason: str

    def __str__(self) -> str:
        return "Line {:d}: {:s}".format(self.line, self.reason)


def _attribute_path(node: ast.AST) -> str | None:
    """Return a dotted path for a simple attribute expression."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


class _SafetyVisitor(ast.NodeVisitor):
    def _reject(self, node: ast.AST, reason: str) -> None:
        raise SafeCodeViolation(getattr(node, "lineno", 1), reason)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            if root in _BLOCKED_IMPORT_ROOTS or root not in _ALLOWED_IMPORT_ROOTS:
                self._reject(node, "Import of {!r} is not allowed in safe mode".format(root))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        root = (node.module or "").split(".", 1)[0]
        if node.level or root in _BLOCKED_IMPORT_ROOTS or root not in _ALLOWED_IMPORT_ROOTS:
            self._reject(node, "Import from {!r} is not allowed in safe mode".format(node.module or "relative module"))

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if node.id in _BLOCKED_CALLS:
            self._reject(node, "{!r} is not allowed in safe mode".format(node.id))

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr.startswith("__") or node.attr in _BLOCKED_ATTRS:
            self._reject(node, "Access to attribute {!r} is not allowed in safe mode".format(node.attr))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        path = _attribute_path(node.func)
        operator = path.removeprefix("bpy.ops.") if path else None
        if operator in _BLOCKED_BPY_OPS:
            self._reject(node, "Operator {!r} is not allowed in safe mode".format(path))
        self.generic_visit(node)


def validate_blender_code(code: str) -> None:
    """Raise :class:`SafeCodeViolation` if *code* violates the safe policy."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as ex:
        raise SafeCodeViolation(ex.lineno or 1, ex.msg) from ex
    _SafetyVisitor().visit(tree)
