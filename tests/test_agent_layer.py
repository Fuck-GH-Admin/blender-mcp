# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the agent-native layer that do not require Blender."""

from __future__ import annotations

import os
import json
import tempfile
import unittest

from blmcp.agent_ops._bridge import load_toolcode
from blmcp import create_server
from blmcp.metrics import record_schema_tax, record_tool_call
from blmcp.profiles import agent_modules, official_modules
from blmcp.security import SafeCodeViolation, validate_blender_code
from blmcp.state.runtime import AgentRuntime


class TestSafeCode(unittest.TestCase):
    def test_allows_normal_blender_code(self) -> None:
        validate_blender_code("import bpy\nbpy.ops.mesh.primitive_cube_add()\nresult = {'ok': True}")

    def test_rejects_unsafe_operations(self) -> None:
        cases = (
            "import os",
            "open('/tmp/data', 'w')",
            "bpy.app.handlers.load_post.append(lambda _: None)",
            "bpy.ops.wm.quit_blender()",
            "value.__class__",
        )
        for code in cases:
            with self.subTest(code=code), self.assertRaises(SafeCodeViolation):
                validate_blender_code(code)


class TestRuntime(unittest.TestCase):
    def test_identity_revision_and_request_replay_are_server_local(self) -> None:
        runtime = AgentRuntime()
        runtime.register_references({"target": {"id": "obj_42", "name": "Cube"}})
        self.assertEqual(runtime.resolve_object("obj_42"), "Cube")
        self.assertIsNone(runtime.stale_error(0))
        self.assertEqual(runtime.stale_error(1)["error"]["code"], "STALE_SCENE")  # type: ignore[index]

        committed = runtime.commit({"ok": True, "target": {"id": "obj_42", "name": "Cube"}}, "request-1")
        self.assertEqual(committed["revision"], 1)
        replay = runtime.completed_request("request-1")
        assert replay is not None
        self.assertEqual(replay["status"], "already_completed")
        self.assertEqual(replay["action_id"], committed["action_id"])


class TestProfilesAndToolcode(unittest.TestCase):
    def test_core_profile_has_no_cli_or_asset_modules(self) -> None:
        modules = official_modules("core", ("execute_blender_code", "get_objects_summary", "render_viewport_to_path"))
        self.assertEqual(modules, ("execute_blender_code", "get_objects_summary"))
        self.assertEqual(agent_modules("official"), ())
        self.assertIn("camera", agent_modules("core"))

    def test_agent_toolcode_expands_and_compiles(self) -> None:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp", "blmcp", "agent_ops")
        for name in ("observation", "object", "modifier", "material", "camera", "light", "render"):
            with self.subTest(name=name):
                source = load_toolcode(os.path.join(base, name + ".py"))
                self.assertNotIn("# @include_begin", source)
                compile(source, name + "_toolcode.py", "exec")


class TestMetrics(unittest.TestCase):
    def test_records_schema_and_calls_only_to_the_opted_in_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = os.path.join(directory, "metrics.jsonl")
            previous = os.environ.get("BLMCP_METRICS_PATH")
            os.environ["BLMCP_METRICS_PATH"] = destination
            try:
                record_schema_tax(create_server(), "core")
                record_tool_call("test_tool", {"object": "Cube"}, {"ok": True})
            finally:
                if previous is None:
                    del os.environ["BLMCP_METRICS_PATH"]
                else:
                    os.environ["BLMCP_METRICS_PATH"] = previous
            with open(destination, encoding="utf-8") as handle:
                entries = [json.loads(line) for line in handle]
        self.assertEqual(entries[0]["kind"], "tool_schema")
        self.assertEqual(entries[0]["tool_count"], 28)
        self.assertEqual(entries[1]["tool"], "test_tool")


if __name__ == "__main__":
    unittest.main()
