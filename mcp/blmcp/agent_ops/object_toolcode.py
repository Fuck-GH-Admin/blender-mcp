# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-side implementation of semantic object tools."""


from __future__ import annotations

__all__ = ('CreateParams', 'DeleteParams', 'DuplicateParams', 'ParentParams', 'PropertiesParams', 'TransformParams', 'create', 'delete', 'duplicate', 'main', 'parent', 'set_properties', 'transform')

from typing import NamedTuple


class CreateParams(NamedTuple):
    primitive: str
    name: str | None
    location: list[float] | None
    rotation: list[float] | None
    scale: list[float] | None


class TransformParams(NamedTuple):
    object: str
    location: list[float] | None
    rotation: list[float] | None
    scale: list[float] | None
    space: str


class DeleteParams(NamedTuple):
    object: str


class DuplicateParams(NamedTuple):
    object: str
    new_name: str | None
    linked_data: bool


class PropertiesParams(NamedTuple):
    object: str
    name: str | None
    visible: bool | None
    render_visible: bool | None
    display_type: str | None


class ParentParams(NamedTuple):
    object: str
    parent: str | None
    keep_world_transform: bool


# @include_begin: _toolcode_runtime.py
# @include_end


def _create_primitive(primitive: str, location: tuple[float, float, float], rotation: tuple[float, float, float]) -> object:
    import bpy  # pylint: disable=import-error,no-name-in-module

    operators = {
        "CUBE": bpy.ops.mesh.primitive_cube_add,
        "UV_SPHERE": bpy.ops.mesh.primitive_uv_sphere_add,
        "ICO_SPHERE": bpy.ops.mesh.primitive_ico_sphere_add,
        "CYLINDER": bpy.ops.mesh.primitive_cylinder_add,
        "CONE": bpy.ops.mesh.primitive_cone_add,
        "TORUS": bpy.ops.mesh.primitive_torus_add,
        "PLANE": bpy.ops.mesh.primitive_plane_add,
        "MONKEY": bpy.ops.mesh.primitive_monkey_add,
    }
    operator = operators.get(primitive)
    if operator is None:
        raise ToolError("INVALID_ARGUMENT", "Unsupported primitive {!r}.".format(primitive))
    try:
        operator(location=location, rotation=rotation)
    except RuntimeError as ex:
        raise ToolError("INVALID_CONTEXT", str(ex), "switch_to_object_mode") from ex
    obj = bpy.context.active_object
    if obj is None:
        raise ToolError("CREATE_FAILED", "Blender did not create an active object.")
    return obj


def create(params: CreateParams) -> Result:
    before = scene_snapshot()
    try:
        require_object_mode()
        location = vec3(params.location, "location") or (0.0, 0.0, 0.0)
        rotation = vec3(params.rotation, "rotation") or (0.0, 0.0, 0.0)
        scale = vec3(params.scale, "scale")
        obj = _create_primitive(params.primitive, location, rotation)
        if scale is not None:
            obj.scale = scale
        if params.name is not None:
            if not params.name.strip():
                raise ToolError("INVALID_ARGUMENT", "name cannot be empty.")
            obj.name = params.name
        return success("object_create", obj, ["created"], before)
    except ToolError as ex:
        return failure("object_create", ex)


def transform(params: TransformParams) -> Result:
    before = scene_snapshot()
    try:
        if params.location is None and params.rotation is None and params.scale is None:
            raise ToolError("INVALID_ARGUMENT", "Provide at least one transform field.")
        obj = require_object(params.object)
        location = vec3(params.location, "location")
        rotation = vec3(params.rotation, "rotation")
        scale = vec3(params.scale, "scale")
        if params.space == "LOCAL":
            if location is not None:
                obj.location = location
            if rotation is not None:
                obj.rotation_euler = rotation
            if scale is not None:
                obj.scale = scale
        elif params.space == "WORLD":
            from mathutils import Euler, Matrix, Vector  # pylint: disable=import-error,no-name-in-module

            old_location, old_rotation, old_scale = obj.matrix_world.decompose()
            obj.matrix_world = Matrix.LocRotScale(
                Vector(location) if location is not None else old_location,
                Euler(rotation) if rotation is not None else old_rotation,
                Vector(scale) if scale is not None else old_scale,
            )
        else:
            raise ToolError("INVALID_ARGUMENT", "space must be WORLD or LOCAL.")
        changed = [name for name, value in (("location", location), ("rotation", rotation), ("scale", scale)) if value is not None]
        return success("object_transform", obj, changed, before)
    except ToolError as ex:
        return failure("object_transform", ex)


def delete(params: DeleteParams) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        obj = require_object(params.object)
        target = object_ref(obj)
        bpy.data.objects.remove(obj, do_unlink=True)
        return success("object_delete", target, ["deleted"], before)
    except ToolError as ex:
        return failure("object_delete", ex)


def duplicate(params: DuplicateParams) -> Result:
    before = scene_snapshot()
    try:
        obj = require_object(params.object)
        copy = obj.copy()
        if not params.linked_data and obj.data is not None:
            copy.data = obj.data.copy()
        for collection in obj.users_collection:
            collection.objects.link(copy)
        if not copy.users_collection:
            raise ToolError("DUPLICATE_FAILED", "The source object is not linked to a collection.")
        if params.new_name is not None:
            if not params.new_name.strip():
                raise ToolError("INVALID_ARGUMENT", "new_name cannot be empty.")
            copy.name = params.new_name
        set_active(copy)
        return success("object_duplicate", copy, ["duplicated"], before)
    except ToolError as ex:
        return failure("object_duplicate", ex)


def set_properties(params: PropertiesParams) -> Result:
    before = scene_snapshot()
    try:
        obj = require_object(params.object)
        changed: list[str] = []
        if params.name is not None:
            if not params.name.strip():
                raise ToolError("INVALID_ARGUMENT", "name cannot be empty.")
            obj.name = params.name
            changed.append("name")
        if params.visible is not None:
            obj.hide_viewport = not params.visible
            changed.append("visible")
        if params.render_visible is not None:
            obj.hide_render = not params.render_visible
            changed.append("render_visible")
        if params.display_type is not None:
            obj.display_type = params.display_type
            changed.append("display_type")
        if not changed:
            raise ToolError("INVALID_ARGUMENT", "Provide at least one property to update.")
        return success("object_set_properties", obj, changed, before)
    except ToolError as ex:
        return failure("object_set_properties", ex)


def parent(params: ParentParams) -> Result:
    before = scene_snapshot()
    try:
        obj = require_object(params.object)
        parent_obj = require_object(params.parent) if params.parent is not None else None
        if parent_obj is obj:
            raise ToolError("INVALID_ARGUMENT", "An object cannot be its own parent.")
        matrix_world = obj.matrix_world.copy()
        obj.parent = parent_obj
        if params.keep_world_transform:
            obj.matrix_world = matrix_world
        return success("object_parent", obj, ["parent"], before)
    except ToolError as ex:
        return failure("object_parent", ex)


def main(params: object) -> Result:
    if isinstance(params, CreateParams):
        return create(params)
    if isinstance(params, TransformParams):
        return transform(params)
    if isinstance(params, DeleteParams):
        return delete(params)
    if isinstance(params, DuplicateParams):
        return duplicate(params)
    if isinstance(params, PropertiesParams):
        return set_properties(params)
    if isinstance(params, ParentParams):
        return parent(params)
    return failure("object_operation", ToolError("INVALID_ARGUMENT", "Unsupported object operation parameters."))
