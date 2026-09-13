# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-side implementation of object-level modeling actions."""

from __future__ import annotations

__all__ = ('Params', 'main')

from typing import NamedTuple


class Params(NamedTuple):
    object: str
    action: str
    others: list[str] | None
    apply_location: bool
    apply_rotation: bool
    apply_scale: bool
    origin: str


# @include_begin: _toolcode_runtime.py
# @include_end


_ORIGIN_TYPES = {
    "GEOMETRY": "ORIGIN_GEOMETRY",
    "CURSOR": "ORIGIN_CURSOR",
    "GEOMETRY_CENTER": "ORIGIN_GEOMETRY_CENTER",
}


def _join(params: Params) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        obj = require_object(params.object)
        if obj.type != "MESH":
            raise ToolError("INVALID_ARGUMENT", "join requires mesh objects; {!r} is {!s}.".format(obj.name, obj.type))
        if not params.others:
            raise ToolError("INVALID_ARGUMENT", "join requires at least one object in others.")
        sources = []
        for name in params.others:
            source = require_object(name)
            if source is obj:
                raise ToolError("INVALID_ARGUMENT", "others must not repeat the target object.")
            if source.type != "MESH":
                raise ToolError(
                    "INVALID_ARGUMENT",
                    "join requires mesh objects; {!r} is {!s}.".format(source.name, source.type),
                )
            sources.append(source)
        require_object_mode()
        set_active(obj)
        for source in sources:
            source.select_set(True)
        try:
            bpy.ops.object.join()
        except RuntimeError as ex:
            raise ToolError("JOIN_FAILED", str(ex)) from ex
        return success("object_manage", obj, ["joined"], before)
    except ToolError as ex:
        return failure("object_manage", ex)


def _apply_transform(params: Params) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        if not (params.apply_location or params.apply_rotation or params.apply_scale):
            raise ToolError("INVALID_ARGUMENT", "Enable at least one of apply_location, apply_rotation, apply_scale.")
        obj = require_object(params.object)
        require_object_mode()
        set_active(obj)
        try:
            bpy.ops.object.transform_apply(
                location=params.apply_location, rotation=params.apply_rotation, scale=params.apply_scale,
            )
        except RuntimeError as ex:
            raise ToolError("APPLY_FAILED", str(ex)) from ex
        changed = [
            name for name, enabled in (
                ("location", params.apply_location),
                ("rotation", params.apply_rotation),
                ("scale", params.apply_scale),
            ) if enabled
        ]
        return success("object_manage", obj, changed, before)
    except ToolError as ex:
        return failure("object_manage", ex)


def _set_origin(params: Params) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        origin_type = _ORIGIN_TYPES.get(params.origin)
        if origin_type is None:
            raise ToolError("INVALID_ARGUMENT", "origin must be one of GEOMETRY, CURSOR, GEOMETRY_CENTER.")
        obj = require_object(params.object)
        require_object_mode()
        set_active(obj)
        try:
            bpy.ops.object.origin_set(type=origin_type)
        except RuntimeError as ex:
            raise ToolError("ORIGIN_FAILED", str(ex)) from ex
        return success("object_manage", obj, ["origin"], before)
    except ToolError as ex:
        return failure("object_manage", ex)


def _shade(params: Params, smooth: bool) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        obj = require_object(params.object)
        require_object_mode()
        set_active(obj)
        try:
            if smooth:
                bpy.ops.object.shade_smooth()
            else:
                bpy.ops.object.shade_flat()
        except RuntimeError as ex:
            raise ToolError("SHADE_FAILED", str(ex)) from ex
        return success("object_manage", obj, ["shade_smooth" if smooth else "shade_flat"], before)
    except ToolError as ex:
        return failure("object_manage", ex)


def main(params: object) -> Result:
    if not isinstance(params, Params):
        return failure("object_manage", ToolError("INVALID_ARGUMENT", "Unsupported object_manage parameters."))
    if params.action == "join":
        return _join(params)
    if params.action == "apply_transform":
        return _apply_transform(params)
    if params.action == "set_origin":
        return _set_origin(params)
    if params.action == "shade_smooth":
        return _shade(params, smooth=True)
    if params.action == "shade_flat":
        return _shade(params, smooth=False)
    return failure("object_manage", ToolError("INVALID_ARGUMENT", "Unknown action {!r}.".format(params.action)))
