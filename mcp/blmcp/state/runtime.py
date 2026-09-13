# SPDX-License-Identifier: GPL-3.0-or-later
"""Small server-local state used by the Demo operation layer.

The registry deliberately does not write IDs into a ``.blend`` file.  IDs are
valid only for the lifetime of this MCP server and fall back to object names.
"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

__all__ = ("AgentRuntime", "get_runtime", "object_name_diff", "reset_runtime")

_DIFF_LIMIT = 32


def object_name_diff(before: frozenset[str] | None, after: frozenset[str]) -> dict[str, object]:
    """Compare two object-name snapshots; ``before is None`` means no baseline yet."""
    if before is None:
        return {"created": [], "deleted": [], "truncated": False}
    created = sorted(after - before)
    deleted = sorted(before - after)
    return {
        "created": created[:_DIFF_LIMIT],
        "deleted": deleted[:_DIFF_LIMIT],
        "truncated": len(created) > _DIFF_LIMIT or len(deleted) > _DIFF_LIMIT,
    }


@dataclass
class AgentRuntime:
    revision: int = 0
    _next_action: int = 1
    _object_names: dict[str, str] = field(default_factory=dict)
    _completed_requests: OrderedDict[str, dict[str, Any]] = field(default_factory=OrderedDict)
    _known_objects: frozenset[str] | None = None

    def resolve_object(self, identifier: str) -> str:
        """Resolve a session ID when known, otherwise treat it as an object name."""
        return self._object_names.get(identifier, identifier)

    def register_references(self, value: object) -> None:
        """Record every ``{id, name}`` reference in a compact result recursively."""
        if isinstance(value, dict):
            identity = value.get("id")
            name = value.get("name")
            if isinstance(identity, str) and isinstance(name, str):
                self._object_names[identity] = name
            for child in value.values():
                self.register_references(child)
        elif isinstance(value, list):
            for child in value:
                self.register_references(child)

    def stale_error(self, expected_revision: int) -> dict[str, object] | None:
        if expected_revision != self.revision:
            return {
                "ok": False,
                "error": {
                    "code": "STALE_SCENE",
                    "message": "Scene revision does not match the expected revision.",
                    "recoverable": True,
                    "suggested_action": "scene_summary",
                    "expected_revision": expected_revision,
                    "current_revision": self.revision,
                },
                "revision": self.revision,
            }
        return None

    def completed_request(self, request_id: str | None) -> dict[str, object] | None:
        if not request_id:
            return None
        result = self._completed_requests.get(request_id)
        if result is None:
            return None
        cached = deepcopy(result)
        cached["status"] = "already_completed"
        return cached

    def refresh_known_objects(self, names: frozenset[str]) -> dict[str, object]:
        """Re-baseline the scene's known object names and return what changed."""
        diff = object_name_diff(self._known_objects, names)
        self._known_objects = names
        return diff

    def update_known_objects(self, names: frozenset[str]) -> None:
        """Replace the baseline with live truth (e.g. from fallback probes)."""
        self._known_objects = names

    def _note_delta_objects(self, committed: dict[str, object]) -> None:
        """Keep the known-object baseline current across structured mutations."""
        if self._known_objects is None:
            self._known_objects = frozenset()
        delta = committed.get("delta")
        if not isinstance(delta, dict):
            return
        known = set(self._known_objects)
        for key, add in (("created", True), ("deleted", False)):
            refs = delta.get(key)
            if not isinstance(refs, list):
                continue
            for ref in refs:
                if isinstance(ref, dict) and isinstance(ref.get("name"), str):
                    if add:
                        known.add(ref["name"])
                    else:
                        known.discard(ref["name"])
        self._known_objects = frozenset(known)

    def commit(self, result: dict[str, object], request_id: str | None) -> dict[str, object]:
        """Assign action/revision metadata after a successful mutation."""
        committed = deepcopy(result)
        self.revision += 1
        committed["action_id"] = "act_{:06d}".format(self._next_action)
        self._next_action += 1
        committed["revision"] = self.revision
        self.register_references(committed)
        self._note_delta_objects(committed)
        if request_id:
            self._completed_requests[request_id] = deepcopy(committed)
            while len(self._completed_requests) > 128:
                self._completed_requests.popitem(last=False)
        return committed


_runtime = AgentRuntime()


def get_runtime() -> AgentRuntime:
    return _runtime


def reset_runtime() -> None:
    """Reset state for tests or a freshly created MCP server."""
    global _runtime
    _runtime = AgentRuntime()
