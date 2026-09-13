#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a 3D model of Noto emoji U+1F416 (pig) with super-blender-mcp-next.

Example script and evidence for docs/agent-experience-review.md: imports the
SVG as curves in Blender, extrudes + joins them into one mesh, colorizes from
the SVG fill materials, then uses the structured tools (camera_frame,
light_create_or_update, modifier_manage, render_configure, render_preview)
to light and render the result.

Configuration (environment variables):

- ``BLENDER_BIN``: Blender executable (default ``blender``).
- ``BLMCP_SERVER_CMD``: server launch command (default: ``uv --project
  <repo>/mcp run super-blender-mcp --profile core``).
- ``NOTO_EMOJI_SVG``: SVG to convert (default: the U+1F416 file in the
  sibling ``test/noto-emoji`` checkout of the workspace).
- ``BLMCP_EXAMPLE_PORT``: addon port (default 9988).
- ``BLMCP_EXAMPLE_OUT``: output directory (default: this script's directory).
"""

__all__ = ()

import glob
import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BLENDER = os.environ.get("BLENDER_BIN", "blender")
PORT = int(os.environ.get("BLMCP_EXAMPLE_PORT", "9988"))
OUT_DIR = Path(os.environ.get("BLMCP_EXAMPLE_OUT", Path(__file__).resolve().parent))
DEFAULT_SVG = REPO.parents[0] / "test" / "noto-emoji" / "svg" / "emoji_u1f416.svg"
SVG = Path(os.environ.get("NOTO_EMOJI_SVG", DEFAULT_SVG))

sys.path.insert(0, str(REPO))
from tests.mcp_client import MCPClient  # noqa: E402


def call(client, name, arguments=None):
    response = client.call_tool(name, arguments)
    assert not response.get("isError"), (name, response)
    data = json.loads(response["content"][0]["text"])
    if isinstance(data, dict) and data.get("status") == "ok" and "result" in data:
        data = data["result"]
    return data


def code_result(data):
    assert data.get("ok") is True, data
    return data.get("result", {})


tmp = tempfile.mkdtemp(prefix="blmcp-emoji-")
env = dict(os.environ)
env["HOME"] = tmp
env["ASAN_OPTIONS"] = "leak_check_at_exit=0"


def run_blender(args):
    proc = subprocess.run(args, capture_output=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError("blender failed: {}\n{}".format(args, proc.stderr.decode(errors="replace")[-1500:]))


run_blender([BLENDER, "--command", "extension", "build",
             "--source-dir=" + str(REPO / "addon" / "blender_mcp_addon"), "--output-dir=" + tmp])
zips = glob.glob(os.path.join(tmp, "mcp-*.zip"))
run_blender([BLENDER, "--online-mode", "--background", "--factory-startup", "--command",
             "extension", "install-file", zips[0], "--repo", "user_default", "--enable"])

blender_proc = subprocess.Popen(
    [BLENDER, "--online-mode", "--background", "--command", "blender_mcp", "--port", str(PORT)],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)


def wait_port(port, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(("localhost", port))
                return True
        except OSError:
            time.sleep(0.3)
    return False


try:
    assert wait_port(PORT, 60), "addon port unreachable"

    senv = dict(os.environ)
    senv["BLENDER_MCP_PORT"] = str(PORT)
    senv["BLMCP_METRICS_PATH"] = str(OUT_DIR / "metrics.jsonl")
    senv["GLOBAL_TIMEOUT_SCALE"] = "4"
    server_cmd = shlex.split(os.environ.get(
        "BLMCP_SERVER_CMD",
        "uv --project {:s} run super-blender-mcp --profile core".format(REPO / "mcp"),
    ))
    client = MCPClient(server_cmd, env=senv)
    client.initialize()

    # --- Phase A: enable SVG importer, import, report structure ---
    r = code_result(call(client, "execute_blender_code", {"code": """
import bpy
enabled = None
for name in ('io_curve_svg', 'bl_ext.blender_org.io_curve_svg', 'bl_ext.user_default.io_curve_svg'):
    try:
        bpy.ops.preferences.addon_enable(module=name)
    except Exception:
        continue
    if name in bpy.context.preferences.addons:
        enabled = name
        break
result = {'enabled': enabled, 'addons': [k for k in bpy.context.preferences.addons.keys() if 'svg' in k]}
"""}))
    print("svg importer:", r)
    assert r.get("enabled"), "no SVG importer available"

    r = code_result(call(client, "execute_blender_code", {"code": """
import bpy
from mathutils import Vector
bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.import_curve.svg(filepath={!r})
objs = [o for o in bpy.data.objects]
xs, ys = [], []
for o in objs:
    for corner in o.bound_box:
        w = o.matrix_world @ Vector(corner)
        xs.append(w.x)
        ys.append(w.y)
mats = {{m.name: [round(c, 3) for c in m.diffuse_color] for m in bpy.data.materials}}
result = {{
    'objects': len(objs),
    'types': sorted({{o.type for o in objs}}),
    'names': sorted(o.name for o in objs)[:30],
    'bbox': [round(min(xs), 4), round(max(xs), 4), round(min(ys), 4), round(max(ys), 4)],
    'materials': mats,
}}
""".format(str(SVG))}))
    print("imported:", json.dumps(r, ensure_ascii=False)[:900])

    # --- Phase B: normalize, extrude, join, recolor to Principled nodes ---
    r = code_result(call(client, "execute_blender_code", {"code": """
import bpy
from mathutils import Vector

curves = [o for o in bpy.data.objects if o.type == 'CURVE']

def world_bbox(objs):
    xs, ys, zs = [], [], []
    for o in objs:
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)

