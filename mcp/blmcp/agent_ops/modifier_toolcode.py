# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-side implementation of generic modifier management."""


from __future__ import annotations

__all__ = ('Params', 'main')

from typing import NamedTuple


class Params(NamedTuple):
    object: str
    action: str
    type: str | None
    modifier: str | None
    properties: dict[str, object] | None


# @include_begin: _toolcode_runtime.py
# @include_end


def _modifier(obj: object, name: str | None) -> object:
    if not name:
        raise ToolError("INVALID_ARGUMENT", "modifier is required for this action.")
    modifier = obj.modifiers.get(name)
    if modifier is None:
        raise ToolError("MODIFIER_NOT_FOUND", "Modifier {!r} does not exist on {!r}.".format(name, obj.name), "get_object_detail_summary")
    return modifier


def _set_properties(modifier: object, properties: dict[str, object] | None) -> list[str]:
    if not properties:
        return []
    blocked = {"name", "rna_type", "type"}
    changed: list[str] = []
    for key, value in properties.items():
        if key in blocked or key.startswith("_"):
            raise ToolError("INVALID_MODIFIER_PROPERTY", "Property {!r} cannot be changed.".format(key))
        rna_property = modifier.bl_rna.properties.get(key)
        if rna_property is None:
            raise ToolError("INVALID_MODIFIER_PROPERTY", "Modifier property {!r} does not exist.".format(key))
        if rna_property.is_readonly or rna_property.type in {"COLLECTION", "POINTER"}:
            raise ToolError("INVALID_MODIFIER_PROPERTY", "Modifier property {!r} is not supported by this tool.".format(key))
        try:
            setattr(modifier, key, value)
        except (TypeError, ValueError) as ex:
            raise ToolError("INVALID_MODIFIER_PROPERTY", "Could not set {!r}: {:s}".format(key, str(ex))) from ex
        changed.append(key)
    return changed


def main(params: Params) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        obj = require_object(params.object)
        if params.action == "add":
            if not params.type:
                raise ToolError("INVALID_ARGUMENT", "type is required when action is add.")
            try:
                modifier = obj.modifiers.new(params.modifier or params.type.title(), params.type)
            except (RuntimeError, TypeError) as ex:
                raise ToolError("INVALID_MODIFIER_TYPE", "Could not add modifier {!r}: {:s}".format(params.type, str(ex))) from ex
            changed = ["modifier"] + _set_properties(modifier, params.properties)
        elif params.action == "update":
            modifier = _modifier(obj, params.modifier)
            changed = _set_properties(modifier, params.properties)
            if not changed:
                raise ToolError("INVALID_ARGUMENT", "properties is required when action is update.")
        elif params.action == "remove":
            modifier = _modifier(obj, params.modifier)
            obj.modifiers.remove(modifier)
            changed = ["modifier"]
        elif params.action == "apply":
            require_object_mode()
            modifier = _modifier(obj, params.modifier)
            set_active(obj)
            try:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            except RuntimeError as ex:
                raise ToolError("MODIFIER_APPLY_FAILED", str(ex), "switch_to_object_mode") from ex
            changed = ["modifier"]
        else:
            raise ToolError("INVALID_ARGUMENT", "action must be add, update, remove, or apply.")
        return success("modifier_manage", obj, changed, before)
    except ToolError as ex:
        return failure("modifier_manage", ex)
