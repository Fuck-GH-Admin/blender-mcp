# SPDX-License-Identifier: GPL-3.0-or-later
"""Semantic object creation and editing tools."""


from __future__ import annotations

__all__ = ('DisplayType', 'Primitive', 'TransformSpace', 'register')

from typing import Literal

from blmcp.agent_ops._bridge import load_toolcode, resolve_object, run_mutation
from blmcp.tools_helpers import toolcode_format_call
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = load_toolcode(__file__)
Primitive = Literal["CUBE", "UV_SPHERE", "ICO_SPHERE", "CYLINDER", "CONE", "TORUS", "PLANE", "MONKEY"]
TransformSpace = Literal["WORLD", "LOCAL"]
DisplayType = Literal["TEXTURED", "SOLID", "WIRE", "BOUNDS"]


def _mutation(
    tool: str,
    params: object,
    arguments: dict[str, object],
    expected_revision: int | None,
    request_id: str | None,
) -> dict[str, object]:
    return run_mutation(
        tool, arguments, toolcode_format_call(_TOOL_CALL, params),
        expected_revision=expected_revision, request_id=request_id,
    )


def register(mcp: FastMCP) -> None:
    """Register compact object operations for every agent profile."""
    from blmcp.agent_ops.object_toolcode import (  # pylint: disable=import-outside-toplevel
        CreateParams, DeleteParams, DuplicateParams, ParentParams, PropertiesParams, TransformParams,
    )

    @mcp.tool(annotations=ToolAnnotations(title="Create Object", destructiveHint=True, idempotentHint=False))
    def object_create(
        primitive: Primitive,
        name: str | None = None,
        location: list[float] | None = None,
        rotation: list[float] | None = None,
        scale: list[float] | None = None,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Create a named primitive without generating Blender Python. Rotation is in radians."""
        arguments = locals().copy()
        return _mutation(
            "object_create", CreateParams(primitive, name, location, rotation, scale), arguments,
            expected_revision, request_id,
        )

    @mcp.tool(annotations=ToolAnnotations(title="Transform Object", destructiveHint=True, idempotentHint=True))
    def object_transform(
        object: str,
        location: list[float] | None = None,
        rotation: list[float] | None = None,
        scale: list[float] | None = None,
        space: TransformSpace = "WORLD",
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Set only the supplied transform fields. Rotation is in radians; ``object`` accepts a name or session ID."""
        arguments = locals().copy()
        return _mutation(
            "object_transform", TransformParams(resolve_object(object), location, rotation, scale, space), arguments,
            expected_revision, request_id,
        )

    @mcp.tool(annotations=ToolAnnotations(title="Delete Object", destructiveHint=True, idempotentHint=False))
    def object_delete(
        object: str,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Delete one object by name or session ID."""
        arguments = locals().copy()
        return _mutation("object_delete", DeleteParams(resolve_object(object)), arguments, expected_revision, request_id)

    @mcp.tool(annotations=ToolAnnotations(title="Duplicate Object", destructiveHint=True, idempotentHint=False))
    def object_duplicate(
        object: str,
        new_name: str | None = None,
        linked_data: bool = True,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Duplicate an object. By default, the duplicate shares the source mesh or curve data."""
        arguments = locals().copy()
        return _mutation(
            "object_duplicate", DuplicateParams(resolve_object(object), new_name, linked_data), arguments,
            expected_revision, request_id,
        )

    @mcp.tool(annotations=ToolAnnotations(title="Set Object Properties", destructiveHint=True, idempotentHint=True))
    def object_set_properties(
        object: str,
        name: str | None = None,
        visible: bool | None = None,
        render_visible: bool | None = None,
        display_type: DisplayType | None = None,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Rename an object or change its viewport/render visibility and display type."""
        arguments = locals().copy()
        return _mutation(
            "object_set_properties",
            PropertiesParams(resolve_object(object), name, visible, render_visible, display_type),
            arguments, expected_revision, request_id,
        )

    @mcp.tool(annotations=ToolAnnotations(title="Set Object Parent", destructiveHint=True, idempotentHint=True))
    def object_parent(
        object: str,
        parent: str | None = None,
        keep_world_transform: bool = True,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Set or clear an object's parent while optionally preserving its world transform."""
        arguments = locals().copy()
        parent_name = resolve_object(parent) if parent is not None else None
        return _mutation(
            "object_parent", ParentParams(resolve_object(object), parent_name, keep_world_transform), arguments,
            expected_revision, request_id,
        )

    from blmcp.agent_ops import _registry  # pylint: disable=import-outside-toplevel

    for name, operation in (
        ("object_create", object_create),
        ("object_delete", object_delete),
        ("object_duplicate", object_duplicate),
        ("object_parent", object_parent),
        ("object_set_properties", object_set_properties),
        ("object_transform", object_transform),
    ):
        _registry.register_operation(name, operation)