x0, x1, y0, y1, z0, z1 = world_bbox(curves)
s = 2.0 / max(x1 - x0, y1 - y0)

# Scale at the object level. The extrude depth lives in curve-data units,
# so compensate by 1/s to land at world units after conversion. Detail
# paths extrude deeper than the body so their faces sit proud of the
# body surface (coplanar faces would z-fight).
areas = {}
for o in curves:
    ox0, ox1, oy0, oy1, _, _ = world_bbox([o])
    areas[o.name] = (ox1 - ox0) * (oy1 - oy0)
body_name = max(areas, key=areas.get)
for o in curves:
    depth = 0.12 if o.name == body_name else 0.18
    o.scale = (s, s, s)
    o.data.extrude = depth / s
    o.data.fill_mode = 'BOTH'
    o.data.resolution_u = 12
for o in curves:
    o.select_set(True)
bpy.context.view_layer.objects.active = curves[0]
bpy.ops.object.convert(target='MESH')
bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]
if len(bpy.context.selected_objects) > 1:
    bpy.ops.object.join()
emoji = bpy.context.active_object
emoji.name = 'Emoji'
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# SVG importer materials are viewport-only; rebuild them as Principled nodes.
for mat in bpy.data.materials:
    color = tuple(mat.diffuse_color[:3])
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (*color, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.45
    mat.node_tree.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
emoji.location = (0.0, 0.0, 0.0)
emoji.rotation_euler = (1.5707963, 0.0, 0.0)
bx0, bx1, by0, by1, bz0, bz1 = world_bbox([emoji])
result = {
    'mesh': emoji.name,
    'verts': len(emoji.data.vertices),
    'faces': len(emoji.data.polygons),
    'materials': [m.name for m in emoji.data.materials],
    'world_bbox': [round(v, 3) for v in (bx0, bx1, by0, by1, bz0, bz1)],
}
"""}))
    print("mesh:", r)
    assert r.get("verts", 0) > 0 and abs(max(r["world_bbox"]) - min(r["world_bbox"])) < 6.0, "bad proportions"

    # --- Phase C: structured tools ---
    ground = call(client, "object_create", {
        "primitive": "PLANE", "name": "Ground", "location": [0.0, 0.0, -1.001], "scale": [10.0, 10.0, 1.0]})
    assert ground.get("ok") is True, ground
    ground_mat = call(client, "material_create_or_update", {
        "name": "GroundMat", "base_color": [0.82, 0.82, 0.84], "roughness": 0.9})
    assert ground_mat.get("ok") is True, ground_mat
    assign = call(client, "material_assign", {"object": "Ground", "material": "GroundMat"})
    assert assign.get("ok") is True, assign

    bevel = call(client, "modifier_manage", {
        "object": "Emoji", "action": "add", "type": "BEVEL",
        "properties": {"width": 0.004, "segments": 2}})
    assert bevel.get("ok") is True, bevel
    print("bevel added")

    cam = code_result(call(client, "execute_blender_code", {"code": """
import bpy
bpy.ops.object.camera_add(location=(0, 0, 0))
result = {'camera': bpy.context.active_object.name}
"""}))
    camera_name = cam["camera"]

    framed = call(client, "camera_frame", {
        "objects": ["Emoji"], "camera": camera_name, "view": "THREE_QUARTER", "padding": 0.18})
    assert framed.get("ok") is True, framed
    print("camera framed")

    key = call(client, "light_create_or_update", {
        "name": "KeyLight", "type": "AREA", "energy": 550.0, "size": 1.8,
        "location": [2.2, -2.8, 2.6], "rotation": [0.9, 0.0, 0.65]})
    assert key.get("ok") is True, key
    fill = code_result(call(client, "execute_blender_code", {"code": """
import bpy
bpy.ops.object.light_add(type='SUN', location=(0, 0, 5))
sun = bpy.context.active_object
sun.data.energy = 0.9
sun.rotation_euler = (0.7, 0.2, 2.4)
world = bpy.context.scene.world or bpy.data.worlds.new('World')
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
bg.inputs[0].default_value = (0.72, 0.78, 0.88, 1.0)
bg.inputs[1].default_value = 0.35
result = {'fill': sun.name}
"""}))
    print("lights:", key.get("target"), fill.get("fill"))

    conf = call(client, "render_configure", {
        "engine": "CYCLES", "resolution_x": 1024, "resolution_y": 1024, "samples": 48})
    assert conf.get("ok") is True, conf
    cpu = code_result(call(client, "execute_blender_code", {"code": """
import bpy
bpy.context.scene.cycles.device = 'CPU'
result = {'device': bpy.context.scene.cycles.device}
"""}))
    print("render engine:", conf, cpu)

    png = OUT_DIR / "emoji_u1f416_pig.png"
    preview = call(client, "render_preview", {"output_path": str(png), "max_dimension": 1024})
    assert preview.get("ok") is True, preview
    print("preview:", png.stat().st_size, "bytes")

    blend = OUT_DIR / "emoji_u1f416_pig.blend"
    saved = code_result(call(client, "execute_blender_code", {"code": """
import bpy
bpy.ops.wm.save_as_mainfile(filepath={!r})
result = {{'saved': bpy.data.filepath}}
""".format(str(blend))}))
    print("blend saved:", saved)

    client.close()
finally:
    blender_proc.terminate()
    try:
        blender_proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        blender_proc.kill()

print("DONE")
print("artifacts:", png, blend)
