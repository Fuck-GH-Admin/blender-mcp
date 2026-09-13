# SPDX-License-Identifier: GPL-3.0-or-later
"""Startup-selected tool profiles; no client-specific dynamic tool loading."""

from __future__ import annotations

from collections.abc import Iterable

__all__ = ("PROFILE_NAMES", "agent_modules", "official_modules", "pack_modules")

PROFILE_NAMES = ("official", "core", "creator", "asset", "full")

_PACK_MODULES = ("local_import", "polyhaven")

_CORE_OFFICIAL = frozenset({
    "execute_blender_code",
    "get_object_detail_summary",
    "get_objects_summary",
    "get_python_api_docs",
    "get_screenshot_of_window_as_image",
    "get_screenshot_of_window_as_json",
    "search_api_docs",
    "search_manual_docs",
})
_CREATOR_OFFICIAL = _CORE_OFFICIAL | frozenset({
    "get_screenshot_of_area_as_image",
    "jump_to_tab_by_name",
    "jump_to_tab_by_space_type",
    "jump_to_view3d_object_by_name",
    "jump_to_view3d_object_data_by_name",
    "render_thumbnail_to_path",
    "render_viewport_to_path",
})
_AGENT_MODULES = (
    "observation", "object", "object_manage", "modifier", "material", "camera", "light",
    "render", "batch", "escape",
)


def official_modules(profile: str, all_modules: Iterable[str]) -> tuple[str, ...]:
    """Filter upstream modules for a fixed profile at server start."""
    modules = tuple(sorted(all_modules))
    if profile in {"official", "full"}:
        return modules
    allowed = _CREATOR_OFFICIAL if profile == "creator" else _CORE_OFFICIAL
    return tuple(module for module in modules if module in allowed)


def agent_modules(profile: str) -> tuple[str, ...]:
    """Return new operation modules for every agent profile."""
    if profile == "official":
        return ()
    return _AGENT_MODULES


def pack_modules(profile: str) -> tuple[str, ...]:
    """Return capability-pack provider modules for the profiles that enable them."""
    if profile in {"asset", "full"}:
        return _PACK_MODULES
    return ()
