# SPDX-License-Identifier: GPL-3.0-or-later
"""High-level camera creation and framing operations."""

from __future__ import annotations

__all__ = ('CameraView', 'register')

from typing import Literal

from blmcp.agent_ops._bridge import load_toolcode, resolve_object, resolve_objects, run_mutation
from blmcp.tools_helpers import toolcode_format_call
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = load_toolcode(__file__)
CameraView = Literal["FRONT", "BACK", "LEFT", "RIGHT", "TOP", "THREE_QUARTER"]


def register(mcp: FastMCP) -> None:
    from blmcp.agent_ops import _registry  # pylint: disable=import-outside-toplevel
    from blmcp.agent_ops.camera_toolcode import CreateParams, Params  # pylint: disable=import-outside-toplevel

    @mcp.tool(annotations=ToolAnnotations(title="Frame Camera", destructiveHint=True, idempotentHint=True))
    def camera_frame(
        objects: list[str],
        camera: str | None = None,
        view: CameraView = "THREE_QUARTER",
        padding: float = 0.15,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Frame objects in a camera view without manually calculating bounds, lens, or orientation."""
        arguments = locals().copy()
        params = Params(resolve_objects(objects), resolve_object(camera) if camera else None, view, padding)
        return run_mutation(
            "camera_frame", arguments, toolcode_format_call(_TOOL_CALL, params),
            expected_revision=expected_revision, request_id=request_id,
        )

    @mcp.tool(annotations=ToolAnnotations(title="Create or Update Camera", destructiveHint=True, idempotentHint=True))
    def camera_create_or_update(
        name: str,
        location: list[float] | None = None,
        rotation: list[float] | None = None,
        target: list[float] | None = None,
        lens: float | None = None,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Create or update a camera. Rotation is in radians; ``target`` aims the camera at a world point (mutually exclusive with ``rotation``). Lens is the focal length in millimetres."""
        arguments = locals().copy()
        return run_mutation(
            "camera_create_or_update", arguments,
            toolcode_format_call(_TOOL_CALL, CreateParams(name, location, rotation, target, lens)),
            expected_revision=expected_revision, request_id=request_id,
        )

    _registry.register_operation("camera_create_or_update", camera_create_or_update)
    _registry.register_operation("camera_frame", camera_frame)
