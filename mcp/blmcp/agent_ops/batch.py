# SPDX-License-Identifier: GPL-3.0-or-later
"""Sequential batch execution of registered structured operations (AX-03)."""

from __future__ import annotations

__all__ = ('register',)

import time
from typing import Any

from blmcp.agent_ops._registry import all_operations, get_operation
from blmcp.metrics import record_tool_call
from blmcp.state import get_runtime
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_BATCH_LIMIT = 32


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="Scene Batch", destructiveHint=True, idempotentHint=False))
    def scene_batch(
        operations: list[dict[str, Any]],
        stop_on_error: bool = True,
    ) -> dict[str, object]:
        """Run a sequence of structured operations in one round trip. Each item is ``{"tool": name, "arguments": {...}}``; execution stops at the first failing operation unless ``stop_on_error`` is false. Only structured operations are allowed; every item may carry its own ``request_id`` for retry safety."""
        arguments = locals().copy()
        started = time.monotonic()

        def _error(code: str, message: str) -> dict[str, object]:
            return {
                "ok": False,
                "error": {"code": code, "message": message, "recoverable": True},
                "revision": get_runtime().revision,
            }

        if not isinstance(operations, list) or not operations:
            result = _error("INVALID_ARGUMENT", "operations must be a non-empty list.")
        elif len(operations) > _BATCH_LIMIT:
            result = _error("INVALID_ARGUMENT", "operations is limited to {:d} items.".format(_BATCH_LIMIT))
        else:
            results: list[dict[str, object]] = []
            failed_at: int | None = None
            for index, item in enumerate(operations):
                if not isinstance(item, dict) or not isinstance(item.get("tool"), str):
                    entry = _error("INVALID_ARGUMENT", "Each operation must be an object with a string 'tool' field.")
                elif not isinstance(item.get("arguments", {}), dict):
                    entry = _error("INVALID_ARGUMENT", "'arguments' must be an object.")
                else:
                    operation = get_operation(item["tool"])
                    if operation is None:
                        entry = _error(
                            "INVALID_ARGUMENT",
                            "Unknown or non-batchable tool {!r} (available: {:s}).".format(
                                item["tool"], ", ".join(all_operations()),
                            ),
                        )
                    else:
                        try:
                            entry = operation(**item.get("arguments", {}))
                        except TypeError as ex:
                            entry = _error("INVALID_ARGUMENT", "Bad arguments for {!r}: {:s}".format(item["tool"], str(ex)))
                        except Exception as ex:  # pylint: disable=broad-exception-caught
                            entry = _error("OPERATION_FAILED", "{:s}: {:s}".format(item["tool"], str(ex)[:200]))
                results.append(entry)
                if entry.get("ok") is not True and failed_at is None:
                    failed_at = index
                if entry.get("ok") is not True and stop_on_error:
                    break
            result = {
                "ok": failed_at is None,
                "results": results,
                "failed_at": failed_at,
                "revision": get_runtime().revision,
            }
        record_tool_call("scene_batch", arguments, result, duration_ms=(time.monotonic() - started) * 1000.0)
        return result
