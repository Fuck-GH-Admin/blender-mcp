# SPDX-License-Identifier: GPL-3.0-or-later
"""MCP tools for the Poly Haven pack: compact search plus download-and-import."""


from __future__ import annotations

__all__ = ('AssetType', 'ImportPlan', 'Resolution', 'register')

from typing import Literal, NamedTuple

import time

from blmcp.agent_ops._bridge import load_toolcode, resolve_object, run_mutation
from blmcp.agent_ops._registry import register_operation
from blmcp.metrics import record_tool_call
from blmcp.providers.polyhaven import client
from blmcp.state import get_runtime
from blmcp.tools_helpers import toolcode_format_call
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = load_toolcode(__file__)
AssetType = Literal["hdri", "texture", "model"]
Resolution = Literal["1k", "2k", "4k", "8k"]
_SEARCH_LIMIT_DEFAULT = 5
_SEARCH_LIMIT_MAX = 10


class ImportPlan(NamedTuple):
    """Server-side download plan for one asset import."""

    kind: str
    name: str
    files: list[tuple[str, str]]


def _error(code: str, message: str, suggested_action: str | None = None) -> dict[str, object]:
    error: dict[str, object] = {"code": code, "message": message, "recoverable": True}
    if suggested_action:
        error["suggested_action"] = suggested_action
    return {"ok": False, "error": error, "revision": get_runtime().revision}


def _prepare_import(asset_id: str, resolution: str) -> ImportPlan:
    """Resolve asset metadata and download every needed file into the local cache."""
    info = client.fetch_asset_info(asset_id)
    kind = str(info["type"])
    name = str(info["name"]).strip() or asset_id
    files = client.fetch_asset_files(asset_id)
    downloaded = [
        (role, client.download_file(url, asset_id))
        for role, url in client.resolve_import_files(files, kind, resolution)
    ]
    return ImportPlan(kind=kind, name=name, files=downloaded)


def _import_params(plan: ImportPlan, target_object: str | None) -> object:
    """Build the Blender-side parameters for one prepared import plan."""
    from blmcp.providers.polyhaven.tools_toolcode import (  # pylint: disable=import-outside-toplevel
        ImportHDRIParams, ImportModelParams, ImportTextureParams,
    )

    paths = dict(plan.files)
    if plan.kind == "hdri":
        return ImportHDRIParams(name=plan.name, filepath=paths["hdri"])
    if plan.kind == "texture":
        roles = [role for role in paths if role != "hdri"]
        return ImportTextureParams(name=plan.name, filepaths=[(role, paths[role]) for role in roles], target_object=target_object)
    if plan.kind == "model":
        return ImportModelParams(name=plan.name, filepath=paths["model"])
    raise client.AssetFetchError("Unsupported Poly Haven asset type {!r}.".format(plan.kind))


def register(mcp: FastMCP) -> None:
    """Register Poly Haven tools for the profiles that enable this pack."""

    @mcp.tool(annotations=ToolAnnotations(title="Search Poly Haven Assets", readOnlyHint=True, openWorldHint=True))
    def polyhaven_search(
        query: str = "",
        asset_type: AssetType = "hdri",
        limit: int = _SEARCH_LIMIT_DEFAULT,
    ) -> dict[str, object]:
        """Search free Poly Haven assets (external service). Returns compact rows for polyhaven_import."""
        arguments = locals().copy()
        started = time.monotonic()
        try:
            capped = max(1, min(int(limit), _SEARCH_LIMIT_MAX))
            assets = client.search_assets(asset_type, query, capped)
        except (client.AssetFetchError, ValueError) as ex:
            result = _error("ASSET_FETCH_FAILED", str(ex), "polyhaven_search")
        else:
            result = {"ok": True, "asset_type": asset_type, "count": len(assets), "assets": assets}
        record_tool_call("polyhaven_search", arguments, result, duration_ms=(time.monotonic() - started) * 1000.0)
        return result

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Import Poly Haven Asset", destructiveHint=True, idempotentHint=False, openWorldHint=True,
        )
    )
    def polyhaven_import(
        asset_id: str,
        object: str | None = None,
        resolution: Resolution = "2k",
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Download and import one Poly Haven asset: HDRIs set the world, textures build a material, models append the asset's bundled blend file. Use polyhaven_search first."""
        arguments = locals().copy()
        if not asset_id.strip():
            result = _error("INVALID_ARGUMENT", "asset_id cannot be empty.", "polyhaven_search")
            record_tool_call("polyhaven_import", arguments, result, duration_ms=0.0)
            return result
        started = time.monotonic()
        try:
            plan = _prepare_import(asset_id.strip(), resolution)
            target = resolve_object(object) if object is not None else None
            call = toolcode_format_call(_TOOL_CALL, _import_params(plan, target))
        except client.AssetFetchError as ex:
            result = _error("ASSET_FETCH_FAILED", str(ex), "polyhaven_search")
            record_tool_call("polyhaven_import", arguments, result, duration_ms=(time.monotonic() - started) * 1000.0)
            return result
        return run_mutation(
            "polyhaven_import", arguments, call,
            expected_revision=expected_revision, request_id=request_id,
        )

    register_operation("polyhaven_import", polyhaven_import)
    register_operation("polyhaven_search", polyhaven_search)
