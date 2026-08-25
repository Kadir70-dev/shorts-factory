"""Runs INSIDE Blender. Voxel STORYTELLING mode: builds a recognizable
primitive (house / bank / dollar sign / car / person-marker) and
voxelizes THAT, instead of voxelizing an organic character mesh into an
unreadable cube blob (the audit's core complaint about the mortgage
video's one voxel scene).

Reuses `_bucket_vertices`/`_build_voxel_mesh` from `_voxelize_script.py`
and `build_house`/`build_bank` from `_procedural_building_script.py` via
sys.path -- same directory, plain-Python import, no package needed since
these run standalone inside Blender's interpreter anyway.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
import bmesh
from mathutils import Vector

from _voxelize_script import _bucket_vertices, _build_voxel_mesh  # noqa: E402
from _procedural_building_script import build_house, build_bank, _material  # noqa: E402


def _densify(obj, target_edge_len: float) -> None:
    """`_bucket_vertices` only samples existing mesh VERTICES (proven fine
    on the organic, densely-subdivided gobkit character mesh). Low-poly
    architectural primitives have almost none -- a cube has 8 -- so
    without this, voxelizing a house leaves a sparse, disconnected
    scatter of cubes instead of a solid recognizable shape.

    FIRST fix used `bpy.ops.mesh.subdivide(number_cuts=N)` in a loop.
    That produced a real, confirmed bug on this file's hand-built roof
    bmesh: subdividing large custom quad/n-gon faces this way created
    uneven "ribbon" banding (long strips subdivided finely along one axis
    but not the other) instead of a uniform grid -- visually confirmed by
    a real render showing the roof as a giant terraced slab dominating
    the frame while the simple cube-based wall body stayed comparatively
    sparse. Rather than special-case the subdivide operator further, this
    uses Blender's built-in Voxel Remesh (`obj.data.remesh_voxel_size` +
    `bpy.ops.object.voxel_remesh()`) -- an OpenVDB level-set remesher
    purpose-built for turning arbitrary (including non-manifold/n-gon)
    geometry into a uniformly dense, watertight mesh at a target
    resolution. It does not care how the original faces were wound or
    shaped, which is exactly the property the subdivide-loop lacked."""
    # Voxel Remesh collapses to an EMPTY mesh when the requested voxel
    # size is larger than the object's own thinnest dimension (confirmed
    # by a real test: door/window insets ~0.08-0.1 units thick vanished
    # entirely -- 0 verts, 0 blocks -- at the default 0.28 target). Clamp
    # per-object so thin slabs get a finer local voxel size instead of
    # disappearing; thick objects (walls, roof) still use the requested
    # resolution unchanged.
    thinnest = min((d for d in obj.dimensions if d > 1e-6), default=target_edge_len)
    voxel_size = min(target_edge_len, thinnest / 3.0)
    voxel_size = max(voxel_size, 0.01)

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)

    # Defensive: an open (non-watertight) shell made Voxel Remesh
    # pathologically slow on this file's hand-built roof bmesh (a real,
    # confirmed hang -- 10+ minutes, still climbing CPU -- gone once that
    # specific mesh was closed at the source in
    # _procedural_building_script.py). Close any remaining open boundary
    # here too, generically, so any future hand-built shape doesn't
    # reproduce the same hang.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.fill_holes(sides=0)
    bpy.ops.object.mode_set(mode="OBJECT")

    obj.data.remesh_voxel_size = voxel_size
    obj.data.remesh_voxel_adaptivity = 0.0
    bpy.ops.object.voxel_remesh()


def _densify_subdivide(obj, target_edge_len: float) -> None:
    """The ORIGINAL densify approach (kept, not deleted): repeated
    `bpy.ops.mesh.subdivide()`. Voxel Remesh (above) fixed a real bug on
    hand-built architectural bmesh (uneven ribbon banding on the house
    roof) but introduced a real regression of its own on thin curved
    glyph geometry -- confirmed by a render: build_dollar_sign()'s "$"
    became an unreadable smoothed/filled blob under Voxel Remesh at
    multiple resolutions and camera angles, where the ORIGINAL subdivide
    approach (this function, proven correct in the previous session)
    preserved its sharp curves correctly. Used only for that shape type
    -- see main()'s per-object-type dispatch."""
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bm = bmesh.from_edit_mesh(obj.data)
    for _ in range(8):
        max_len = max((e.calc_length() for e in bm.edges), default=0.0)
        if max_len <= target_edge_len:
            break
        cuts = max(1, int(max_len / target_edge_len))
        bpy.ops.mesh.subdivide(number_cuts=cuts)
        bm = bmesh.from_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode="OBJECT")


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _voxel_story_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def build_dollar_sign(height=3.0, seed=0):
    """Extruded text '$' -- an unambiguous "money" glyph, not an
    abstract shape standing in for money."""
    bpy.ops.object.text_add(location=(0, 0, 0))
    txt = bpy.context.active_object
    txt.data.body = "$"
    txt.data.extrude = 0.15
    txt.data.size = height
    txt.data.align_x = "CENTER"
    txt.data.align_y = "CENTER"
    bpy.ops.object.convert(target="MESH")
    mat = _material("k70_dollar", (0.15, 0.65, 0.25), roughness=0.4, metallic=0.3)
    txt.data.materials.append(mat)
    return [txt]


