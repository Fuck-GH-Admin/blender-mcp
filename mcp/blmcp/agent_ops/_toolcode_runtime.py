# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared Blender-side helpers embedded into every structured operation."""

__all__ = ('Result', 'ToolError', 'color4', 'failure', 'object_ref', 'object_ref_from_state', 'require_object', 'require_object_mode', 'scene_snapshot', 'set_active', 'state_delta', 'success', 'vec3')

import math
from typing import Any, NamedTuple


class ToolError(RuntimeError):
    def __init__(self, code: str, message: str, suggested_action: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggested_action = suggested_action


class Result(NamedTuple):
    ok: bool
    action: str | None = None
    target: dict[str, str] | None = None
    changed: list[str] | None = None
    delta: dict[str, object] | None = None
    error: dict[str, object] | None = None


def _object_id(obj: Any) -> str:
    return "obj_{:x}".format(obj.as_pointer())


def object_ref(obj: Any) -> dict[str, str]:
    return {"id": _object_id(obj), "name": obj.name}


def require_object(name: str) -> Any:
    import bpy  # pylint: disable=import-error,no-name-in-module

    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ToolError(
            "OBJECT_NOT_FOUND",
            "Object {!r} does not exist.".format(name),
            "search_objects",
        )
    return obj


def require_object_mode() -> None:
    import bpy  # pylint: disable=import-error,no-name-in-module

    if bpy.context.mode == "OBJECT":
        return
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except RuntimeError as ex:
        raise ToolError("INVALID_CONTEXT", str(ex), "switch_to_object_mode") from ex


def set_active(obj: Any) -> None:
    import bpy  # pylint: disable=import-error,no-name-in-module

    for other in bpy.context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def vec3(value: list[float] | tuple[float, float, float] | None, field: str) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ToolError("INVALID_ARGUMENT", "{:s} must contain exactly three numbers.".format(field))
    converted = []
    for component in value:
        if not isinstance(component, (int, float)) or isinstance(component, bool) or not math.isfinite(component):
            raise ToolError("INVALID_ARGUMENT", "{:s} must contain finite numbers.".format(field))
        converted.append(float(component))
    return (converted[0], converted[1], converted[2])


def color4(value: list[float] | tuple[float, ...] | None, field: str) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) not in (3, 4):
        raise ToolError("INVALID_ARGUMENT", "{:s} must contain three or four values from 0 to 1.".format(field))
    converted = vec3(list(value[:3]), field)
    assert converted is not None
    alpha = 1.0 if len(value) == 3 else value[3]
    if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not math.isfinite(alpha):
        raise ToolError("INVALID_ARGUMENT", "{:s} must contain finite numbers.".format(field))
    all_values = (*converted, float(alpha))
    if any(component < 0.0 or component > 1.0 for component in all_values):
        raise ToolError("INVALID_ARGUMENT", "{:s} values must be between 0 and 1.".format(field))
    return all_values


def _state_of(obj: Any) -> dict[str, object]:
    return {
        "id": _object_id(obj),
        "name": obj.name,
        "type": obj.type,
        # A matrix is canonical whereas Euler decomposition can pick equivalent
        # angles differently on consecutive dependency-graph evaluations.
        "matrix_world": [round(float(value), 6) for row in obj.matrix_world for value in row],
        "parent": _object_id(obj.parent) if obj.parent else None,
        "hide_viewport": bool(obj.hide_viewport),
        "hide_render": bool(obj.hide_render),
        "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
        "modifiers": [(modifier.name, modifier.type) for modifier in obj.modifiers],
    }


def scene_snapshot() -> dict[str, object]:
    import bpy  # pylint: disable=import-error,no-name-in-module

    objects = {_object_id(obj): _state_of(obj) for obj in bpy.data.objects}
    active = bpy.context.view_layer.objects.active
    return {
        "objects": objects,
        "active": object_ref(active) if active else None,
        "selected": sorted((object_ref(obj) for obj in bpy.context.selected_objects), key=lambda ref: ref["id"]),
    }


def state_delta(before: dict[str, object], after: dict[str, object]) -> dict[str, object]:
    before_objects = before["objects"]
    after_objects = after["objects"]
    assert isinstance(before_objects, dict) and isinstance(after_objects, dict)
    before_ids = set(before_objects)
    after_ids = set(after_objects)

    created = [object_ref_from_state(after_objects[identifier]) for identifier in sorted(after_ids - before_ids)]
    deleted = [object_ref_from_state(before_objects[identifier]) for identifier in sorted(before_ids - after_ids)]
    renamed = [
        {"id": identifier, "from": before_objects[identifier]["name"], "to": after_objects[identifier]["name"]}
        for identifier in sorted(before_ids & after_ids)
        if before_objects[identifier]["name"] != after_objects[identifier]["name"]
    ]
    changed = [
        object_ref_from_state(after_objects[identifier])
        for identifier in sorted(before_ids & after_ids)
        if before_objects[identifier] != after_objects[identifier]
    ]
    return {
        "created": created[:20],
        "deleted": deleted[:20],
        "renamed": renamed[:20],
        "changed": changed[:20],
        "active": after["active"],
        "selected": after["selected"][:20],
        "truncated": any(len(items) > 20 for items in (created, deleted, renamed, changed)),
    }


def object_ref_from_state(state: dict[str, object]) -> dict[str, str]:
    return {"id": str(state["id"]), "name": str(state["name"])}


def success(action: str, target: Any | dict[str, str] | None, changed: list[str], before: dict[str, object]) -> Result:
    after = scene_snapshot()
    return Result(
        ok=True,
        action=action,
        target=target if isinstance(target, dict) else (object_ref(target) if target is not None else None),
        changed=changed,
        delta=state_delta(before, after),
    )


def failure(action: str, error: ToolError) -> Result:
    detail: dict[str, object] = {
        "code": error.code,
        "message": error.message,
        "recoverable": True,
    }
    if error.suggested_action:
        detail["suggested_action"] = error.suggested_action
    return Result(ok=False, action=action, changed=[], error=detail)
