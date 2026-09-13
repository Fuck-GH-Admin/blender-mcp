# SPDX-License-Identifier: GPL-3.0-or-later
"""Compact scene observation tools for agent planning."""


from __future__ import annotations

__all__ = ('register',)

import time

from blmcp.agent_ops._bridge import load_toolcode, run_query
from blmcp.metrics import record_tool_call
from blmcp.state import get_runtime
from blmcp.tools_helpers import toolcode_format_call
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = load_toolcode(__file__)


def _query(tool: str, params: object, arguments: dict[str, object]) -> dict[str, object]:
    return run_query(tool, arguments, toolcode_format_call(_TOOL_CALL, params))


def register(mcp: FastMCP) -> None:
    from blmcp.agent_ops.observation_toolcode import (  # pylint: disable=import-outside-toplevel
        RefreshParams, SceneSummaryParams, SearchParams,
    )

    @mcp.tool(annotations=ToolAnnotations(title="Scene Summary", readOnlyHint=True))
    def scene_summary() -> dict[str, object]:
        """Return a compact scene summary: counts, selection, camera, mode, and render engine."""
        return _query("scene_summary", SceneSummaryParams(), {})

    @mcp.tool(annotations=ToolAnnotations(title="Search Objects", readOnlyHint=True))
    def search_objects(
        name_pattern: str | None = None,
        object_type: str | None = None,
        collection: str | None = None,
        material: str | None = None,
        visible: bool | None = None,
        limit: int = 20,
    ) -> dict[str, object]:
        """Find only matching objects. Use this before object editing in large scenes."""
        arguments = locals().copy()
        return _query(
            "search_objects",
            SearchParams(name_pattern, object_type, collection, material, visible, limit),
            arguments,
        )

    @mcp.tool(annotations=ToolAnnotations(title="Scene Refresh", readOnlyHint=True))
    def scene_refresh() -> dict[str, object]:
        """Re-observe the scene after edits that bypassed structured tools (fallback Python, manual edits, undo) and report created/deleted objects. Re-baselines the server's scene knowledge; does not advance the revision."""
        started = time.monotonic()
        result = run_query("scene_refresh", {}, toolcode_format_call(_TOOL_CALL, RefreshParams()), record=False)
        if result.get("ok") is True:
            names = result.get("names")
            known = frozenset(str(name) for name in names) if isinstance(names, list) else frozenset()
            diff = get_runtime().refresh_known_objects(known)
            result.pop("names", None)
            result["created"] = diff["created"]
            result["deleted"] = diff["deleted"]
            result["truncated"] = diff["truncated"]
        record_tool_call("scene_refresh", {}, result, duration_ms=(time.monotonic() - started) * 1000.0)
        return result
