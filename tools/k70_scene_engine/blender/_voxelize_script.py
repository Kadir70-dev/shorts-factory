"""Runs INSIDE Blender (bpy). Invoked by voxelizer.py via
`blender --background --python _voxelize_script.py -- <args.json>`.

The vertex-bucketing algorithm (`_bucket_vertices`) is a direct, credited
adaptation of `create_blocks()` in the vendored
`minecraft-voxel-loader-scripts/Scripts/blender_voxelizer.py` (MIT
license, carl-vbn) -- same idea (floor each world-space vertex position
into a block_size grid cell, keep one representative color per occupied
cell) -- but everything downstream is original: instead of writing a
Minecraft `.blocks` file for a Fabric mod to place real Minecraft blocks,
`_build_voxel_mesh()` builds actual cube primitives in THIS Blender scene
and `main()` renders them with Blender's own engine. No Minecraft/Fabric/
Mojang code, format, or asset is read, written, or required anywhere in
this file.
"""
import json
import sys
from math import floor
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _voxelize_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def _source_material_color(obj) -> tuple[float, float, float] | None:
    """Falls back to the source object's own Principled-BSDF base color
    when there's no vertex-color layer. Every procedural/prop object this
    engine builds (_procedural_building_script.py, _character_roster.py,
    etc.) sets material color this way, not via vertex colors -- without
    this fallback, every voxelized object rendered flat uniform gray
    (confirmed by a real render: a voxelized house came out entirely
    white/gray, roof and walls and door all identical, no part
    distinguishable from any other)."""
    if not obj.data.materials:
        return None
    mat = obj.data.materials[0]
    if mat is None or not mat.use_nodes:
        return None
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        return None
    r, g, b, _a = bsdf.inputs["Base Color"].default_value
    return (r, g, b)


def _bucket_vertices(obj, block_size: float) -> dict[tuple[int, int, int], tuple[float, float, float]]:
    """Adapted from blender_voxelizer.py's create_blocks(): floor every
    world-space vertex into a block_size grid cell, keep one vertex color
    per occupied cell -- vertex color layer if the mesh has one, else the
    source object's own material color, else white."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    bm.from_object(obj, depsgraph)
    bm.verts.ensure_lookup_table()

    color_layer = bm.loops.layers.color.active if bm.loops.layers.color else None
    vertex_colors = {}
    if color_layer is not None:
        for face in bm.faces:
            for loop in face.loops:
                vertex_colors[loop.vert.index] = tuple(loop[color_layer])[:3]

    fallback_color = _source_material_color(obj) or (0.85, 0.85, 0.85)

    blocks: dict[tuple[int, int, int], tuple[float, float, float]] = {}
    for vertex in bm.verts:
        world_pos = obj.matrix_world @ vertex.co
        cell = (floor(world_pos.x / block_size), floor(world_pos.y / block_size),
                floor(world_pos.z / block_size))
        blocks.setdefault(cell, vertex_colors.get(vertex.index, fallback_color))
    bm.free()
    return blocks


def _build_voxel_mesh(blocks: dict, block_size: float) -> None:
    """Places one cube per occupied cell, colored by the bucketed vertex
    color. No Minecraft block placement or client involved.

    FIRST version called `bpy.ops.mesh.primitive_cube_add()` once per
    block via the operator. Fine at the small counts the dollar-sign/car
    tests used, but a real, confirmed bug at house/bank scale: ~2500
    blocks took 5+ minutes and never finished (operator-call overhead
    dominates at that count). This instead groups blocks by color and
    builds ONE combined bmesh per color group (typically a handful of
    groups, not thousands of operator calls), so total object/material
    count stays small regardless of how many voxels there are."""
    groups: dict[tuple, list[tuple[int, int, int]]] = {}
    for cell, color in blocks.items():
        key = tuple(round(c, 2) for c in color)
        groups.setdefault(key, []).append(cell)

    half = block_size * 0.96 / 2
    cube_offsets = [
        (-half, -half, -half), (half, -half, -half), (half, half, -half), (-half, half, -half),
        (-half, -half, half), (half, -half, half), (half, half, half), (-half, half, half),
    ]
    cube_faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]

    for i, (color, cells) in enumerate(groups.items()):
        bm = bmesh.new()
        for (bx, by, bz) in cells:
            cx, cy, cz = (bx + 0.5) * block_size, (by + 0.5) * block_size, (bz + 0.5) * block_size
            verts = [bm.verts.new((cx + ox, cy + oy, cz + oz)) for ox, oy, oz in cube_offsets]
            for face in cube_faces:
                bm.faces.new([verts[idx] for idx in face])
        mesh = bpy.data.meshes.new(f"k70_voxel_group_{i}")
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(f"k70_voxel_group_{i}", mesh)
        bpy.context.collection.objects.link(obj)

        mat = bpy.data.materials.new(name=f"k70_voxel_mat_{i}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        obj.data.materials.append(mat)


def main() -> None:
    a = _args()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    src = Path(a["source_path"])
    fmt = a["source_format"]
    if fmt == "glb":
        bpy.ops.import_scene.gltf(filepath=str(src))
    elif fmt == "fbx":
        bpy.ops.import_scene.fbx(filepath=str(src))
    else:
        raise ValueError(f"unsupported source_format '{fmt}'")

    mesh_objs = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if not mesh_objs:
        raise RuntimeError(f"no mesh objects imported from {src}")

    block_size = a["block_size"]
    all_blocks: dict = {}
    for obj in mesh_objs:
        all_blocks.update(_bucket_vertices(obj, block_size))
    if not all_blocks:
        raise RuntimeError("voxelization produced zero occupied cells -- source mesh may be empty or block_size too large")

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    _build_voxel_mesh(all_blocks, block_size)

    cam_data = bpy.data.cameras.new("k70_voxel_cam")
    cam_obj = bpy.data.objects.new("k70_voxel_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    xs = [bx for bx, by, bz in all_blocks]
    ys = [by for bx, by, bz in all_blocks]
    zs = [bz for bx, by, bz in all_blocks]
    cx, cy, cz = ((min(xs) + max(xs)) / 2 * block_size,
                  (min(ys) + max(ys)) / 2 * block_size,
                  (min(zs) + max(zs)) / 2 * block_size)
    span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1) * block_size
    cam_obj.location = (cx + span * 1.6, cy - span * 1.6, cz + span * 1.2)
    direction = Vector((cx, cy, cz)) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam_obj

    sun_data = bpy.data.lights.new("k70_voxel_sun", type="SUN")
    sun_data.energy = 3.5
    sun_obj = bpy.data.objects.new("k70_voxel_sun", sun_data)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = (0.9, 0, 0.6)

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
    print(f"K70_VOXEL_RENDER_OK {render['output']} blocks={len(all_blocks)}")


if __name__ == "__main__":
    main()