def build_car(length=4.2, width=1.8, height=1.4, seed=0):
    """A simple boxy car silhouette -- cabin + body + 4 wheels."""
    objs = []
    body_mat = _material("k70_car_body", (0.75, 0.15, 0.15), roughness=0.35, metallic=0.4)
    wheel_mat = _material("k70_car_wheel", (0.05, 0.05, 0.05), roughness=0.8)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, height * 0.3))
    body = bpy.context.active_object
    body.name = "car_body"
    body.scale = (length / 2, width / 2, height * 0.3)
    bpy.ops.object.transform_apply(scale=True)
    body.data.materials.append(body_mat)
    objs.append(body)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(-length * 0.05, 0, height * 0.7))
    cabin = bpy.context.active_object
    cabin.name = "car_cabin"
    cabin.scale = (length * 0.32, width / 2 * 0.9, height * 0.25)
    bpy.ops.object.transform_apply(scale=True)
    cabin.data.materials.append(body_mat)
    objs.append(cabin)

    for dx in (-1, 1):
        for dy in (-1, 1):
            bpy.ops.mesh.primitive_cylinder_add(
                radius=height * 0.22, depth=width * 0.15,
                rotation=(1.5708, 0, 0),
                location=(dx * length * 0.32, dy * width * 0.52, height * 0.22))
            wheel = bpy.context.active_object
            wheel.name = f"car_wheel_{dx}_{dy}"
            wheel.data.materials.append(wheel_mat)
            objs.append(wheel)
    return objs


BUILDERS = {"house": build_house, "bank": build_bank, "dollar": build_dollar_sign, "car": build_car}


def main() -> None:
    a = _args()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    object_type = a["object_type"]
    if object_type not in BUILDERS:
        raise ValueError(f"unknown object_type '{object_type}'; known: {list(BUILDERS)}")
    BUILDERS[object_type](**a.get("params", {}))

    block_size = a["block_size"]
    densify_fn = _densify_subdivide if object_type == "dollar" else _densify
    for obj in list(bpy.data.objects):
        if obj.type == "MESH":
            print(f"K70_DEBUG pre-densify {obj.name} verts={len(obj.data.vertices)} "
                  f"dims={tuple(round(x, 2) for x in obj.dimensions)}")
            sys.stdout.flush()
            densify_fn(obj, block_size * 0.8)
            print(f"K70_DEBUG post-densify {obj.name} verts={len(obj.data.vertices)} "
                  f"dims={tuple(round(x, 2) for x in obj.dimensions)}")
            sys.stdout.flush()

    all_blocks: dict = {}
    for obj in list(bpy.data.objects):
        if obj.type == "MESH":
            b = _bucket_vertices(obj, block_size)
            print(f"K70_DEBUG blocks from {obj.name}: {len(b)}")
            sys.stdout.flush()
            all_blocks.update(b)
    if not all_blocks:
        raise RuntimeError(f"voxelization of '{object_type}' produced zero occupied cells")

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    _build_voxel_mesh(all_blocks, block_size)

    xs = [bx for bx, by, bz in all_blocks]
    ys = [by for bx, by, bz in all_blocks]
    zs = [bz for bx, by, bz in all_blocks]
    cx, cy, cz = ((min(xs) + max(xs)) / 2 * block_size,
                  (min(ys) + max(ys)) / 2 * block_size,
                  (min(zs) + max(zs)) / 2 * block_size)
    span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1) * block_size

    cam_data = bpy.data.cameras.new("k70_voxel_cam")
    cam_obj = bpy.data.objects.new("k70_voxel_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = (cx + span * 1.6, cy - span * 1.6, cz + span * 1.1)
    cam_obj.rotation_euler = (Vector((cx, cy, cz)) - cam_obj.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam_obj

    world = bpy.data.worlds.new("k70_world")
    world.use_nodes = True
    bpy.context.scene.world = world
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.06, 0.07, 0.10, 1.0)
        bg.inputs["Strength"].default_value = 0.5

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
    print(f"K70_VOXEL_STORY_RENDER_OK {render['output']} type={object_type} blocks={len(all_blocks)}")


if __name__ == "__main__":
    main()
