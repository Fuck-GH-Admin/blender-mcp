# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-side implementation of Poly Haven asset imports."""


from __future__ import annotations

__all__ = ('ImportHDRIParams', 'ImportModelParams', 'ImportTextureParams', 'main')

from typing import NamedTuple


class ImportHDRIParams(NamedTuple):
    name: str
    filepath: str


class ImportTextureParams(NamedTuple):
    name: str
    filepaths: list[tuple[str, str]]
    target_object: str | None


class ImportModelParams(NamedTuple):
    name: str
    filepath: str


# @include_begin: ../../agent_ops/_toolcode_runtime.py
# @include_end


def _require_file(filepath: str) -> None:
    import os

    if not os.path.isfile(filepath):
        raise ToolError("ASSET_FILE_MISSING", "Downloaded asset file is missing: {!r}.".format(filepath))


def _import_hdri(params: ImportHDRIParams) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        _require_file(params.filepath)
        scene = bpy.context.scene
        world = scene.world
        if world is None:
            world = bpy.data.worlds.new(params.name)
            scene.world = world
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        background = next((node for node in nodes if node.type == "BACKGROUND"), None)
        if background is None:
            background = nodes.new("ShaderNodeBackground")
            output = next((node for node in nodes if node.type == "OUTPUT_WORLD"), None)
            if output is None:
                output = nodes.new("ShaderNodeOutputWorld")
            links.new(background.outputs["Background"], output.inputs["Surface"])
        environment = nodes.new("ShaderNodeTexEnvironment")
        environment.image = bpy.data.images.load(params.filepath, check_existing=True)
        links.new(environment.outputs["Color"], background.inputs["Color"])
        return success("polyhaven_import", None, ["world_environment"], before)
    except ToolError as ex:
        return failure("polyhaven_import", ex)


def _import_texture(params: ImportTextureParams) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        for _role, filepath in params.filepaths:
            _require_file(filepath)
        material = bpy.data.materials.get(params.name) or bpy.data.materials.new(params.name)
        material.use_nodes = True
        tree = material.node_tree
        principled = next((node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
        if principled is None:
            raise ToolError("MATERIAL_SCHEMA_UNSUPPORTED", "The material has no Principled BSDF node.")
        offset = 0.0
        changed = ["material"]
        for role, filepath in params.filepaths:
            image = bpy.data.images.load(filepath, check_existing=True)
            if role != "base_color":
                image.colorspace_settings.name = "Non-Color"
            texture = tree.nodes.new("ShaderNodeTexImage")
            texture.location = (-400.0, -200.0 * offset)
            texture.image = image
            offset += 1.0
            if role == "base_color":
                tree.links.new(texture.outputs["Color"], principled.inputs["Base Color"])
            elif role == "roughness":
                tree.links.new(texture.outputs["Color"], principled.inputs["Roughness"])
            elif role == "normal":
                normal_map = tree.nodes.new("ShaderNodeNormalMap")
                normal_map.location = (-200.0, -400.0)
                tree.links.new(texture.outputs["Color"], normal_map.inputs["Color"])
                tree.links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
        target = None
        if params.target_object is not None:
            obj = require_object(params.target_object)
            if not obj.material_slots:
                raise ToolError(
                    "INVALID_ARGUMENT",
                    "Object {!r} has no material slots.".format(obj.name),
                    "material_assign",
                )
            obj.material_slots[0].material = material
            changed.append("assigned")
            target = obj
        return success("polyhaven_import", target, changed, before)
    except ToolError as ex:
        return failure("polyhaven_import", ex)


def _import_model(params: ImportModelParams) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        _require_file(params.filepath)
        require_object_mode()
        with bpy.data.libraries.load(params.filepath, link=False) as (data_from, data_to):
            data_to.objects = list(data_from.objects)
        appended = [obj for obj in data_to.objects if obj is not None]
        if not appended:
            raise ToolError("IMPORT_FAILED", "The asset blend file contains no objects.")
        collection = bpy.context.scene.collection
        for obj in appended:
            if obj.name not in collection.objects:
                collection.objects.link(obj)
        set_active(appended[0])
        return success("polyhaven_import", appended[0], ["imported"], before)
    except ToolError as ex:
        return failure("polyhaven_import", ex)


def main(params: object) -> Result:
    if isinstance(params, ImportHDRIParams):
        return _import_hdri(params)
    if isinstance(params, ImportTextureParams):
        return _import_texture(params)
    if isinstance(params, ImportModelParams):
        return _import_model(params)
    return failure("polyhaven_import", ToolError("INVALID_ARGUMENT", "Unsupported import parameters."))
