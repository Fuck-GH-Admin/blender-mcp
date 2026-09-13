# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the 1.1.1 agent-experience improvements (AX-01..AX-08)."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest

from blmcp.agent_ops._bridge import load_toolcode, wrap_fallback_code
from blmcp.agent_ops._registry import all_operations
from blmcp.metrics import record_tool_call
from blmcp.metrics.context_benchmark import summarize_run
from blmcp.state.runtime import AgentRuntime, object_name_diff


def _call_tool(mcp: object, name: str, arguments: dict[str, object]) -> dict[str, object]:
    result = asyncio.run(mcp.call_tool(name, arguments))  # type: ignore[attr-defined]
    if isinstance(result, tuple):
        structured = next((item for item in result if isinstance(item, dict)), None)
        if structured is not None:
            return structured
        content = result[0]
    else:
        content = result
    for item in content:
        text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
        if text is not None:
            return json.loads(text)
    raise AssertionError("Tool {:s} returned no text content: {!r}".format(name, result))


class TestUnrestrictedEscapeHatch(unittest.TestCase):
    """AX-01: the unrestricted escape hatch is opt-in at startup only."""

    def test_absent_by_default(self) -> None:
        from blmcp import create_server

        names = {tool.name for tool in asyncio.run(create_server("core").list_tools())}
        self.assertNotIn("execute_blender_code_unrestricted", names)

    def test_present_only_with_flag(self) -> None:
        from blmcp import create_server

        names = {
            tool.name
            for tool in asyncio.run(create_server("core", enable_unrestricted=True).list_tools())
        }
        self.assertIn("execute_blender_code_unrestricted", names)

    def test_never_in_official_profile(self) -> None:
        from blmcp import create_server

        names = {
            tool.name
            for tool in asyncio.run(create_server("official", enable_unrestricted=True).list_tools())
        }
        self.assertNotIn("execute_blender_code_unrestricted", names)


class TestLookAtSemantics(unittest.TestCase):
    """AX-02: cameras and lights support look-at targets and camera creation."""

    def test_toolcodes_compile(self) -> None:
        import blmcp.agent_ops.camera as camera
        import blmcp.agent_ops.light as light

        compile(load_toolcode(camera.__file__), "camera_toolcode", "exec")
        compile(load_toolcode(light.__file__), "light_toolcode", "exec")

    def test_camera_tools_registered(self) -> None:
        from blmcp import create_server

        names = {tool.name for tool in asyncio.run(create_server("core").list_tools())}
        self.assertIn("camera_create_or_update", names)
        self.assertIn("camera_frame", names)


class TestSceneBatch(unittest.TestCase):
    """AX-03: sequential batch execution with per-item results."""

    def test_registry_covers_structured_mutations(self) -> None:
        from blmcp import create_server

        create_server("core")
        core_names = set(all_operations())
        for expected in (
            "object_create", "object_transform", "object_delete", "object_duplicate",
            "object_set_properties", "object_parent", "object_manage", "modifier_manage",
            "material_create_or_update", "material_assign", "camera_create_or_update",
            "camera_frame", "light_create_or_update", "render_configure", "render_preview",
        ):
            self.assertIn(expected, core_names)
        # Escape hatches and batch itself are not batchable.
        self.assertNotIn("execute_blender_code", core_names)
        self.assertNotIn("scene_batch", core_names)
        # Provider tools join the whitelist only for profiles that load packs.
        create_server("asset")
        asset_names = set(all_operations())
        for expected in ("import_file", "polyhaven_import", "polyhaven_search"):
            self.assertIn(expected, asset_names)

    def test_batch_validates_offline(self) -> None:
        from blmcp import create_server

        mcp = create_server("core")
        empty = _call_tool(mcp, "scene_batch", {"operations": []})
        self.assertEqual(empty["error"]["code"], "INVALID_ARGUMENT")
        unknown = _call_tool(mcp, "scene_batch", {
            "operations": [{"tool": "execute_blender_code", "arguments": {"code": "x"}}],
        })
        self.assertFalse(unknown["ok"])
        self.assertEqual(unknown["failed_at"], 0)
        self.assertEqual(unknown["results"][0]["error"]["code"], "INVALID_ARGUMENT")
        self.assertIn("execute_blender_code", unknown["results"][0]["error"]["message"])
        oversized = _call_tool(mcp, "scene_batch", {"operations": [{"tool": "object_create"}] * 33})
        self.assertEqual(oversized["error"]["code"], "INVALID_ARGUMENT")
        # Items that violate the argument schema are rejected by FastMCP validation.
        from mcp.server.fastmcp.exceptions import ToolError  # pylint: disable=import-outside-toplevel

        with self.assertRaises(ToolError):
            _call_tool(mcp, "scene_batch", {"operations": ["object_create"]})

    def test_batch_reports_argument_errors_before_blender(self) -> None:
        from blmcp import create_server

        mcp = create_server("core")
        unknown_kwarg = _call_tool(mcp, "scene_batch", {
            "operations": [{"tool": "object_transform", "arguments": {"bogus": 1}}],
        })
        self.assertFalse(unknown_kwarg["ok"])
        self.assertEqual(unknown_kwarg["failed_at"], 0)
        self.assertEqual(unknown_kwarg["results"][0]["error"]["code"], "INVALID_ARGUMENT")
        self.assertIn("bogus", unknown_kwarg["results"][0]["error"]["message"])

    def test_batch_isolates_bridge_failures_per_item(self) -> None:
        """Without a live Blender the op fails per item; the batch envelope stays well-formed."""
        from blmcp import create_server

        mcp = create_server("core")
        result = _call_tool(mcp, "scene_batch", {
            "operations": [{"tool": "object_transform", "arguments": {"object": "Cube"}}],
        })
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed_at"], 0)
        self.assertEqual(result["results"][0]["error"]["code"], "OPERATION_FAILED")
        self.assertEqual(result["revision"], 0)


