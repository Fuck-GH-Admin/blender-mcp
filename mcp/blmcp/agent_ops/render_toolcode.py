# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-side implementation of render operations."""


from __future__ import annotations

__all__ = ('ConfigureParams', 'PreviewParams', 'configure', 'main', 'preview')

from typing import NamedTuple


class ConfigureParams(NamedTuple):
    engine: str | None
    resolution_x: int | None
    resolution_y: int | None
    samples: int | None
    transparent: bool | None


class PreviewParams(NamedTuple):
    output_path: str
    max_dimension: int
    samples: int


# @include_begin: _toolcode_runtime.py
# @include_end


def _positive_int(value: int | None, field: str, maximum: int) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
        raise ToolError("INVALID_ARGUMENT", "{:s} must be an integer between 1 and {:d}.".format(field, maximum))
    return value


def configure(params: ConfigureParams) -> Result:
    before = scene_snapshot()
    try:
        import bpy  # pylint: disable=import-error,no-name-in-module

        if all(value is None for value in params):
            raise ToolError("INVALID_ARGUMENT", "Provide at least one render setting.")
        scene = bpy.context.scene
        render = scene.render
        changed: list[str] = []
        if params.engine is not None:
            if params.engine not in {"BLENDER_EEVEE", "CYCLES"}:
                raise ToolError("INVALID_ARGUMENT", "engine must be BLENDER_EEVEE or CYCLES.")
            render.engine = params.engine
            changed.append("engine")
        resolution_x = _positive_int(params.resolution_x, "resolution_x", 16384)
        if resolution_x is not None:
            render.resolution_x = resolution_x
            changed.append("resolution_x")
        resolution_y = _positive_int(params.resolution_y, "resolution_y", 16384)
        if resolution_y is not None:
            render.resolution_y = resolution_y
            changed.append("resolution_y")
        samples = _positive_int(params.samples, "samples", 4096)
        if samples is not None:
            if render.engine == "CYCLES":
                scene.cycles.samples = samples
            else:
                scene.eevee.taa_render_samples = samples
            changed.append("samples")
        if params.transparent is not None:
            render.film_transparent = params.transparent
            changed.append("transparent")
        return success("render_configure", None, changed, before)
    except ToolError as ex:
        return failure("render_configure", ex)


def preview(params: PreviewParams) -> Result:
    before = scene_snapshot()
    try:
        import os
        import bpy  # pylint: disable=import-error,no-name-in-module

        if not params.output_path:
            raise ToolError("INVALID_ARGUMENT", "output_path cannot be empty.")
        max_dimension = _positive_int(params.max_dimension, "max_dimension", 2048)
        samples = _positive_int(params.samples, "samples", 256)
        assert max_dimension is not None and samples is not None
        scene = bpy.context.scene
        render = scene.render
        largest = max(render.resolution_x, render.resolution_y)
        scale = min(1.0, max_dimension / largest)
        old = (render.filepath, render.resolution_x, render.resolution_y, render.resolution_percentage)
        render.filepath = os.path.abspath(params.output_path)
        render.resolution_x = max(1, int(render.resolution_x * scale))
        render.resolution_y = max(1, int(render.resolution_y * scale))
        render.resolution_percentage = 100
        old_samples = scene.cycles.samples if render.engine == "CYCLES" else scene.eevee.taa_render_samples
        if render.engine == "CYCLES":
            scene.cycles.samples = samples
        else:
            scene.eevee.taa_render_samples = samples
        try:
            bpy.ops.render.render(write_still=True)
        except RuntimeError as ex:
            raise ToolError("RENDER_FAILED", str(ex)) from ex
        finally:
            render.filepath, render.resolution_x, render.resolution_y, render.resolution_percentage = old
            if render.engine == "CYCLES":
                scene.cycles.samples = old_samples
            else:
                scene.eevee.taa_render_samples = old_samples
        return success("render_preview", None, ["rendered"], before)
    except ToolError as ex:
        return failure("render_preview", ex)


def main(params: object) -> Result:
    if isinstance(params, ConfigureParams):
        return configure(params)
    if isinstance(params, PreviewParams):
        return preview(params)
    return failure("render_operation", ToolError("INVALID_ARGUMENT", "Unsupported render operation parameters."))
