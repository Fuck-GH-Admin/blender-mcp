# SPDX-License-Identifier: GPL-3.0-or-later
"""Server-side client for the public Poly Haven API.

No Blender code lives here.  Downloads are cached under a local directory so
imported images keep a valid on-disk path for the whole Blender session.
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.request

__all__ = (
    "AssetFetchError",
    "cache_root",
    "download_file",
    "fetch_asset_files",
    "fetch_asset_info",
    "resolve_import_files",
    "search_assets",
)

_API_ROOT = "https://api.polyhaven.com"
_API_TIMEOUT = 30.0
_DOWNLOAD_TIMEOUT = 120.0
_USER_AGENT = "super-blender-mcp-next"
_TEXTURE_FORMAT_PREFERENCE = ("jpg", "png")
_MAP_ROLES = (("base_color", "Diffuse"), ("roughness", "Rough"), ("normal", "nor_gl"))
# The API reports asset type as a numeric enum; strings are accepted for robustness.
_TYPE_NAMES = {0: "hdri", 1: "texture", 2: "model"}


class AssetFetchError(RuntimeError):
    """Raised when Poly Haven is unreachable or returns unexpected data."""


def cache_root() -> str:
    """Return the local download cache directory (env-overridable)."""
    override = os.environ.get("BLMCP_POLYHAVEN_CACHE")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".cache", "super-blender-mcp-next", "polyhaven")


def _fetch_json(url: str) -> object:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=_API_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as ex:
        raise AssetFetchError("Poly Haven request failed ({:s}).".format(ex.__class__.__name__)) from ex


def _file_entry_url(entry: object, formats: tuple[str, ...] = ()) -> str:
    """Pick the preferred format from a ``files`` leaf: ``{format: {url: ...}}``."""
    if not isinstance(entry, dict):
        raise AssetFetchError("Unexpected Poly Haven file listing.")
    if not formats:
        formats = tuple(entry)
    for fmt in formats:
        candidate = entry.get(fmt)
        if isinstance(candidate, dict) and isinstance(candidate.get("url"), str):
            return str(candidate["url"])
    raise AssetFetchError("Poly Haven asset has no usable file format.")


def _resolution_entry(section: object, resolution: str, kind_label: str) -> dict[str, object]:
    if not isinstance(section, dict):
        raise AssetFetchError("Unexpected Poly Haven file listing.")
    available = sorted(section)
    entry = section.get(resolution)
    if not isinstance(entry, dict):
        raise AssetFetchError(
            "Resolution {!r} is not available for this {:s} (available: {:s}).".format(
                resolution, kind_label, ", ".join(available) or "none"
            )
        )
    return entry


def search_assets(asset_type: str, query: str, limit: int) -> list[dict[str, object]]:
    """Search one Poly Haven asset type, returning compact ``{id, name, categories}`` rows."""
    type_param = {"hdri": "hdris", "texture": "textures", "model": "models"}.get(asset_type)
    if type_param is None:
        raise AssetFetchError("Unsupported asset type {!r}.".format(asset_type))
    payload = _fetch_json("{:s}/assets?type={:s}".format(_API_ROOT, type_param))
    if not isinstance(payload, dict):
        raise AssetFetchError("Unexpected Poly Haven search response.")
    terms = query.strip().lower().split()
    matches: list[dict[str, object]] = []
    for asset_id, entry in payload.items():
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or asset_id)
        categories = [str(category) for category in (entry.get("categories") or []) if isinstance(category, str)]
        tags = [str(tag) for tag in (entry.get("tags") or []) if isinstance(tag, str)]
        haystack = " ".join((asset_id, name, *categories, *tags)).lower()
        if terms and not all(term in haystack for term in terms):
            continue
        matches.append({"id": asset_id, "name": name, "categories": categories[:3]})
        if len(matches) >= limit:
            break
    return matches


def fetch_asset_info(asset_id: str) -> dict[str, object]:
    """Return ``{name, type}`` for one asset id."""
    payload = _fetch_json("{:s}/info/{:s}".format(_API_ROOT, asset_id))
    if not isinstance(payload, dict):
        raise AssetFetchError("Poly Haven has no asset with id {!r}.".format(asset_id))
    raw_type = payload.get("type")
    kind = _TYPE_NAMES.get(raw_type) if isinstance(raw_type, int) else (str(raw_type) if isinstance(raw_type, str) else None)
    if kind is None:
        raise AssetFetchError("Poly Haven asset {!r} has an unknown type.".format(asset_id))
    return {"name": str(payload.get("name") or asset_id), "type": kind}


def fetch_asset_files(asset_id: str) -> dict[str, object]:
    """Return the raw per-asset download listing."""
    payload = _fetch_json("{:s}/files/{:s}".format(_API_ROOT, asset_id))
    if not isinstance(payload, dict):
        raise AssetFetchError("Unexpected Poly Haven file listing for {!r}.".format(asset_id))
    return payload


def resolve_import_files(files: dict[str, object], kind: str, resolution: str) -> list[tuple[str, str]]:
    """Resolve ``(role, url)`` download entries for one asset import.

    Textures only contribute the maps that exist at the requested resolution;
    HDRIs use the ``hdr`` format and models the single-file ``glb`` format.
    """
    if kind == "hdri":
        section = files.get("hdri")
        entry = _resolution_entry(section, resolution, "HDRI")
        return [("hdri", _file_entry_url(entry, ("hdr",)))]
    if kind == "model":
        # Poly Haven models do not ship a single-file GLB: their ``gltf`` entry
        # is a small JSON that references companion files the API does not
        # expose.  The bundled ``blend`` file is self-contained, so use that.
        section = files.get("blend")
        entry = _resolution_entry(section, resolution, "model")
        return [("model", _file_entry_url(entry, ("blend",)))]
    if kind == "texture":
        resolved: list[tuple[str, str]] = []
        no_map_at_resolution = True
        for role, map_key in _MAP_ROLES:
            section = files.get(map_key)
            if not isinstance(section, dict) or resolution not in section:
                continue
            no_map_at_resolution = False
            resolved.append((role, _file_entry_url(section[resolution], _TEXTURE_FORMAT_PREFERENCE)))
        if no_map_at_resolution:
            raise AssetFetchError(
                "Resolution {!r} is not available for this texture (available: {:s}).".format(
                    resolution, ", ".join(sorted({key for section in files.values() if isinstance(section, dict) for key in section})) or "none"
                )
            )
        return resolved
    raise AssetFetchError("Unsupported Poly Haven asset type {!r}.".format(kind))


def download_file(url: str, asset_id: str) -> str:
    """Download *url* into the cache directory of *asset_id* and return its path."""
    directory = os.path.join(cache_root(), asset_id)
    os.makedirs(directory, exist_ok=True)
    filename = url.rsplit("/", 1)[-1].split("?", 1)[0] or "asset.bin"
    path = os.path.join(directory, filename)
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        return path
    try:
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT) as response, open(path, "wb") as fh:
            shutil.copyfileobj(response, fh)
    except OSError as ex:
        try:
            os.remove(path)
        except OSError:
            pass
        raise AssetFetchError("Poly Haven download failed ({:s}).".format(ex.__class__.__name__)) from ex
    return path