class TestObjectManage(unittest.TestCase):
    """AX-04: object-level modeling actions."""

    def test_toolcode_compiles(self) -> None:
        import blmcp.agent_ops.object_manage as manage

        compile(load_toolcode(manage.__file__), "object_manage_toolcode", "exec")

    def test_registered(self) -> None:
        from blmcp import create_server

        names = {tool.name for tool in asyncio.run(create_server("core").list_tools())}
        self.assertIn("object_manage", names)


class TestDurationMetrics(unittest.TestCase):
    """AX-05: per-call durations are recorded and aggregated."""

    def test_record_tool_call_persists_duration(self) -> None:
        previous = os.environ.get("BLMCP_METRICS_PATH")
        destination = os.path.join(tempfile.mkdtemp(), "metrics.jsonl")
        os.environ["BLMCP_METRICS_PATH"] = destination
        try:
            record_tool_call("object_create", {}, {"ok": True}, duration_ms=12.3456)
        finally:
            if previous is None:
                del os.environ["BLMCP_METRICS_PATH"]
            else:
                os.environ["BLMCP_METRICS_PATH"] = previous
        with open(destination, encoding="utf-8") as handle:
            entry = json.loads(handle.readline())
        self.assertEqual(entry["duration_ms"], 12.346)

    def test_summarize_run_aggregates_duration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "metrics.jsonl")
            entries = (
                {"timestamp": 1.0, "tool": "render_preview", "ok": True, "duration_ms": 100.0,
                 "estimated_argument_tokens": 1, "estimated_result_tokens": 1, "estimated_generated_python_tokens": 0},
                {"timestamp": 2.0, "tool": "render_preview", "ok": True, "duration_ms": 300.0,
                 "estimated_argument_tokens": 1, "estimated_result_tokens": 1, "estimated_generated_python_tokens": 0},
            )
            with open(path, "w", encoding="utf-8") as handle:
                for entry in entries:
                    handle.write(json.dumps(entry) + "\n")
            stats = summarize_run(path)["tools"]["render_preview"]
            self.assertAlmostEqual(stats["duration_ms_total"], 400.0)
            self.assertAlmostEqual(stats["duration_ms_max"], 300.0)


class TestSceneChangeTracking(unittest.TestCase):
    """AX-06: scene_refresh baseline and fallback change probe."""

    def test_object_name_diff(self) -> None:
        self.assertEqual(object_name_diff(None, frozenset({"Cube"}))["truncated"], False)
        diff = object_name_diff(frozenset({"Cube", "Light"}), frozenset({"Cube", "Suzanne"}))
        self.assertEqual(diff["created"], ["Suzanne"])
        self.assertEqual(diff["deleted"], ["Light"])

    def test_runtime_baseline_flow(self) -> None:
        runtime = AgentRuntime()
        first = runtime.refresh_known_objects(frozenset({"Cube"}))
        self.assertEqual(first["created"], [])
        second = runtime.refresh_known_objects(frozenset({"Cube", "Suzanne"}))
        self.assertEqual(second["created"], ["Suzanne"])

    def test_wrap_fallback_code_structure(self) -> None:
        wrapped = wrap_fallback_code("result = {'value': 1}")
        self.assertTrue(wrapped.startswith("import bpy as _blmcp_bpy\n"))
        self.assertIn("result = {'value': 1}", wrapped)
        self.assertIn('result["_scene_changed"]', wrapped)
        self.assertIn("except Exception", wrapped)
        compile(wrapped, "<wrapped>", "exec")


class TestLocalImport(unittest.TestCase):
    """AX-08: local file imports with server-side validation."""

    def test_toolcode_compiles(self) -> None:
        import blmcp.providers.local_import.tools as tools

        compile(load_toolcode(tools.__file__), "local_import_toolcode", "exec")

    def test_offline_validation(self) -> None:
        from blmcp import create_server

        mcp = create_server("asset")
        missing = _call_tool(mcp, "import_file", {"path": "/nonexistent/file.svg", "format": "svg"})
        self.assertEqual(missing["error"]["code"], "INVALID_PATH")
        with tempfile.TemporaryDirectory() as directory:
            wrong = os.path.join(directory, "notes.txt")
            open(wrong, "w").write("x")
            mismatch = _call_tool(mcp, "import_file", {"path": wrong, "format": "svg"})
            self.assertEqual(mismatch["error"]["code"], "INVALID_ARGUMENT")
            empty = _call_tool(mcp, "import_file", {"path": "  ", "format": "svg"})
            self.assertEqual(empty["error"]["code"], "INVALID_ARGUMENT")

    def test_asset_profile_exposes_import_file(self) -> None:
        from blmcp import create_server

        asset = {tool.name for tool in asyncio.run(create_server("asset").list_tools())}
        core = {tool.name for tool in asyncio.run(create_server("core").list_tools())}
        self.assertIn("import_file", asset)
        self.assertNotIn("import_file", core)


class TestSceneRefreshTool(unittest.TestCase):
    """AX-06: the refresh tool is registered on agent profiles."""

    def test_registered(self) -> None:
        from blmcp import create_server

        names = {tool.name for tool in asyncio.run(create_server("core").list_tools())}
        self.assertIn("scene_refresh", names)


if __name__ == "__main__":
    unittest.main()
