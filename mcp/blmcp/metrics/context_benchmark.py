# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline comparison helpers for context-cost measurements.

The schema tax of any profile is measured in-process without Blender.  Run
reports aggregate the JSONL file written when ``BLMCP_METRICS_PATH`` is set,
so an official-versus-next comparison only needs two recorded sessions.

Usage::

    uv run --project mcp python -m blmcp.metrics.context_benchmark schema-tax
    uv run --project mcp python -m blmcp.metrics.context_benchmark run-report run.jsonl
    uv run --project mcp python -m blmcp.metrics.context_benchmark compare baseline.jsonl candidate.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

__all__ = ("compare_runs", "main", "schema_tax_rows", "summarize_run")

_PROFILE_CHOICES = ("official", "core", "creator", "asset", "full")
_TOKEN_KEYS = (
    "estimated_argument_tokens",
    "estimated_result_tokens",
    "estimated_generated_python_tokens",
)


def schema_tax_rows(profiles: list[str]) -> list[dict[str, Any]]:
    """Measure the frozen tool-schema cost of each profile in-process."""
    import blmcp  # pylint: disable=import-outside-toplevel,cyclic-import

    rows: list[dict[str, Any]] = []
    for profile in profiles:
        schema = blmcp.metrics.context.tool_schema_snapshot(blmcp.create_server(profile))
        size = len(json.dumps(schema, ensure_ascii=False, default=str).encode("utf-8"))
        rows.append({
            "profile": profile,
            "tool_count": len(schema),
            "schema_bytes": size,
            "estimated_schema_tokens": (size + 3) // 4,
        })
    return rows


def summarize_run(metrics_path: str | Path) -> dict[str, Any]:
    """Aggregate one ``BLMCP_METRICS_PATH`` JSONL session into compact metrics."""
    schema_row: dict[str, Any] | None = None
    per_tool: dict[str, dict[str, int]] = {}
    timestamps: list[float] = []
    with Path(metrics_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            try:
                timestamps.append(float(entry.get("timestamp", 0.0)))
            except (TypeError, ValueError):
                pass
            if entry.get("kind") == "tool_schema":
                schema_row = {
                    "profile": entry.get("profile"),
                    "tool_count": entry.get("tool_count"),
                    "schema_bytes": entry.get("schema_bytes"),
                    "estimated_schema_tokens": entry.get("estimated_schema_tokens"),
                }
                continue
            stats = per_tool.setdefault(str(entry.get("tool", "?")), {
                "calls": 0, "ok": 0, "errors": 0,
                "argument_tokens": 0, "result_tokens": 0, "generated_python_tokens": 0,
                "duration_ms_total": 0.0, "duration_ms_max": 0.0,
            })
            stats["calls"] += 1
            if entry.get("ok") is True:
                stats["ok"] += 1
            elif entry.get("ok") is False:
                stats["errors"] += 1
            for key in _TOKEN_KEYS:
                stats[key.replace("estimated_", "").replace("_tokens", "") + "_tokens"] += int(entry.get(key, 0) or 0)
            duration = entry.get("duration_ms")
            if isinstance(duration, (int, float)):
                stats["duration_ms_total"] += float(duration)
                stats["duration_ms_max"] = max(stats["duration_ms_max"], float(duration))

    totals: dict[str, int] = {"tool_calls": 0, "ok": 0, "errors": 0}
    for key in ("argument_tokens", "result_tokens", "generated_python_tokens"):
        totals[key] = sum(stats[key] for stats in per_tool.values())
    for key in ("ok", "errors"):
        totals[key] = sum(stats[key] for stats in per_tool.values())
    totals["tool_calls"] = sum(stats["calls"] for stats in per_tool.values())
    schema_tokens = int(schema_row["estimated_schema_tokens"]) if schema_row else 0
    return {
        "schema": schema_row,
        "tools": dict(sorted(per_tool.items())),
        "totals": totals,
        "wall_time_seconds": round(max(timestamps) - min(timestamps), 3) if len(timestamps) > 1 else 0.0,
        "estimated_context_growth_tokens": (
            schema_tokens + totals["argument_tokens"] + totals["result_tokens"] + totals["generated_python_tokens"]
        ),
    }


def compare_runs(baseline_path: str | Path, candidate_path: str | Path) -> dict[str, Any]:
    """Summarize two recorded sessions and diff their totals (candidate minus baseline)."""
    baseline = summarize_run(baseline_path)
    candidate = summarize_run(candidate_path)
    delta: dict[str, int] = {}
    for key, value in candidate["totals"].items():
        delta[key] = value - baseline["totals"].get(key, 0)
    delta["estimated_context_growth_tokens"] = (
        candidate["estimated_context_growth_tokens"] - baseline["estimated_context_growth_tokens"]
    )
    return {
        "baseline": baseline,
        "candidate": candidate,
        "totals_delta_candidate_minus_baseline": delta,
    }


def _print_rows(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    line = "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    print(line)
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))


