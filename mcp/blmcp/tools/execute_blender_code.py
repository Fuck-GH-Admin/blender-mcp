# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

# pylint: disable=C0114  # See tool doc-string.

__all__ = (
    "register",
)

import time

from blmcp.tools_helpers.blender_cli import run_blender_cli, synced_blend_for_cli
from blmcp.agent_ops._bridge import execute_fallback_code
from blmcp.metrics import record_tool_call
from blmcp.security import SafeCodeViolation, validate_blender_code
from blmcp.settings import agent_mode_enabled, unsafe_python_enabled
from blmcp.tools_helpers.connection import send_code
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module


def register(mcp: FastMCP) -> None:
    if not agent_mode_enabled():
        @mcp.tool(
            annotations=ToolAnnotations(
                title="Execute Python Code",
                destructiveHint=True,
            )
        )
        def execute_blender_code(code: str) -> dict[str, object]:
            """
            Execute Python code in the connected Blender instance.

            The code runs in Blender's Python environment with full access to ``bpy``.
            To return data, assign a JSON-serialisable dict to a variable named ``result``.
            Deferred completion via ``check_is_finished`` is only supported by the
            interactive addon server, and is rejected in background mode.
            """
            return send_code(code, strict_json=False)
    else:
        def _execute_blender_code_safe(code: str, debug: bool = False) -> dict[str, object]:
            """
            Execute Python code in the connected Blender instance.

            The code runs in Blender's Python environment with full access to ``bpy``.
            To return data, assign a JSON-serialisable dict to a variable named ``result``.
            Deferred completion via ``check_is_finished`` is only supported by the
            interactive addon server, and is rejected in background mode.

            Safe mode is on by default and rejects filesystem, process, network,
            persistent-handler, and dynamic-execution patterns. Start the server with
            ``--unsafe-python`` only for a trusted local session.
            """
            return execute_fallback_code(
                "execute_blender_code", {"code": code, "debug": debug}, code,
                unsafe_python=unsafe_python_enabled(), debug=debug,
            )

        mcp.tool(
            name="execute_blender_code",
            annotations=ToolAnnotations(
                title="Execute Python Code",
                destructiveHint=True,
            )
        )(_execute_blender_code_safe)

    if not agent_mode_enabled():
        @mcp.tool(
            annotations=ToolAnnotations(
                title="Execute Python Code for Command-Line",
                destructiveHint=True,
            )
        )
        def execute_blender_code_for_cli(blend_file: str, code: str) -> dict[str, object]:
            """
            Execute Python code in a background Blender process.

            Opens *blend_file* with ``blender --background`` and runs *code*.
            Assign a dict to ``result`` to return data.
            """
            # LLM-generated code may return non-JSON-serializable values
            # (e.g. Blender objects), handled by `run_blender_cli` via `default=repr`.
            with synced_blend_for_cli(blend_file) as synced_path:
                value = run_blender_cli(synced_path, code)
                assert isinstance(value, dict), "Expected dict from `run_blender_cli`, got {!r}".format(type(value))
                return value
    else:
        def _execute_blender_code_for_cli_safe(blend_file: str, code: str) -> dict[str, object]:
            """Run fallback code in background Blender after the same safe-policy check."""
            if not unsafe_python_enabled():
                try:
                    validate_blender_code(code)
                except SafeCodeViolation as ex:
                    result: dict[str, object] = {
                        "ok": False,
                        "error": {
                            "code": "SAFE_CODE_REJECTED",
                            "message": str(ex),
                            "recoverable": True,
                            "suggested_action": "use_structured_tool_or_rewrite_code",
                        },
                    }
                    record_tool_call(
                        "execute_blender_code_for_cli",
                        {"blend_file": blend_file, "code": code},
                        result,
                        generated_python_chars=len(code),
                        duration_ms=0.0,
                    )
                    return result

            started = time.monotonic()
            with synced_blend_for_cli(blend_file) as synced_path:
                value = run_blender_cli(synced_path, code)
            assert isinstance(value, dict), "Expected dict from `run_blender_cli`, got {!r}".format(type(value))
            result = {"ok": True, "result": value}
            record_tool_call(
                "execute_blender_code_for_cli",
                {"blend_file": blend_file, "code": code},
                result,
                generated_python_chars=len(code),
                duration_ms=(time.monotonic() - started) * 1000.0,
            )
            return result

        mcp.tool(
            name="execute_blender_code_for_cli",
            annotations=ToolAnnotations(
                title="Execute Python Code for Command-Line",
                destructiveHint=True,
            ),
        )(_execute_blender_code_for_cli_safe)
