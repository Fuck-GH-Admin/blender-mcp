# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-side implementation of local file imports."""

from __future__ import annotations

__all__ = ('ImportFileParams', 'main')

from typing import NamedTuple


class ImportFileParams(NamedTuple):
    path: str
    format: str


# @include_begin: ../../agent_ops/_toolcode_runtime.py
# @include_end


def _require_file(filepath: str) -> None:
    import os

    if not os.path.isfile(filepath):
        raise ToolError("INVALID_PATH", "File does not exist: {!r}.".format(filepath))


def _run_operator(operation: object, filepath: str) -> None:
    try:
        operation(filepath=filepath)
    except RuntimeError as ex:
        raise ToolError("IMPORT_FAILED", str(ex)) from ex


def _ensure_svg_addon() -> None:
    import addon_utils  # pylint: disable=import-error,no-name-in-module

    loaded, enabled = addon_utils.check("io_curve_svg")
    if not enabled:
        try:
            addon_utils.enable("io_curve_svg", default_set=True, persistent=False)
        except Exception as ex:  # pylint: disable=broad-exception-caught
            raise ToolError("ADDON_ENABLE_FAILED", "Cannot enable io_curve_svg: {:s}".format(ex)) from ex


def _import_file(params: ImportFileParams) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        _require_file(params.path)
        if params.format == "svg":
            _ensure_svg_addon()
            _run_operator(bpy.ops.import_curve.svg, params.path)
        elif params.format in {"glb", "gltf"}:
            _run_operator(bpy.ops.import_scene.gltf, params.path)
        elif params.format == "obj":
            _run_operator(bpy.ops.wm.obj_import, params.path)
        elif params.format == "fbx":
            _run_operator(bpy.ops.import_scene.fbx, params.path)
        elif params.format == "image":
            try:
                bpy.data.images.load(params.path, check_existing=True)
            except RuntimeError as ex:
                raise ToolError("IMPORT_FAILED", str(ex)) from ex
            return success("import_file", None, ["image"], before)
        else:
            raise ToolError("INVALID_ARGUMENT", "Unsupported format {!r}.".format(params.format))
        return success("import_file", bpy.context.view_layer.objects.active, ["imported"], before)
    except ToolError as ex:
        return failure("import_file", ex)


def main(params: object) -> Result:
    if isinstance(params, ImportFileParams):
        return _import_file(params)
    return failure("import_file", ToolError("INVALID_ARGUMENT", "Unsupported import parameters."))
