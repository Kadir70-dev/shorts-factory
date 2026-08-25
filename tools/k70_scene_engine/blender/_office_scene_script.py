"""Runs INSIDE Blender. Builds a genuine furnished office vignette: two
walls + floor + a real Poly Haven desk/chair/laptop/lamp/clock
composition, lit with an HDRI office-interior environment. Replaces the
"character standing on an empty floor in front of a flat gradient" look
with an actual set.

    blender --background --python _office_scene_script.py -- <args.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
from mathutils import Vector

from lighting_presets import setup_lighting, apply_hdri_world  # noqa: E402
from camera_presets import build_camera  # noqa: E402

POLYHAVEN_DIR = Path(__file__).resolve().parents[1] / "vendor" / "polyhaven"


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _office_scene_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def _import_prop(slug: str, location, rotation_z: float = 0.0, scale: float = 1.0):
    gltf_path = POLYHAVEN_DIR / slug / f"{slug}.gltf"
    if not gltf_path.exists():
        raise FileNotFoundError(f"prop not found: {gltf_path}")
    bpy.ops.import_scene.gltf(filepath=str(gltf_path))
    imported = list(bpy.context.selected_objects)
    for o in imported:
        if o.parent is None:
            o.location = location
            o.rotation_euler = (0, 0, rotation_z)
            o.scale = (scale, scale, scale)
    return imported


def _material(name, color, roughness=0.85, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def build_office_set(width=5.0, depth=4.0, height=2.8):
    """Floor + back wall + side wall (an open box, camera-facing side
    left open) + real furniture. Returns the list of created objects."""
    objs = []
    wall_mat = _material("k70_office_wall", (0.82, 0.80, 0.76), roughness=0.9)
    floor_mat = _material("k70_office_floor", (0.35, 0.28, 0.22), roughness=0.35, metallic=0.05)

    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "office_floor"
    floor.scale = (width, depth, 1)
    bpy.ops.object.transform_apply(scale=True)
    floor.data.materials.append(floor_mat)
    objs.append(floor)

    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, depth / 2, height / 2))
    back_wall = bpy.context.active_object
    back_wall.name = "office_back_wall"
    back_wall.rotation_euler = (1.5708, 0, 0)
    back_wall.scale = (width, height, 1)
    bpy.ops.object.transform_apply(scale=True)
    back_wall.data.materials.append(wall_mat)
    objs.append(back_wall)

    bpy.ops.mesh.primitive_plane_add(size=1, location=(-width / 2, 0, height / 2))
    side_wall = bpy.context.active_object
    side_wall.name = "office_side_wall"
    side_wall.rotation_euler = (0, 1.5708, 0)
    side_wall.scale = (depth, height, 1)
    bpy.ops.object.transform_apply(scale=True)
    side_wall.data.materials.append(wall_mat)
    objs.append(side_wall)

    # window cutout stand-in: a bright emissive panel on the side wall
    # (a real boolean window cutout is out of scope for the time budget;
    # this reads as daylight coming through a window at a glance without
    # needing a real hole in the geometry)
    win_mat = bpy.data.materials.new("k70_window_glow")
    win_mat.use_nodes = True
    emit = win_mat.node_tree.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (0.75, 0.82, 0.95, 1.0)
    emit.inputs["Strength"].default_value = 1.8
    out = win_mat.node_tree.nodes.get("Material Output")
    win_mat.node_tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    bpy.ops.mesh.primitive_plane_add(size=1, location=(-width / 2 + 0.01, depth * 0.15, height * 0.6))
    window = bpy.context.active_object
    window.name = "office_window_glow"
    window.rotation_euler = (0, 1.5708, 0)
    window.scale = (depth * 0.35, height * 0.4, 1)
    bpy.ops.object.transform_apply(scale=True)
    window.data.materials.append(win_mat)
    objs.append(window)

    # real furniture, real PBR Poly Haven assets
    objs += _import_prop("metal_office_desk", (0, depth * 0.15, 0), rotation_z=3.14159, scale=1.0)
    objs += _import_prop("SchoolChair_01", (0, depth * 0.42, 0), rotation_z=0.0, scale=1.0)
    objs += _import_prop("classic_laptop", (0.05, depth * 0.05, 0.75), rotation_z=2.9, scale=1.0)
    objs += _import_prop("desk_lamp_arm_01", (-0.55, depth * 0.05, 0.75), rotation_z=0.0, scale=1.0)
    objs += _import_prop("wall_clock", (width * 0.3, depth / 2 - 0.03, height * 0.75), rotation_z=1.5708, scale=1.0)
    objs += _import_prop("drawer_cabinet", (0.85, depth * 0.32, 0), rotation_z=0.0, scale=1.0)

    return objs


def main() -> None:
    a = _args()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    build_office_set(width=a.get("width", 5.0), depth=a.get("depth", 4.0), height=a.get("height", 2.8))

    mins = Vector((float("inf"),) * 3)
    maxs = Vector((float("-inf"),) * 3)
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            wc = obj.matrix_world @ Vector(corner)
            mins = Vector(min(x, y) for x, y in zip(mins, wc))
            maxs = Vector(max(x, y) for x, y in zip(maxs, wc))

    setup_lighting("office_interior", mins, maxs, add_ground=False, rotation_z=2.4)
    build_camera(a.get("shot", "medium"), mins, maxs, angle=a.get("angle", "three_quarter"))

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = a.get("width_px", 1280)
    scene.render.resolution_y = a.get("height_px", 720)
    scene.render.filepath = a["output"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_stamp = False
    if hasattr(scene, "eevee"):
        try:
            scene.eevee.taa_render_samples = a.get("samples", 64)
            scene.eevee.use_raytracing = True
        except AttributeError:
            pass

    bpy.ops.render.render(write_still=True)
    print(f"K70_OFFICE_RENDER_OK {a['output']}")


if __name__ == "__main__":
    main()
