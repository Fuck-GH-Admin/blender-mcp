# SPDX-License-Identifier: GPL-3.0-or-later
"""Compact render configuration and preview operations."""


from __future__ import annotations

__all__ = ('RenderEngine', 'register')

from typing import Literal

from blmcp.agent_ops._bridge import load_toolcode, run_mutation
from blmcp.tools_helpers import toolcode_format_call
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = load_toolcode(__file__)
RenderEngine = Literal["BLENDER_EEVEE", "CYCLES"]


def _mutation(
    tool: str, params: object, arguments: dict[str, object], expected_revision: int | None, request_id: str | None,
) -> dict[str, object]:
    return run_mutation(
        tool, arguments, toolcode_format_call(_TOOL_CALL, params),
        expected_revision=expected_revision, request_id=request_id,
    )


def register(mcp: FastMCP) -> None:
    from blmcp.agent_ops.render_toolcode import ConfigureParams, PreviewParams  # pylint: disable=import-outside-toplevel

    @mcp.tool(annotations=ToolAnnotations(title="Configure Render", destructiveHint=True, idempotentHint=True))
    def render_configure(
        engine: RenderEngine | None = None,
        resolution_x: int | None = None,
        resolution_y: int | None = None,
        samples: int | None = None,
        transparent: bool | None = None,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Set only the requested render settings; samples apply to Cycles or Eevee as appropriate."""
        arguments = locals().copy()
        return _mutation(
            "render_configure", ConfigureParams(engine, resolution_x, resolution_y, samples, transparent), arguments,
            expected_revision, request_id,
        )

    @mcp.tool(annotations=ToolAnnotations(title="Render Preview", destructiveHint=True, idempotentHint=False))
    def render_preview(
        output_path: str,
        max_dimension: int = 512,
        samples: int = 16,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Render a synchronous low-resolution preview to an explicit output path."""
        arguments = locals().copy()
        return _mutation(
            "render_preview", PreviewParams(output_path, max_dimension, samples), arguments, expected_revision, request_id,
        )

    from blmcp.agent_ops import _registry  # pylint: disable=import-outside-toplevel

    _registry.register_operation("render_configure", render_configure)
    _registry.register_operation("render_preview", render_preview)