def _command_schema_tax(args: argparse.Namespace) -> int:
    profiles = [profile.strip() for profile in args.profiles.split(",") if profile.strip()]
    rows = schema_tax_rows(profiles)
    _print_rows(
        ("profile", "tools", "schema_bytes", "est_tokens"),
        [
            (row["profile"], str(row["tool_count"]), str(row["schema_bytes"]), str(row["estimated_schema_tokens"]))
            for row in rows
        ],
    )
    return 0


def _command_run_report(args: argparse.Namespace) -> int:
    summary = summarize_run(args.metrics_path)
    schema = summary["schema"] or {}
    print("schema: profile={!r} tools={!r} est_tokens={!r}".format(
        schema.get("profile"), schema.get("tool_count"), schema.get("estimated_schema_tokens"),
    ))
    _print_rows(
        ("tool", "calls", "ok", "errors", "arg_tok", "result_tok", "gen_py_tok", "ms_total", "ms_max"),
        [
            (
                name, str(stats["calls"]), str(stats["ok"]), str(stats["errors"]),
                str(stats["argument_tokens"]), str(stats["result_tokens"]), str(stats["generated_python_tokens"]),
                "{:.0f}".format(stats.get("duration_ms_total", 0.0)), "{:.0f}".format(stats.get("duration_ms_max", 0.0)),
            )
            for name, stats in summary["tools"].items()
        ] or [("(no calls)", "-", "-", "-", "-", "-", "-", "-", "-")],
    )
    print("totals: {!r}".format(summary["totals"]))
    print("estimated_context_growth_tokens: {:d}".format(summary["estimated_context_growth_tokens"]))
    print("wall_time_seconds: {!r}".format(summary["wall_time_seconds"]))
    return 0


def _command_compare(args: argparse.Namespace) -> int:
    result = compare_runs(args.baseline_path, args.candidate_path)
    print(json.dumps(result["totals_delta_candidate_minus_baseline"], indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Context-cost benchmark helpers for super-blender-mcp-next.")
    commands = parser.add_subparsers(dest="command", required=True)

    schema_tax = commands.add_parser("schema-tax", help="Measure the tool-schema tax of one or more profiles.")
    schema_tax.add_argument("--profiles", default="official,core,creator,asset,full", help="Comma-separated profiles.")
    schema_tax.set_defaults(handler=_command_schema_tax)

    run_report = commands.add_parser("run-report", help="Aggregate one recorded metrics JSONL session.")
    run_report.add_argument("metrics_path", help="Path to the BLMCP_METRICS_PATH JSONL file.")
    run_report.set_defaults(handler=_command_run_report)

    compare = commands.add_parser("compare", help="Diff two recorded sessions (candidate minus baseline).")
    compare.add_argument("baseline_path", help="Metrics JSONL of the baseline run (e.g. official profile).")
    compare.add_argument("candidate_path", help="Metrics JSONL of the candidate run (e.g. core profile).")
    compare.set_defaults(handler=_command_compare)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
