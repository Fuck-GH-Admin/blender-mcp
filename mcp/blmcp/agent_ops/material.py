# SPDX-License-Identifier: GPL-3.0-or-later
"""Principled-material creation and assignment tools."""


from __future__ import annotations

__all__ = ('register',)

from blmcp.agent_ops._bridge import load_toolcode, resolve_object, run_mutation
from blmcp.tools_helpers import toolcode_format_call
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = load_toolcode(__file__)


def _mutation(
    tool: str, params: object, arguments: dict[str, object], expected_revision: int | None, request_id: str | None,
) -> dict[str, object]:
    return run_mutation(
        tool, arguments, toolcode_format_call(_TOOL_CALL, params),
        expected_revision=expected_revision, request_id=request_id,
    )


def register(mcp: FastMCP) -> None:
    from blmcp.agent_ops.material_toolcode import AssignParams, CreateParams  # pylint: disable=import-outside-toplevel

    @mcp.tool(annotations=ToolAnnotations(title="Create or Update Material", destructiveHint=True, idempotentHint=True))
    def material_create_or_update(
        name: str,
        base_color: list[float] | None = None,
        metallic: float | None = None,
        roughness: float | None = None,
        alpha: float | None = None,
        emission: list[float] | None = None,
        emission_strength: float | None = None,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Create or update a Principled BSDF material. Color values are RGB/RGBA values from 0 to 1."""
        arguments = locals().copy()
        return _mutation(
            "material_create_or_update",
            CreateParams(name, base_color, metallic, roughness, alpha, emission, emission_strength),
            arguments, expected_revision, request_id,
        )

    @mcp.tool(annotations=ToolAnnotations(title="Assign Material", destructiveHint=True, idempotentHint=True))
    def material_assign(
        object: str,
        material: str,
        slot: int = 0,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Assign an existing material to a mesh object's slot, replacing slot zero by default."""
        arguments = locals().copy()
        return _mutation(
            "material_assign", AssignParams(resolve_object(object), material, slot), arguments,
            expected_revision, request_id,
        )

    from blmcp.agent_ops import _registry  # pylint: disable=import-outside-toplevel

    _registry.register_operation("material_assign", material_assign)
    _registry.register_operation("material_create_or_update", material_create_or_update)
