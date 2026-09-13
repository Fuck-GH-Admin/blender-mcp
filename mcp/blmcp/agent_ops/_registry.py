# SPDX-License-Identifier: GPL-3.0-or-later
"""Registry of structured operations callable by ``scene_batch``.

Only tools that follow the compact structured contract register themselves
here; the registry therefore doubles as the batch whitelist.  Escape hatches
and raw Python are never registered.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

__all__ = ("all_operations", "get_operation", "register_operation", "reset_registry")

_OPERATIONS: dict[str, Callable[..., dict[str, Any]]] = {}


def register_operation(name: str, operation: Callable[..., dict[str, Any]]) -> None:
    """Add one structured operation to the batch whitelist."""
    _OPERATIONS[name] = operation


def get_operation(name: str) -> Callable[..., dict[str, Any]] | None:
    return _OPERATIONS.get(name)


def all_operations() -> tuple[str, ...]:
    return tuple(sorted(_OPERATIONS))


def reset_registry() -> None:
    """Clear registrations when a new server is built."""
    _OPERATIONS.clear()
