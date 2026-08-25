"""K70 3D Motion Graphics engine. Runs inside Blender.

REMOVED (2026-08-26): the generic growth_stage/milestone "capital block"
template that used to live here -- a row of beveled boxes that grow taller
per milestone, with an extruded 3D numeral above each. It produced
meaningless output whenever the caller had no real financial mechanism to
show and passed a placeholder milestone anyway (confirmed case: shot H3 in
data/jobs/k70_fed_money_creation_ep01_v3, milestone label "?", rendered as
an unlabeled beige/gold pillar with no semantic content -- see
K70_FINANCE_STRICT_CINEMATIC_POLICY discussion). Removing it here removes
the ONLY implementation every call site in the repo depends on, so no
script anywhere can produce this visual again -- see main()'s hard failure
below.

The reusable engine (Blender world/lighting/camera rig, the beveled-box
and extruded-3D-label helpers, the resumable frame-render loop) is kept
intact for a real semantic template to be built on top of: money flow,
transaction flow, bank/Fed/Treasury relationships, balance-sheet
animation, or a network/flow diagram. None of those is implemented yet.
A beat with no meaningful 3D template available must fail or be
reclassified to a different shot type -- never fall back to a generic
pillar.

    blender --background --python _motion_graphics_3d_script.py -- <args.json>
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _motion_graphics_3d_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def _material(name, color, roughness=0.35, metallic=0.35):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def _beveled_box(name, size, location, material, bevel=0.02, segments=4):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(scale=True)
    bev = obj.modifiers.new("bevel", type="BEVEL")
    bev.width = bevel
    bev.segments = segments
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.materials.append(material)
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
    bpy.ops.object.select_all(action='DESELECT')
    return obj


def build_3d_label(text, location, size, material, extrude=0.03):
    """Real DIMENSIONAL typography (extruded text object with bevel), the
    deliberate differentiator from the Sketch style's flat Grease-Pencil
    strokes -- this is genuinely 3D, catches real light/shadow."""
    bpy.ops.object.text_add(location=location, rotation=(math.radians(90), 0, 0))
    txt = bpy.context.active_object
    txt.name = text.replace("$", "usd_").replace(",", "").replace(" ", "_")
    txt.data.body = text
    txt.data.size = size
    txt.data.align_x = 'CENTER'
    txt.data.align_y = 'CENTER'
    txt.data.extrude = extrude
    txt.data.bevel_depth = extrude * 0.15
    txt.data.bevel_resolution = 2
    txt.data.materials.append(material)
    bpy.context.view_layer.update()
    return txt


def key(obj, frame, loc=None, scale=None, euler=None):
    bpy.context.scene.frame_set(frame)
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert(data_path="location", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)
    if euler is not None:
        obj.rotation_euler = euler
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def main() -> None:
    a = _args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    render = a["render"]
    scene.render.engine = render["engine"]
    scene.render.resolution_x = render["width"]
    scene.render.resolution_y = render["height"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_stamp = False
    if hasattr(scene, "eevee"):
        try:
            scene.eevee.taa_render_samples = render["samples"]
            scene.eevee.use_raytracing = render.get("raytracing", True)
        except AttributeError:
            pass

    world = bpy.data.worlds.new("mg_world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.03, 0.03, 0.05, 1.0)
    bg.inputs["Strength"].default_value = 0.3

    if "growth_stage" in a:
        raise SystemExit(
            "K70_MOTIONGRAPHICS3D_TEMPLATE_REMOVED: the generic growth_stage/"
            "milestone pillar-block template was removed from production use "
            "(confirmed meaningless output, e.g. shot H3 in "
            "k70_fed_money_creation_ep01_v3 -- an unlabeled beige/gold pillar). "
            "3D Motion Graphics requires a meaningful semantic template (money "
            "flow, transaction flow, bank/Fed/Treasury relationships, "
            "balance-sheet animation, network/flow diagram) -- none is "
            "implemented in this script yet. Reclassify this beat to a "
            "different shot type instead of calling this renderer with a "
            "growth_stage spec.")
    raise SystemExit(
        "K70_MOTIONGRAPHICS3D_NO_TEMPLATE: no semantic 3D-motion template is "
        "implemented in this script. Do not add a generic fallback -- "
        "reclassify this beat to REAL_FOOTAGE or ANIMATED_CHART, or implement "
        "a real semantic template (money flow / transaction flow / "
        "balance-sheet / network diagram) and dispatch to it explicitly here.")

    frame_range = a.get("frame_range")
    if frame_range:
        scene.frame_start, scene.frame_end = frame_range

    key_light = bpy.data.lights.new("mg_key", type="AREA")
    key_light.energy = 250
    key_light.size = 1.5
    key_obj = bpy.data.objects.new("mg_key", key_light)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = (1.2, -0.5, 2.2)
    key_obj.rotation_euler = (math.radians(45), 0, math.radians(35))

    rim_light = bpy.data.lights.new("mg_rim", type="AREA")
    rim_light.energy = 120
    rim_light.size = 1.0
    rim_obj = bpy.data.objects.new("mg_rim", rim_light)
    bpy.context.collection.objects.link(rim_obj)
    rim_obj.location = (-1.2, 2.2, 1.4)
    rim_obj.rotation_euler = (math.radians(70), 0, math.radians(-150))

    cam_data = bpy.data.cameras.new("mg_cam")
    cam_data.lens = a.get("lens", 50)
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = a.get("fstop", 2.2)
    cam_obj = bpy.data.objects.new("mg_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    focus_empty = bpy.data.objects.new("mg_focus", None)
    bpy.context.collection.objects.link(focus_empty)
    cam_data.dof.focus_object = focus_empty

    def aim(loc, look_at):
        cam_obj.location = loc
        cam_obj.rotation_euler = (Vector(look_at) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()

    for kf in a["camera_keyframes"]:
        scene.frame_set(kf["frame"])
        aim(kf["location"], kf["look_at"])
        cam_obj.keyframe_insert(data_path="location", frame=kf["frame"])
        cam_obj.keyframe_insert(data_path="rotation_euler", frame=kf["frame"])
        focus_empty.location = kf["look_at"]
        focus_empty.keyframe_insert(data_path="location", frame=kf["frame"])
    for fc in cam_obj.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.handle_left_type = 'AUTO_CLAMPED'
            kp.handle_right_type = 'AUTO_CLAMPED'

    out_dir = Path(render["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    n_frames = a.get("n_frames", 1)
    def _done(p: Path) -> bool:
        return p.exists() and p.stat().st_size > 1024
    fs, fe = scene.frame_start, scene.frame_end
    for i in range(n_frames):
        out_path = out_dir / f"frame_{i:03d}.png"
        if _done(out_path):
            print(f"  [resume] frame_{i:03d} already present, skipping")
            continue
        t = fs + (fe - fs) * i / max(n_frames - 1, 1)
        scene.frame_set(int(round(t)))
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
    print(f"K70_MOTIONGRAPHICS3D_RENDER_OK {out_dir} frames={n_frames}")


if __name__ == "__main__":
    main()
