# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-side implementation of compact scene observation."""


from __future__ import annotations

__all__ = ('RefreshParams', 'RefreshResult', 'SceneSummaryParams', 'SceneSummaryResult', 'SearchParams', 'SearchResult', 'main', 'refresh', 'scene_summary', 'search')

from collections import Counter
from typing import NamedTuple


class SceneSummaryParams(NamedTuple):
    pass


class SearchParams(NamedTuple):
    name_pattern: str | None
    object_type: str | None
    collection: str | None
    material: str | None
    visible: bool | None
    limit: int


class RefreshParams(NamedTuple):
    pass


# @include_begin: _toolcode_runtime.py
# @include_end


class SceneSummaryResult(NamedTuple):
    ok: bool
    object_count: int | None = None
    object_types: dict[str, int] | None = None
    collection_count: int | None = None
    active: dict[str, str] | None = None
    selected: list[dict[str, str]] | None = None
    camera: dict[str, str] | None = None
    mode: str | None = None
    render_engine: str | None = None
    error: dict[str, object] | None = None


class SearchResult(NamedTuple):
    ok: bool
    objects: list[dict[str, object]] | None = None
    total_matches: int | None = None
    truncated: bool | None = None
    error: dict[str, object] | None = None


class RefreshResult(NamedTuple):
    ok: bool
    object_count: int | None = None
    names: list[str] | None = None
    active: dict[str, str] | None = None
    selected: list[dict[str, str]] | None = None
    error: dict[str, object] | None = None


def scene_summary() -> SceneSummaryResult:
    import bpy  # pylint: disable=import-error,no-name-in-module

    active = bpy.context.view_layer.objects.active
    scene = bpy.context.scene
    return SceneSummaryResult(
        ok=True,
        object_count=len(bpy.data.objects),
        object_types=dict(sorted(Counter(obj.type for obj in bpy.data.objects).items())),
        collection_count=len(bpy.data.collections),
        active=object_ref(active) if active else None,
        selected=sorted((object_ref(obj) for obj in bpy.context.selected_objects), key=lambda ref: ref["id"]),
        camera=object_ref(scene.camera) if scene.camera else None,
        mode=bpy.context.mode,
        render_engine=scene.render.engine,
    )


def search(params: SearchParams) -> SearchResult:
    import fnmatch
    import bpy  # pylint: disable=import-error,no-name-in-module

    if not 1 <= params.limit <= 100:
        return SearchResult(
            ok=False,
            error={"code": "INVALID_ARGUMENT", "message": "limit must be between 1 and 100.", "recoverable": True},
        )
    matches: list[dict[str, object]] = []
    for obj in sorted(bpy.data.objects, key=lambda item: item.name.casefold()):
        if params.name_pattern and not fnmatch.fnmatchcase(obj.name.casefold(), params.name_pattern.casefold()):
            continue
        if params.object_type and obj.type != params.object_type:
            continue
        if params.collection and all(col.name != params.collection for col in obj.users_collection):
            continue
        if params.material:
            material_names = [slot.material.name for slot in obj.material_slots if slot.material]
            if params.material not in material_names:
                continue
        if params.visible is not None and bool(obj.visible_get()) != params.visible:
            continue
        matches.append({
            **object_ref(obj),
            "type": obj.type,
            "location": [round(float(value), 4) for value in obj.matrix_world.translation],
            "dimensions": [round(float(value), 4) for value in obj.dimensions],
        })
    return SearchResult(
        ok=True,
        objects=matches[:params.limit],
        total_matches=len(matches),
        truncated=len(matches) > params.limit,
    )


def refresh(params: RefreshParams) -> RefreshResult:
    import bpy  # pylint: disable=import-error,no-name-in-module

    active = bpy.context.view_layer.objects.active
    return RefreshResult(
        ok=True,
        object_count=len(bpy.data.objects),
        names=sorted(obj.name for obj in bpy.data.objects),
        active=object_ref(active) if active else None,
        selected=sorted((object_ref(obj) for obj in bpy.context.selected_objects), key=lambda ref: ref["id"]),
    )


def main(params: object) -> SceneSummaryResult | SearchResult | RefreshResult:
    if isinstance(params, SceneSummaryParams):
        return scene_summary()
    if isinstance(params, SearchParams):
        return search(params)
    if isinstance(params, RefreshParams):
        return refresh(params)
    return SearchResult(ok=False, error={"code": "INVALID_ARGUMENT", "message": "Unsupported observation parameters.", "recoverable": True})
