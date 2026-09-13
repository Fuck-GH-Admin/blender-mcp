# SPDX-License-Identifier: GPL-3.0-or-later
"""Server-side plumbing shared by semantic agent operations."""

from __future__ import annotations

import time

from blmcp.metrics import record_tool_call
from blmcp.security import SafeCodeViolation, validate_blender_code
from blmcp.state import get_runtime
from blmcp.tools_helpers.connection import send_code

__all__ = (
    "execute_fallback_code",
    "load_toolcode",
    "resolve_object",
    "resolve_objects",
    "run_mutation",
    "run_query",
    "wrap_fallback_code",
)


def load_toolcode(module_file: str) -> str:
    """Load an operation's Blender-side module using the official convention."""
    from blmcp.tools_helpers import toolcode_load_from_filepath, toolcode_wrap_with_calling_convention

    return toolcode_wrap_with_calling_convention(toolcode_load_from_filepath(module_file))


# Sentinel names used by `wrap_fallback_code`; never part of the tool contract.
_FALLBACK_BEFORE = "_blmcp_objects_before"


def wrap_fallback_code(code: str) -> str:
    """Wrap agent-generated code with a lightweight scene-change probe.

    The probe compares object name sets before and after execution and stores
    the verdict in the ``result`` dict (promoted to the envelope key
    ``scene_changed`` by :func:`execute_fallback_code`).  It deliberately does
    not advance the revision: only committed structured mutations do that.
    """
    prefix = (
        "import bpy as _blmcp_bpy\n"
        "{:s} = frozenset(obj.name for obj in _blmcp_bpy.data.objects)\n".format(_FALLBACK_BEFORE)
    )
    suffix = (
        "\ntry:\n"
        "    _blmcp_objects_after = frozenset(obj.name for obj in _blmcp_bpy.data.objects)\n"
        "    if isinstance(result, dict):\n"
        "        result[\"_scene_changed\"] = _blmcp_objects_after != {:s}\n"
        "        result[\"_scene_names\"] = sorted(_blmcp_objects_after)\n"
        "except Exception:  # noqa: BLE001 - the probe must never mask agent errors\n"
        "    pass\n"
    ).format(_FALLBACK_BEFORE)
    return prefix + code + suffix


def _short_message(value: object) -> str:
    lines = [line.strip() for line in str(value).splitlines() if line.strip()]
    return (lines[-1] if lines else "The Blender bridge returned an unspecified error.")[:320]


def _error(code: str, message: str, suggested_action: str | None = None) -> dict[str, object]:
    error: dict[str, object] = {"code": code, "message": message, "recoverable": True}
    if suggested_action:
        error["suggested_action"] = suggested_action
    return {"ok": False, "error": error, "revision": get_runtime().revision}


def _finish(tool: str, arguments: dict[str, object], result: dict[str, object], started: float, generated_python_chars: int) -> dict[str, object]:
    """Attach timing and append the local JSONL observation for one tool call."""
    record_tool_call(
        tool, arguments, result,
        generated_python_chars=generated_python_chars,
        duration_ms=(time.monotonic() - started) * 1000.0,
    )
    return result


def _bridge_result(response: dict[str, object]) -> dict[str, object]:
    if response.get("status") != "ok":
        return _error("BLENDER_EXECUTION_FAILED", _short_message(response.get("message")), "scene_summary")
    result = response.get("result")
    if not isinstance(result, dict):
        return _error("INVALID_BRIDGE_RESULT", "The Blender operation returned a non-object result.")
    return result


def resolve_object(identifier: str) -> str:
    return get_runtime().resolve_object(identifier)


def resolve_objects(identifiers: list[str]) -> list[str]:
    return [resolve_object(identifier) for identifier in identifiers]


def run_query(
    tool: str,
    arguments: dict[str, object],
    code: str,
    *,
    record: bool = True,
) -> dict[str, object]:
    """Run trusted read-only toolcode and normalize its envelope.

    ``record=False`` skips the built-in metrics entry for callers that must
    post-process the payload before recording (e.g. ``scene_refresh`` drops
    the raw name list the agent never sees).
    """
    started = time.monotonic()
    result = _bridge_result(send_code(code, strict_json=True))
    if result.get("ok") is True:
        result = dict(result)
        result["revision"] = get_runtime().revision
        get_runtime().register_references(result)
    return _finish(tool, arguments, result, started, 0) if record else result


def run_mutation(
    tool: str,
    arguments: dict[str, object],
    code: str,
    *,
    expected_revision: int | None = None,
    request_id: str | None = None,
) -> dict[str, object]:
    """Run trusted toolcode with revision checks and retry-safe acknowledgements."""
    started = time.monotonic()
    runtime = get_runtime()
    cached = runtime.completed_request(request_id)
    if cached is not None:
        return _finish(tool, arguments, cached, started, 0)
    if expected_revision is not None:
        stale = runtime.stale_error(expected_revision)
        if stale is not None:
            return _finish(tool, arguments, stale, started, 0)

    result = _bridge_result(send_code(code, strict_json=True))
    if result.get("ok") is not True:
        result = dict(result)
        result.setdefault("revision", runtime.revision)
        return _finish(tool, arguments, result, started, 0)
    return _finish(tool, arguments, runtime.commit(result, request_id), started, 0)


def execute_fallback_code(
    tool: str,
    arguments: dict[str, object],
    code: str,
    *,
    unsafe_python: bool,
    debug: bool,
) -> dict[str, object]:
    """Execute agent-generated code through the optional safe AST guard."""
    started = time.monotonic()
    if not unsafe_python:
        try:
            validate_blender_code(code)
        except SafeCodeViolation as ex:
            return _finish(
                tool, arguments,
                _error("SAFE_CODE_REJECTED", str(ex), "use_structured_tool_or_rewrite_code"),
                started, len(code),
            )

    response = send_code(wrap_fallback_code(code), strict_json=False)
    if response.get("status") != "ok":
        failure_result = _error("BLENDER_EXECUTION_FAILED", _short_message(response.get("message")), "search_api_docs")
        if debug:
            failure_result["debug"] = str(response.get("message", ""))[:4000]
        return _finish(tool, arguments, failure_result, started, len(code))
    result: dict[str, object] = {"ok": True, "result": response.get("result")}
    payload = result["result"]
    if isinstance(payload, dict):
        scene_changed = payload.pop("_scene_changed", None)
        if isinstance(scene_changed, bool):
            result["scene_changed"] = scene_changed
        names = payload.pop("_scene_names", None)
        if isinstance(names, list):
            get_runtime().update_known_objects(frozenset(str(name) for name in names))
    for key in ("stdout", "stderr"):
        if key in response:
            result[key] = str(response[key])[:4000]
    return _finish(tool, arguments, result, started, len(code))
