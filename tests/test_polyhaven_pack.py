# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the Poly Haven capability pack and its profile wiring."""

from __future__ import annotations

import asyncio
import unittest

from blmcp.agent_ops._bridge import load_toolcode
from blmcp.profiles import pack_modules
from blmcp.providers.polyhaven import client, tools


class TestProfileWiring(unittest.TestCase):
    def test_packs_load_only_for_asset_and_full(self) -> None:
        self.assertEqual(pack_modules("official"), ())
        self.assertEqual(pack_modules("core"), ())
        self.assertEqual(pack_modules("creator"), ())
        self.assertEqual(pack_modules("asset"), ("local_import", "polyhaven"))
        self.assertEqual(pack_modules("full"), ("local_import", "polyhaven"))

    def test_asset_profile_exposes_pack_tools(self) -> None:
        from blmcp import create_server

        async def tool_names(profile: str) -> set[str]:
            return {tool.name for tool in await create_server(profile).list_tools()}

        asset_tools = asyncio.run(tool_names("asset"))
        core_tools = asyncio.run(tool_names("core"))
        self.assertIn("polyhaven_search", asset_tools)
        self.assertIn("polyhaven_import", asset_tools)
        self.assertNotIn("polyhaven_search", core_tools)
        self.assertNotIn("polyhaven_import", core_tools)


class TestClient(unittest.TestCase):
    def test_search_filters_by_query_terms_and_limits(self) -> None:
        fake_assets = {
            "aerial_grass": {"name": "Aerial Grass Field", "categories": ["outdoor"], "tags": ["grass"]},
            "brown_mud": {"name": "Brown Mud", "categories": ["outdoor"], "tags": []},
            "brick_wall": {"name": "Old Bricks", "categories": ["indoor", "wall"], "tags": []},
        }
        original = client._fetch_json
        client._fetch_json = lambda url: fake_assets  # type: ignore[assignment]
        try:
            rows = client.search_assets("texture", "grass", 5)
            limited = client.search_assets("texture", "outdoor", 1)
        finally:
            client._fetch_json = original
        self.assertEqual([row["id"] for row in rows], ["aerial_grass"])
        self.assertEqual(len(limited), 1)

    def test_search_rejects_unknown_type(self) -> None:
        with self.assertRaises(client.AssetFetchError):
            client.search_assets("sound", "", 5)

    def test_hdri_resolution_must_exist(self) -> None:
        files = {"hdri": {"1k": {"hdr": {"url": "http://example.test/a_1k.hdr"}}}}
        with self.assertRaises(client.AssetFetchError):
            client.resolve_import_files(files, "hdri", "2k")
        self.assertEqual(
            client.resolve_import_files(files, "hdri", "1k"),
            [("hdri", "http://example.test/a_1k.hdr")],
        )

    def test_texture_roles_map_to_polyhaven_map_keys(self) -> None:
        files = {
            "Diffuse": {"2k": {"jpg": {"url": "http://example.test/d.jpg"}, "png": {"url": "http://example.test/d.png"}}},
            "nor_gl": {"2k": {"png": {"url": "http://example.test/n.png"}}},
            "Rough": {"1k": {"jpg": {"url": "http://example.test/r.jpg"}}},
        }
        resolved = client.resolve_import_files(files, "texture", "2k")
        self.assertEqual(
            resolved,
            [("base_color", "http://example.test/d.jpg"), ("normal", "http://example.test/n.png")],
        )

    def test_texture_requires_any_map_at_resolution(self) -> None:
        files = {"Diffuse": {"1k": {"jpg": {"url": "http://example.test/d.jpg"}}}}
        with self.assertRaises(client.AssetFetchError):
            client.resolve_import_files(files, "texture", "4k")

    def test_model_uses_bundled_blend_file(self) -> None:
        files = {"blend": {"2k": {"blend": {"url": "http://example.test/m.blend"}}},
                 "gltf": {"2k": {"gltf": {"url": "http://example.test/m.gltf"}}}}
        self.assertEqual(
            client.resolve_import_files(files, "model", "2k"),
            [("model", "http://example.test/m.blend")],
        )


class TestImportPreparation(unittest.TestCase):
    def test_toolcode_expands_and_compiles(self) -> None:
        code = load_toolcode(tools.__file__)
        compile(code, "polyhaven_toolcode", "exec")

    def test_prepare_import_downloads_expected_roles(self) -> None:
        original_fetch_info = client.fetch_asset_info
        original_fetch_files = client.fetch_asset_files
        original_download = client.download_file
        client.fetch_asset_info = lambda asset_id: {"name": "Test HDRI", "type": "hdri"}  # type: ignore[assignment]
        client.fetch_asset_files = lambda asset_id: {"hdri": {"2k": {"hdr": {"url": "http://example.test/t.hdr"}}}}  # type: ignore[assignment]
        client.download_file = lambda url, asset_id: "/cache/test.hdr"  # type: ignore[assignment]
        try:
            plan = tools._prepare_import("test_hdri", "2k")
        finally:
            client.fetch_asset_info = original_fetch_info  # type: ignore[assignment]
            client.fetch_asset_files = original_fetch_files  # type: ignore[assignment]
            client.download_file = original_download  # type: ignore[assignment]
        self.assertEqual(plan.kind, "hdri")
        self.assertEqual(plan.name, "Test HDRI")
        self.assertEqual(plan.files, [("hdri", "/cache/test.hdr")])

    def test_import_params_per_kind(self) -> None:
        from blmcp.providers.polyhaven.tools_toolcode import ImportHDRIParams, ImportModelParams, ImportTextureParams

        hdri = tools._import_params(tools.ImportPlan("hdri", "N", [("hdri", "/a.hdr")]), None)
        self.assertIsInstance(hdri, ImportHDRIParams)
        texture = tools._import_params(
            tools.ImportPlan("texture", "N", [("base_color", "/d.jpg"), ("roughness", "/r.jpg")]), "Cube",
        )
        self.assertIsInstance(texture, ImportTextureParams)
        assert isinstance(texture, ImportTextureParams)
        self.assertEqual(texture.target_object, "Cube")
        model = tools._import_params(tools.ImportPlan("model", "N", [("model", "/m.glb")]), None)
        self.assertIsInstance(model, ImportModelParams)


if __name__ == "__main__":
    unittest.main()
