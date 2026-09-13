# SPDX-License-Identifier: GPL-3.0-or-later
"""Object-level modeling operations: join, apply, origin, shading (AX-04)."""

from __future__ import annotations

__all__ = ('ManageAction', 'OriginType', 'register')

from typing import Literal

from blmcp.agent_ops._bridge import load_toolcode, resolve_object, resolve_objects, run_mutation
from blmcp.tools_helpers import toolcode_format_call
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = load_toolcode(__file__)
ManageAction = Literal["join", "apply_transform", "set_origin", "shade_smooth", "shade_flat"]
OriginType = Literal["GEOMETRY", "CURSOR", "GEOMETRY_CENTER"]


def register(mcp: FastMCP) -> None:
    from blmcp.agent_ops import _registry  # pylint: disable=import-outside-toplevel
    from blmcp.agent_ops.object_manage_toolcode import Params  # pylint: disable=import-outside-toplevel

    @mcp.tool(annotations=ToolAnnotations(title="Manage Object", destructiveHint=True, idempotentHint=False))
    def object_manage(
        object: str,
        action: ManageAction,
        others: list[str] | None = None,
        apply_location: bool = True,
        apply_rotation: bool = True,
        apply_scale: bool = True,
        origin: OriginType = "GEOMETRY",
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """High-frequency object-level modeling actions. ``join`` merges ``others`` into ``object`` (meshes only); ``apply_transform`` bakes the selected transform channels; ``set_origin`` recenters the origin; ``shade_smooth``/``shade_flat`` set shading."""
        arguments = locals().copy()
        return run_mutation(
            "object_manage", arguments,
            toolcode_format_call(
                _TOOL_CALL,
                Params(
                    resolve_object(object), action,
                    resolve_objects(others) if others is not None else None,
                    apply_location, apply_rotation, apply_scale, origin,
                ),
            ),
            expected_revision=expected_revision, request_id=request_id,
        )

    _registry.register_operation("object_manage", object_manage)
