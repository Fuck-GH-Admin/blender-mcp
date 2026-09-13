# SPDX-License-Identifier: GPL-3.0-or-later
"""MCP tool for importing local asset files into the connected Blender."""

from __future__ import annotations

__all__ = ('ImportFileFormat', 'register')

import os
from typing import Literal

from blmcp.agent_ops._bridge import load_toolcode, run_mutation
from blmcp.metrics import record_tool_call
from blmcp.agent_ops._registry import register_operation
from blmcp.state import get_runtime
from blmcp.tools_helpers import toolcode_format_call
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = load_toolcode(__file__)
ImportFileFormat = Literal["svg", "glb", "gltf", "obj", "fbx", "image"]
_EXPECTED_EXTENSIONS = {
    "svg": (".svg",),
    "glb": (".glb",),
    "gltf": (".gltf",),
    "obj": (".obj",),
    "fbx": (".fbx",),
    "image": (".bmp", ".exr", ".hdr", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"),
}


def _error(code: str, message: str, suggested_action: str | None = None) -> dict[str, object]:
    error: dict[str, object] = {"code": code, "message": message, "recoverable": True}
    if suggested_action:
        error["suggested_action"] = suggested_action
    return {"ok": False, "error": error, "revision": get_runtime().revision}


def register(mcp: FastMCP) -> None:
    from blmcp.providers.local_import.tools_toolcode import ImportFileParams  # pylint: disable=import-outside-toplevel

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Import Local File", destructiveHint=True, idempotentHint=False,
        )
    )
    def import_file(
        path: str,
        format: ImportFileFormat,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Import a local file into the scene: SVG curves, glTF/GLB, OBJ, FBX geometry, or a reference image datablock. The path must be readable by the Blender process."""
        arguments = locals().copy()
        result: dict[str, object] | None = None
        if not path.strip():
            result = _error("INVALID_ARGUMENT", "path cannot be empty.")
        elif not os.path.isfile(os.path.abspath(os.path.expanduser(path.strip()))):
            result = _error("INVALID_PATH", "File does not exist: {!r}.".format(path))
        else:
            filepath = os.path.abspath(os.path.expanduser(path.strip()))
            if not filepath.lower().endswith(_EXPECTED_EXTENSIONS[format]):
                result = _error(
                    "INVALID_ARGUMENT",
                    "format {!r} expects {:s}; the path ends with {!r}.".format(
                        format, " or ".join(_EXPECTED_EXTENSIONS[format]), os.path.splitext(filepath)[1],
                    ),
                )
        if result is not None:
            record_tool_call("import_file", arguments, result, duration_ms=0.0)
            return result
        return run_mutation(
            "import_file", arguments,
            toolcode_format_call(_TOOL_CALL, ImportFileParams(path=filepath, format=format)),
            expected_revision=expected_revision, request_id=request_id,
        )

    register_operation("import_file", import_file)
