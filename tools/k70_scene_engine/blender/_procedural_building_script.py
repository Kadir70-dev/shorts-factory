"""Runs INSIDE Blender. Builds simple, ORIGINAL, parametric building
exteriors from primitive geometry -- house, bank, office building, store.

Why procedural primitives instead of a downloaded building model: verified
live against all three vendored/available asset sources before writing
this file --
  - Poly Haven's real, documented API (521 real models queried 2026-08-22)
    has ZERO full house/bank/office building exteriors -- confirmed by
    keyword search across every record, not assumed.
  - cc0-asset-index's Quaternius/Kenney indexers are metadata-only (see
    catalog/sources/cc0_asset_index.py) with no working downloader.
  - Gobkit and CC0Tree are character/prop packs, not architecture.

Building generic massing from primitives sidesteps that gap entirely and
has a real benefit the brief asked for directly: "These do not need to
reproduce real trademarked buildings. They need to communicate the
concept visually" -- a parametric box+roof IS a house silhouette to a
viewer in 3 seconds of screen time, without any licensing question at all.

Each `build_*(width, depth, height, seed)` function returns the list of
created objects. Called from `main()` based on `building_type` in the
JSON spec (same `--background --python ... -- args.json` convention as
scene_builder_script.py).
"""
import json
import random
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _procedural_building_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def _material(name: str, color, roughness=0.7, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
    return mat


def _box(name, size, location, material=None):
    # `primitive_cube_add(size=1)` already creates a FULL 1x1x1 cube (the
    # "size" arg is edge length, not half-extent/radius) -- scaling by
    # size/2 here was a real bug that silently halved every building's
    # actual footprint relative to anything built at literal scale (like
    # this file's hand-built gable roof, which uses real width/depth
    # directly). Confirmed by direct measurement: build_house(width=6)
    # produced a body with dims.x=3.0, not 6.0. Invisible in a standalone
    # render (camera auto-frames to whatever size exists) but is exactly
    # why the roof visually swallowed the body in the voxel-story render
    # (roof at ~full requested scale, body at half).
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(scale=True)
    if material:
        obj.data.materials.append(material)
    return obj


def build_house(width=6.0, depth=8.0, height=3.2, seed=0):
    """Box body + gable roof + a door-shaped inset + window insets --
    the minimum silhouette a viewer reads as "a house" without needing
    any texture detail at all."""
    random.seed(seed)
    objs = []
    wall_mat = _material("k70_house_wall", (0.85, 0.80, 0.70), roughness=0.85)
    roof_mat = _material("k70_house_roof", (0.30, 0.18, 0.15), roughness=0.6)
    door_mat = _material("k70_house_door", (0.35, 0.22, 0.12), roughness=0.5)
    window_mat = _material("k70_house_window", (0.55, 0.75, 0.85), roughness=0.1, metallic=0.2)

    body = _box("house_body", (width, depth, height), (0, 0, height / 2), wall_mat)
    objs.append(body)

    # gable roof, built explicitly (not a cube deformation): ridge line
    # runs along Y at X=0; two rectangular slopes connect the ridge to the
    # left/right base edges, two triangular gables cap front/back.
    bm = bmesh.new()
    roof_h = height * 0.55
    hw, hd = width / 2 * 1.08, depth / 2 * 1.05
    b0 = bm.verts.new((-hw, -hd, 0))   # front-left
    b1 = bm.verts.new((hw, -hd, 0))    # front-right
    b2 = bm.verts.new((hw, hd, 0))     # back-right
    b3 = bm.verts.new((-hw, hd, 0))    # back-left
    r0 = bm.verts.new((0, -hd, roof_h))  # front ridge point
    r1 = bm.verts.new((0, hd, roof_h))   # back ridge point
    bm.faces.new((b0, b3, r1, r0))   # left slope
    bm.faces.new((b1, r0, r1, b2))   # right slope
    bm.faces.new((b0, b1, r0))       # front gable
    bm.faces.new((b3, r1, b2))       # back gable
    bm.faces.new((b0, b1, b2, b3))   # base -- closes the shell so the roof
                                      # is watertight. Left open, this mesh
                                      # made Blender's Voxel Remesh (used
                                      # by the voxel-story pipeline)
                                      # pathologically slow -- a real,
                                      # confirmed hang (10+ minutes, still
                                      # climbing CPU) on the open shell,
                                      # gone once the mesh is closed.
    mesh = bpy.data.meshes.new("house_roof_mesh")
    bm.to_mesh(mesh)
    bm.free()
    roof = bpy.data.objects.new("house_roof", mesh)
    bpy.context.collection.objects.link(roof)
    roof.location = (0, 0, height)
    roof.data.materials.append(roof_mat)
    objs.append(roof)

    door = _box("house_door", (width * 0.16, 0.1, height * 0.55),
                (0, -depth / 2 - 0.05, height * 0.275), door_mat)
    objs.append(door)

    for side in (-1, 1):
        win = _box(f"house_window_{side}", (width * 0.18, 0.08, height * 0.28),
                   (side * width * 0.28, -depth / 2 - 0.04, height * 0.55), window_mat)
        objs.append(win)
    return objs


def build_bank(width=10.0, depth=8.0, height=5.0, n_columns=5, seed=0):
    """Box body + a row of columns + a triangular pediment -- the
    generic "classical financial institution" silhouette, not any real
    bank's actual branded architecture."""
    objs = []
    stone_mat = _material("k70_bank_stone", (0.80, 0.78, 0.72), roughness=0.75)
    col_mat = _material("k70_bank_column", (0.88, 0.86, 0.80), roughness=0.6)
    door_mat = _material("k70_bank_door", (0.15, 0.12, 0.10), roughness=0.3, metallic=0.4)

    body = _box("bank_body", (width, depth, height), (0, 0, height / 2), stone_mat)
    objs.append(body)

    col_h = height * 0.85
    col_r = 0.35
    span = width * 0.8
    for i in range(n_columns):
        x = -span / 2 + span * i / (n_columns - 1)
        bpy.ops.mesh.primitive_cylinder_add(radius=col_r, depth=col_h,
                                            location=(x, -depth / 2 - col_r, col_h / 2))
        col = bpy.context.active_object
        col.name = f"bank_column_{i}"
        col.data.materials.append(col_mat)
        objs.append(col)

    pediment_h = height * 0.22
    bm = bmesh.new()
    hw = width / 2 * 0.9
    base_z, apex_z = height, height + pediment_h
    d0, d1 = -depth / 2 - col_r * 2, -depth / 2 - col_r * 2 + 0.6
    verts = [
        bm.verts.new((-hw, d0, base_z)), bm.verts.new((hw, d0, base_z)),
        bm.verts.new((hw, d1, base_z)), bm.verts.new((-hw, d1, base_z)),
        bm.verts.new((0, (d0 + d1) / 2, apex_z)),
    ]
    bm.faces.new((verts[0], verts[1], verts[2], verts[3]))
    bm.faces.new((verts[0], verts[3], verts[4]))
    bm.faces.new((verts[1], verts[0], verts[4]))
    bm.faces.new((verts[2], verts[1], verts[4]))
    bm.faces.new((verts[3], verts[2], verts[4]))
    mesh = bpy.data.meshes.new("bank_pediment_mesh")
    bm.to_mesh(mesh)
    bm.free()
    pediment = bpy.data.objects.new("bank_pediment", mesh)
    bpy.context.collection.objects.link(pediment)
    pediment.data.materials.append(stone_mat)
    objs.append(pediment)

    door = _box("bank_door", (width * 0.14, 0.1, height * 0.5),
                (0, -depth / 2 - 0.05, height * 0.25), door_mat)
    objs.append(door)
    return objs


def build_office(width=8.0, depth=8.0, height=18.0, floors=6, seed=0):
    """A tall box with a regular window grid -- generic corporate office
    tower massing."""
    objs = []
    facade_mat = _material("k70_office_facade", (0.55, 0.60, 0.65), roughness=0.4, metallic=0.3)
    window_mat = _material("k70_office_window", (0.35, 0.55, 0.70), roughness=0.05, metallic=0.6)

    body = _box("office_body", (width, depth, height), (0, 0, height / 2), facade_mat)
    objs.append(body)

    win_w, win_h = width * 0.12, height / floors * 0.55
    for floor in range(floors):
        z = height / floors * (floor + 0.5)
        for col in range(3):
            x = -width * 0.3 + width * 0.3 * col
            win = _box(f"office_window_{floor}_{col}", (win_w, 0.06, win_h),
                      (x, -depth / 2 - 0.03, z), window_mat)
            objs.append(win)
    return objs


def build_store(width=7.0, depth=6.0, height=3.6, seed=0):
    """Box body + full glass storefront + a signage plinth."""
    objs = []
    wall_mat = _material("k70_store_wall", (0.75, 0.72, 0.68), roughness=0.8)
    glass_mat = _material("k70_store_glass", (0.6, 0.75, 0.8), roughness=0.05, metallic=0.1)
    sign_mat = _material("k70_store_sign", (0.9, 0.75, 0.15), roughness=0.4)

    body = _box("store_body", (width, depth, height), (0, 0, height / 2), wall_mat)
    objs.append(body)
    glass = _box("store_glass", (width * 0.85, 0.06, height * 0.65),
                (0, -depth / 2 - 0.03, height * 0.35), glass_mat)
    objs.append(glass)
    sign = _box("store_sign", (width * 0.6, 0.15, height * 0.15),
               (0, -depth / 2 - 0.1, height * 0.9), sign_mat)
    objs.append(sign)
    return objs


BUILDERS = {"house": build_house, "bank": build_bank, "office": build_office, "store": build_store}


def main() -> None:
    a = _args()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    btype = a["building_type"]
    if btype not in BUILDERS:
        raise ValueError(f"unknown building_type '{btype}'; known: {list(BUILDERS)}")
    params = a.get("params", {})
    BUILDERS[btype](**params)

    # Compute the camera framing from the BUILDING ONLY, before the ground
    # plane exists -- including a 40-unit ground plane in the bounding box
    # made "span" huge and shrank the building to a speck in the first
    # test render (see FINAL_REPORT.md).
    mins = Vector((float("inf"),) * 3)
    maxs = Vector((float("-inf"),) * 3)
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            wc = obj.matrix_world @ Vector(corner)
            mins = Vector(min(x, y) for x, y in zip(mins, wc))
            maxs = Vector(max(x, y) for x, y in zip(maxs, wc))
    center = (mins + maxs) / 2
    span = max((maxs - mins).x, (maxs - mins).y, (maxs - mins).z, 1.0)
    distance = span * 1.35

    # ground plane, sized relative to the building instead of a fixed 40
    # units, and added AFTER the framing math above
    bpy.ops.mesh.primitive_plane_add(size=span * 6, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground_mat = bpy.data.materials.new("k70_ground")
    ground_mat.use_nodes = True
    bsdf = ground_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.25, 0.28, 0.24, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.9
    ground.data.materials.append(ground_mat)

    cam_data = bpy.data.cameras.new("k70_cam")
    cam_data.lens = 32
    cam_obj = bpy.data.objects.new("k70_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = center + Vector((distance * 0.9, -distance * 1.3, distance * 0.55))
    direction = center - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam_obj

    world = bpy.data.worlds.new("k70_world")
    world.use_nodes = True
    bpy.context.scene.world = world
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.55, 0.65, 0.78, 1.0)
        bg.inputs["Strength"].default_value = 1.0

    sun_data = bpy.data.lights.new("k70_sun", type="SUN")
    sun_data.energy = 4.5
    sun_obj = bpy.data.objects.new("k70_sun", sun_data)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = (0.85, 0, 0.9)

    render = a["render"]
    scene = bpy.context.scene
    scene.render.engine = render["engine"]
    scene.render.resolution_x = render["width"]
    scene.render.resolution_y = render["height"]
    scene.render.filepath = render["output"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_stamp = False
    if render["engine"] == "CYCLES":
        scene.cycles.samples = render["samples"]
    elif hasattr(scene, "eevee"):
        try:
            scene.eevee.taa_render_samples = render["samples"]
        except AttributeError:
            pass

    bpy.ops.render.render(write_still=True)
    print(f"K70_BUILDING_RENDER_OK {render['output']} type={btype}")


if __name__ == "__main__":
    main()
