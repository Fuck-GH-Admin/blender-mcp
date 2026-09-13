# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-side implementation of deterministic camera operations."""

from __future__ import annotations

__all__ = ('CreateParams', 'Params', 'main')

import math
from typing import NamedTuple


class Params(NamedTuple):
    objects: list[str]
    camera: str | None
    view: str
    padding: float


class CreateParams(NamedTuple):
    name: str
    location: list[float] | None
    rotation: list[float] | None
    target: list[float] | None
    lens: float | None


# @include_begin: _toolcode_runtime.py
# @include_end


_VIEW_DIRECTIONS = {
    "FRONT": (0.0, -1.0, 0.0),
    "BACK": (0.0, 1.0, 0.0),
    "LEFT": (-1.0, 0.0, 0.0),
    "RIGHT": (1.0, 0.0, 0.0),
    "TOP": (0.0, 0.0, 1.0),
    "THREE_QUARTER": (1.0, -1.0, 0.75),
}


def _camera(name: str | None) -> object:
    import bpy  # pylint: disable=import-error,no-name-in-module

    if name is not None:
        camera = require_object(name)
        if camera.type != "CAMERA":
            raise ToolError("INVALID_ARGUMENT", "Object {!r} is not a camera.".format(name))
        return camera
    if bpy.context.scene.camera is not None:
        return bpy.context.scene.camera
    data = bpy.data.cameras.new("MCP_Camera")
    camera = bpy.data.objects.new("MCP_Camera", data)
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    return camera


def _apply_aim(obj: object, location: tuple[float, float, float] | None, rotation: tuple[float, float, float] | None, target: tuple[float, float, float] | None, changed: list[str]) -> None:
    """Set orientation from rotation or a world-space look-at target."""
    from mathutils import Vector  # pylint: disable=import-error,no-name-in-module

    if rotation is not None and target is not None:
        raise ToolError("INVALID_ARGUMENT", "Provide either rotation or target, not both.")
    if location is not None:
        obj.location = location
        changed.append("location")
    if rotation is not None:
        obj.rotation_euler = rotation
        changed.append("rotation")
    if target is not None:
        target_vec = Vector(target)
        if target_vec == obj.location:
            raise ToolError("INVALID_ARGUMENT", "target must differ from the camera location.")
        obj.rotation_euler = (target_vec - obj.location).to_track_quat("-Z", "Y").to_euler()
        changed.append("rotation")


def _frame(params: Params) -> Result:
    before = scene_snapshot()
    try:
        from mathutils import Vector  # pylint: disable=import-error,no-name-in-module

        if not params.objects:
            raise ToolError("INVALID_ARGUMENT", "objects must contain at least one object name.")
        if params.view not in _VIEW_DIRECTIONS:
            raise ToolError("INVALID_ARGUMENT", "view is not supported.")
        if not isinstance(params.padding, (int, float)) or isinstance(params.padding, bool) or not 0.0 <= params.padding < 0.75:
            raise ToolError("INVALID_ARGUMENT", "padding must be between 0 and 0.75.")
        objects = [require_object(name) for name in params.objects]
        points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
        if not points:
            raise ToolError("FRAME_FAILED", "The selected objects do not have bounds.")
        target = sum(points, Vector()) / len(points)
        radius = max((point - target).length for point in points)
        camera = _camera(params.camera)
        direction = Vector(_VIEW_DIRECTIONS[params.view]).normalized()
        half_angle = max(float(camera.data.angle) / 2.0, math.radians(1.0))
        distance = max(0.5, radius / max(math.sin(half_angle) * (1.0 - params.padding), 0.01))
        camera.location = target + direction * distance
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.clip_end = max(float(camera.data.clip_end), distance + radius * 4.0)
        import bpy  # pylint: disable=import-error,no-name-in-module

        bpy.context.scene.camera = camera
        return success("camera_frame", camera, ["framed"], before)
    except ToolError as ex:
        return failure("camera_frame", ex)


def _create_or_update(params: CreateParams) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        if not params.name.strip():
            raise ToolError("INVALID_ARGUMENT", "name cannot be empty.")
        if params.lens is not None and (
            not isinstance(params.lens, (int, float)) or isinstance(params.lens, bool)
            or not math.isfinite(params.lens) or not 1.0 <= params.lens <= 10000.0
        ):
            raise ToolError("INVALID_ARGUMENT", "lens must be a finite value between 1 and 10000 millimetres.")
        location = vec3(params.location, "location")
        rotation = vec3(params.rotation, "rotation")
        target = vec3(params.target, "target")
        obj = bpy.data.objects.get(params.name)
        created = obj is None
        if obj is None:
            data = bpy.data.cameras.new(params.name)
            obj = bpy.data.objects.new(params.name, data)
            bpy.context.scene.collection.objects.link(obj)
        if obj.type != "CAMERA":
            raise ToolError("NAME_CONFLICT", "Object {!r} exists but is not a camera.".format(params.name))
        changed = ["created"] if created else []
        _apply_aim(obj, location, rotation, target, changed)
        if params.lens is not None:
            obj.data.lens = float(params.lens)
            changed.append("lens")
        if bpy.context.scene.camera is None:
            bpy.context.scene.camera = obj
            changed.append("scene_camera")
        return success("camera_create_or_update", obj, changed or ["camera"], before)
    except ToolError as ex:
        return failure("camera_create_or_update", ex)


def main(params: object) -> Result:
    if isinstance(params, CreateParams):
        return _create_or_update(params)
    if isinstance(params, Params):
        return _frame(params)
    return failure("camera_operation", ToolError("INVALID_ARGUMENT", "Unsupported camera operation parameters."))
