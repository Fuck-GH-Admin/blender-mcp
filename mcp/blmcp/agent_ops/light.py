# SPDX-License-Identifier: GPL-3.0-or-later
"""Create or update common Blender lights."""

from __future__ import annotations

__all__ = ('LightType', 'register')

from typing import Literal

from blmcp.agent_ops._bridge import load_toolcode, run_mutation
from blmcp.tools_helpers import toolcode_format_call
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = load_toolcode(__file__)
LightType = Literal["POINT", "SUN", "SPOT", "AREA"]


def register(mcp: FastMCP) -> None:
    from blmcp.agent_ops import _registry  # pylint: disable=import-outside-toplevel
    from blmcp.agent_ops.light_toolcode import Params  # pylint: disable=import-outside-toplevel

    @mcp.tool(annotations=ToolAnnotations(title="Create or Update Light", destructiveHint=True, idempotentHint=True))
    def light_create_or_update(
        name: str,
        type: LightType = "AREA",
        energy: float | None = None,
        color: list[float] | None = None,
        location: list[float] | None = None,
        rotation: list[float] | None = None,
        size: float | None = None,
        target: list[float] | None = None,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Create or update a point, sun, spot, or area light. Rotation is in radians; ``target`` aims the light at a world point (mutually exclusive with ``rotation``)."""
        arguments = locals().copy()
        result = run_mutation(
            "light_create_or_update", arguments,
            toolcode_format_call(_TOOL_CALL, Params(name, type, energy, color, location, rotation, size, target)),
            expected_revision=expected_revision, request_id=request_id,
        )
        return result

    _registry.register_operation("light_create_or_update", light_create_or_update)
