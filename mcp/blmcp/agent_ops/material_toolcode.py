# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-side implementation of Principled material operations."""


from __future__ import annotations

__all__ = ('AssignParams', 'CreateParams', 'assign', 'create_or_update', 'main')

import math
from typing import NamedTuple


class CreateParams(NamedTuple):
    name: str
    base_color: list[float] | None
    metallic: float | None
    roughness: float | None
    alpha: float | None
    emission: list[float] | None
    emission_strength: float | None


class AssignParams(NamedTuple):
    object: str
    material: str
    slot: int


# @include_begin: _toolcode_runtime.py
# @include_end


def _unit_value(value: float | None, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ToolError("INVALID_ARGUMENT", "{:s} must be a finite number from 0 to 1.".format(field))
    return float(value)


def _non_negative(value: float | None, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
        raise ToolError("INVALID_ARGUMENT", "{:s} must be a finite non-negative number.".format(field))
    return float(value)


def _principled(material: object) -> object:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
        if output is None:
            output = nodes.new("ShaderNodeOutputMaterial")
        material.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return bsdf


def _set_socket(node: object, names: tuple[str, ...], value: object) -> bool:
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return True
    return False


def create_or_update(params: CreateParams) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        if not params.name.strip():
            raise ToolError("INVALID_ARGUMENT", "name cannot be empty.")
        material = bpy.data.materials.get(params.name)
        created = material is None
        if material is None:
            material = bpy.data.materials.new(params.name)
        bsdf = _principled(material)
        changed: list[str] = ["created"] if created else []
        base_color = color4(params.base_color, "base_color")
        if base_color is not None:
            _set_socket(bsdf, ("Base Color",), base_color)
            changed.append("base_color")
        metallic = _unit_value(params.metallic, "metallic")
        if metallic is not None:
            _set_socket(bsdf, ("Metallic",), metallic)
            changed.append("metallic")
        roughness = _unit_value(params.roughness, "roughness")
        if roughness is not None:
            _set_socket(bsdf, ("Roughness",), roughness)
            changed.append("roughness")
        alpha = _unit_value(params.alpha, "alpha")
        if alpha is not None:
            _set_socket(bsdf, ("Alpha",), alpha)
            changed.append("alpha")
        emission = color4(params.emission, "emission")
        if emission is not None:
            if not _set_socket(bsdf, ("Emission Color", "Emission"), emission):
                raise ToolError("MATERIAL_UNSUPPORTED", "This Blender version has no Principled emission color input.")
            changed.append("emission")
        emission_strength = _non_negative(params.emission_strength, "emission_strength")
        if emission_strength is not None:
            if not _set_socket(bsdf, ("Emission Strength",), emission_strength):
                raise ToolError("MATERIAL_UNSUPPORTED", "This Blender version has no Principled emission strength input.")
            changed.append("emission_strength")
        return success("material_create_or_update", None, changed or ["material"], before)
    except ToolError as ex:
        return failure("material_create_or_update", ex)


def assign(params: AssignParams) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        obj = require_object(params.object)
        material = bpy.data.materials.get(params.material)
        if material is None:
            raise ToolError("MATERIAL_NOT_FOUND", "Material {!r} does not exist.".format(params.material), "material_create_or_update")
        if not hasattr(obj.data, "materials"):
            raise ToolError("UNSUPPORTED_OBJECT_TYPE", "Object {!r} cannot have material slots.".format(obj.name))
        if not isinstance(params.slot, int) or isinstance(params.slot, bool) or params.slot < 0:
            raise ToolError("INVALID_ARGUMENT", "slot must be a non-negative integer.")
        slots = obj.data.materials
        if params.slot > len(slots):
            raise ToolError("INVALID_ARGUMENT", "slot cannot skip existing material slots.")
        if params.slot == len(slots):
            slots.append(material)
        else:
            slots[params.slot] = material
        return success("material_assign", obj, ["material"], before)
    except ToolError as ex:
        return failure("material_assign", ex)


def main(params: object) -> Result:
    if isinstance(params, CreateParams):
        return create_or_update(params)
    if isinstance(params, AssignParams):
        return assign(params)
    return failure("material_operation", ToolError("INVALID_ARGUMENT", "Unsupported material operation parameters."))
