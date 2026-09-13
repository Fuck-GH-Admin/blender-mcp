# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-side implementation of light creation and updates."""

from __future__ import annotations

__all__ = ('Params', 'main')

import math
from typing import NamedTuple


class Params(NamedTuple):
    name: str
    type: str
    energy: float | None
    color: list[float] | None
    location: list[float] | None
    rotation: list[float] | None
    size: float | None
    target: list[float] | None


# @include_begin: _toolcode_runtime.py
# @include_end


def _non_negative(value: float | None, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
        raise ToolError("INVALID_ARGUMENT", "{:s} must be a finite non-negative number.".format(field))
    return float(value)


def main(params: Params) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        if not params.name.strip():
            raise ToolError("INVALID_ARGUMENT", "name cannot be empty.")
        if params.type not in {"POINT", "SUN", "SPOT", "AREA"}:
            raise ToolError("INVALID_ARGUMENT", "type must be POINT, SUN, SPOT, or AREA.")
        if params.rotation is not None and params.target is not None:
            raise ToolError("INVALID_ARGUMENT", "Provide either rotation or target, not both.")
        obj = bpy.data.objects.get(params.name)
        created = obj is None
        if obj is None:
            data = bpy.data.lights.new(params.name, params.type)
            obj = bpy.data.objects.new(params.name, data)
            bpy.context.scene.collection.objects.link(obj)
        if obj.type != "LIGHT":
            raise ToolError("NAME_CONFLICT", "Object {!r} exists but is not a light.".format(params.name))
        if obj.data.type != params.type:
            raise ToolError("LIGHT_TYPE_MISMATCH", "Existing light {!r} has type {!r}.".format(params.name, obj.data.type))
        changed = ["created"] if created else []
        energy = _non_negative(params.energy, "energy")
        if energy is not None:
            obj.data.energy = energy
            changed.append("energy")
        color = color4(params.color, "color")
        if color is not None:
            obj.data.color = color[:3]
            changed.append("color")
        location = vec3(params.location, "location")
        if location is not None:
            obj.location = location
            changed.append("location")
        rotation = vec3(params.rotation, "rotation")
        if rotation is not None:
            obj.rotation_euler = rotation
            changed.append("rotation")
        if params.target is not None:
            from mathutils import Vector  # pylint: disable=import-error,no-name-in-module

            target_point = vec3(params.target, "target")
            if target_point is None:
                raise ToolError("INVALID_ARGUMENT", "target cannot be empty.")
            target_vec = Vector(target_point)
            if target_vec == obj.location:
                raise ToolError("INVALID_ARGUMENT", "target must differ from the light location.")
            obj.rotation_euler = (target_vec - obj.location).to_track_quat("-Z", "Y").to_euler()
            changed.append("rotation")
        size = _non_negative(params.size, "size")
        if size is not None:
            if not hasattr(obj.data, "shape") and obj.data.type != "AREA":
                raise ToolError("UNSUPPORTED_LIGHT_PROPERTY", "size is currently supported only for area lights.")
            obj.data.shape = "DISK"
            obj.data.size = size
            changed.append("size")
        return success("light_create_or_update", obj, changed or ["light"], before)
    except ToolError as ex:
        return failure("light_create_or_update", ex)
