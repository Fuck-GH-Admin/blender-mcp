# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the offline context-cost benchmark helpers."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from blmcp.metrics.context_benchmark import compare_runs, schema_tax_rows, summarize_run


class TestSchemaTax(unittest.TestCase):
    def test_agent_profiles_cost_more_schema_than_official(self) -> None:
        rows = schema_tax_rows(["official", "core", "asset"])
        by_profile = {row["profile"]: row for row in rows}
        self.assertEqual(by_profile["official"]["tool_count"], 26)
        self.assertEqual(by_profile["core"]["tool_count"], 28)
        self.assertEqual(by_profile["asset"]["tool_count"], 31)
        self.assertGreater(
            by_profile["core"]["estimated_schema_tokens"],
            by_profile["official"]["estimated_schema_tokens"],
        )


class TestRunReport(unittest.TestCase):
    def _write_session(self, path: str, tool: str, ok: bool) -> None:
        entries = (
            {
                "timestamp": 1.0,
                "kind": "tool_schema",
                "profile": "core",
                "tool_count": 24,
                "schema_bytes": 96000,
                "estimated_schema_tokens": 24000,
            },
            {
                "timestamp": 2.0,
                "tool": tool,
                "ok": ok,
                "argument_bytes": 40,
                "result_bytes": 80,
                "generated_python_chars": 0,
                "estimated_argument_tokens": 10,
                "estimated_result_tokens": 20,
                "estimated_generated_python_tokens": 0,
            },
            {
                "timestamp": 4.5,
                "tool": tool,
                "ok": True,
                "argument_bytes": 20,
                "result_bytes": 40,
                "generated_python_chars": 0,
                "estimated_argument_tokens": 5,
                "estimated_result_tokens": 10,
                "estimated_generated_python_tokens": 0,
            },
        )
        with open(path, "w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")

    def test_summarize_run_aggregates_calls_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "metrics.jsonl")
            self._write_session(path, "object_create", ok=True)
            summary = summarize_run(path)
            self.assertEqual(summary["schema"]["tool_count"], 24)
            stats = summary["tools"]["object_create"]
            self.assertEqual(stats["calls"], 2)
            self.assertEqual(stats["ok"], 2)
            self.assertEqual(stats["errors"], 0)
            self.assertEqual(stats["argument_tokens"], 15)
            self.assertEqual(stats["result_tokens"], 30)
            self.assertAlmostEqual(summary["wall_time_seconds"], 3.5)
            self.assertEqual(summary["estimated_context_growth_tokens"], 24000 + 15 + 30)

    def test_compare_runs_diffs_totals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            baseline_path = os.path.join(directory, "baseline.jsonl")
            candidate_path = os.path.join(directory, "candidate.jsonl")
            self._write_session(baseline_path, "execute_blender_code", ok=False)
            self._write_session(candidate_path, "object_create", ok=True)
            result = compare_runs(baseline_path, candidate_path)
            delta = result["totals_delta_candidate_minus_baseline"]
            self.assertEqual(delta["tool_calls"], 0)
            self.assertEqual(delta["ok"], 1)
            self.assertEqual(delta["errors"], -1)
            self.assertIn("estimated_context_growth_tokens", delta)


if __name__ == "__main__":
    unittest.main()
