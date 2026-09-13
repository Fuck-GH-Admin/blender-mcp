# SPDX-License-Identifier: GPL-3.0-or-later
"""Generic structured modifier management."""


from __future__ import annotations

__all__ = ('ModifierAction', 'register')

from typing import Any, Literal

from blmcp.agent_ops._bridge import load_toolcode, resolve_object, run_mutation
from blmcp.tools_helpers import toolcode_format_call
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = load_toolcode(__file__)
ModifierAction = Literal["add", "update", "remove", "apply"]


def register(mcp: FastMCP) -> None:
    from blmcp.agent_ops.modifier_toolcode import Params  # pylint: disable=import-outside-toplevel

    @mcp.tool(annotations=ToolAnnotations(title="Manage Modifier", destructiveHint=True, idempotentHint=False))
    def modifier_manage(
        object: str,
        action: ModifierAction,
        type: str | None = None,
        modifier: str | None = None,
        properties: dict[str, Any] | None = None,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Add, update, remove, or apply a modifier without writing bpy code.

        ``type`` is required for ``add`` (for example ``BEVEL``). ``modifier``
        is required for update, remove, and apply. Only writable scalar and
        vector modifier properties are accepted.
        """
        arguments = locals().copy()
        params = Params(resolve_object(object), action, type, modifier, properties)
        return run_mutation(
            "modifier_manage", arguments, toolcode_format_call(_TOOL_CALL, params),
            expected_revision=expected_revision, request_id=request_id,
        )

    from blmcp.agent_ops import _registry  # pylint: disable=import-outside-toplevel

    _registry.register_operation("modifier_manage", modifier_manage)
