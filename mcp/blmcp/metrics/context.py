# SPDX-License-Identifier: GPL-3.0-or-later
"""Write concise per-tool context measurements when explicitly enabled."""

from __future__ import annotations

import json
import os
import time
import asyncio
from pathlib import Path
from typing import Any

__all__ = ("record_schema_tax", "record_tool_call", "tool_schema_snapshot")


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _write(entry: dict[str, Any]) -> None:
    """Append a local measurement when instrumentation is enabled."""
    destination = os.environ.get("BLMCP_METRICS_PATH")
    if not destination:
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")


def tool_schema_snapshot(server: object) -> list[dict[str, Any]]:
    """Return the compact per-tool schema listing used for every tax measurement."""
    tools = asyncio.run(server.list_tools())  # type: ignore[attr-defined]
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.inputSchema,
            "annotations": tool.annotations.model_dump(exclude_none=True) if tool.annotations else None,
        }
        for tool in tools
    ]


def record_schema_tax(server: object, profile: str) -> None:
    """Record one startup schema measurement, including descriptions and annotations.

    ``FastMCP.list_tools`` is asynchronous but is safe to inspect before the
    server begins its transport loop. Failure to inspect never prevents MCP
    startup; call metrics remain available.
    """
    if not os.environ.get("BLMCP_METRICS_PATH"):
        return
    try:
        schema = tool_schema_snapshot(server)
    except Exception:  # pylint: disable=broad-exception-caught
        return
    size = _json_size(schema)
    _write({
        "timestamp": time.time(),
        "kind": "tool_schema",
        "profile": profile,
        "tool_count": len(schema),
        "schema_bytes": size,
        "estimated_schema_tokens": (size + 3) // 4,
    })


def record_tool_call(
    name: str,
    arguments: dict[str, object],
    result: object,
    *,
    generated_python_chars: int = 0,
    duration_ms: float | None = None,
) -> None:
    """Append a local JSONL observation when ``BLMCP_METRICS_PATH`` is set.

    This never sends telemetry.  Token values are deliberately estimates
    (UTF-8 bytes / 4) so benchmark consumers can compare runs consistently.
    """
    argument_bytes = _json_size(arguments)
    result_bytes = _json_size(result)
    entry: dict[str, Any] = {
        "timestamp": time.time(),
        "tool": name,
        "ok": bool(result.get("ok")) if isinstance(result, dict) and "ok" in result else None,
        "argument_bytes": argument_bytes,
        "result_bytes": result_bytes,
        "generated_python_chars": generated_python_chars,
        "estimated_argument_tokens": (argument_bytes + 3) // 4,
        "estimated_result_tokens": (result_bytes + 3) // 4,
        "estimated_generated_python_tokens": (generated_python_chars + 3) // 4,
    }
    if duration_ms is not None:
        entry["duration_ms"] = round(float(duration_ms), 3)
    _write(entry)
