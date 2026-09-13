# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicitly opt-in unrestricted Python escape hatch (AX-01).

Registered only when the server was started with ``--enable-unrestricted``.
It exists so a trusted developer session can lift a single safe-guard
rejection without restarting the server and losing session state.
"""

from __future__ import annotations

__all__ = ('register',)

from blmcp.agent_ops._bridge import execute_fallback_code
from blmcp.settings import unrestricted_enabled
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module


def register(mcp: FastMCP) -> None:
    if not unrestricted_enabled():
        return

    @mcp.tool(
        annotations=ToolAnnotations(title="Execute Python Code Unrestricted", destructiveHint=True, idempotentHint=False)
    )
    def execute_blender_code_unrestricted(code: str) -> dict[str, object]:
        """Execute Python code in Blender with NO safety policy. Only for trusted developer sessions; the server must have been started with --enable-unrestricted.

        Same calling convention as ``execute_blender_code`` (assign a
        JSON-serialisable dict to ``result``), but the AST guard is skipped
        entirely: filesystem, network, process, and addon operations are all
        available. Never enable this for untrusted agents.
        """
        arguments = locals().copy()
        return execute_fallback_code(
            "execute_blender_code_unrestricted", arguments, code, unsafe_python=True, debug=False,
        )
