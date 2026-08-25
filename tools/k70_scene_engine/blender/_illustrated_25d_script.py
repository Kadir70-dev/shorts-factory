"""K70 Visual Engine V2 -- Style 5: 2.5D Illustrated Cinematic. Runs
inside Blender.

Integration note: Krita (paint layers) + Storytools (Blender addon,
GPL-3.0, license-clear, inherits the same --background automation as
every other addon evaluated) are the brief's named tools. Storytools
itself is a camera/storyboard-rigging convenience addon, not a rendering
engine -- the actual foreground/character/midground/background parallax
technique it would help set up is the SAME direct camera-keyframe
approach already proven for the Voxel style's street shots and the
Collage style's dolly, so it's used directly here rather than adding an
addon dependency for a technique already in hand. Krita's paint-layer
authoring is replaced with Blender's own lit (non-flat) Principled BSDF
shapes -- the key differentiator from the flat-emission Vector style:
this style uses REAL soft-shaded lighting + DOF for a painterly,
dimensional feel despite flat cutout geometry.

    blender --background --python _illustrated_25d_script.py -- <args.json>
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
        raise SystemExit("usage: blender --background --python _illustrated_25d_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def soft_material(name, color, roughness=0.65):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def flat_plane(name, size, location, color, rotation=(0.0, 0.0, 0.0), roughness=0.65, bevel=0.03):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_plane_add(size=1, location=location,
                                     rotation=(math.radians(90) + rotation[0], rotation[1], rotation[2]))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0], size[1], 1)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if bevel:
        bev = obj.modifiers.new("bevel", type="BEVEL")
        bev.width = min(size) * bevel
        bev.segments = 6
        bpy.ops.object.modifier_apply(modifier="bevel")
    obj.data.materials.append(soft_material(f"{name}_mat", color, roughness))
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
    return obj


def textured_plane(name, image_path, size, location):
    """Place a real Krita-exported RGBA artwork layer in the depth stack."""
    obj = flat_plane(name, size, location, (1, 1, 1), bevel=0, roughness=1.0)
    mat = obj.data.materials[0]
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(image_path), check_existing=True)
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    mat.surface_render_method = 'DITHERED'
    return obj


def key(obj, frame, loc=None, euler=None, scale=None):
    bpy.context.scene.frame_set(frame)
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert(data_path="location", frame=frame)
    if euler is not None:
        obj.rotation_euler = euler
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)


def build_character(root_location=(0, 0, 0)):
    """A simplified illustrated-style silhouette figure -- same layered-
    shape approach as the Vector style's character, but with fewer, softer
    color blocks (illustrated silhouette, not a flat vector icon), lit by
    real scene lighting instead of flat emission."""
    x, y, z = root_location
    # Locked to the K70 canonical John identity (same skin/shirt values as
    # ROLE_STYLES["john"] in _voxel_human_script.py) for cross-style
    # character continuity -- see K70_VISUAL_ENGINE_V2_REPORT.md.
    JOHN_SHIRT, JOHN_SKIN = (0.18, 0.35, 0.62), (0.82, 0.62, 0.48)
    JOHN_HAIR = (0.25, 0.16, 0.10)
    torso = flat_plane("il_torso", (0.5, 0.75), (x, y, z + 0.55), JOHN_SHIRT, bevel=0.05)
    head = flat_plane("il_head", (0.36, 0.36), (x, y - 0.01, z + 1.18), JOHN_SKIN, bevel=0.45)
    hair = flat_plane("il_hair", (0.40, 0.16), (x, y - 0.015, z + 1.35), JOHN_HAIR, bevel=0.3)
    arm = flat_plane("il_arm", (0.14, 0.5), (x + 0.32, y - 0.005, z + 0.75), JOHN_SKIN, bevel=0.2)
    bpy.context.scene.cursor.location = (x + 0.32, y - 0.005, z + 1.0)
    for o in (arm,):
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    return {"torso": torso, "head": head, "arm": arm}


def animate_character(parts, start=10, length=45):
    arm = parts["arm"]
    for f, ang in ((start, 8.0), (start + int(length * 0.35), -60.0),
                  (start + int(length * 0.7), -45.0), (start + length, 8.0)):
        key(arm, f, euler=(math.radians(ang), 0, 0))
    head = parts["head"]
    for f, off in ((start, 0.0), (start + length // 2, 0.03), (start + length, 0.0)):
        key(head, f, loc=(head.location.x, head.location.y, head.location.z + off))


def build_depth_layers(a):
    """Foreground / character (midground) / background as distinct Z-depth
    planes -- the brief's explicit requirement for this style."""
    layers = {}
    layers["sky"] = flat_plane("bg_sky", (10, 6), (0, 6.0, 3.2), (0.55, 0.62, 0.70), bevel=0, roughness=0.9)
    if a.get("krita_asset"):
        layers["krita_atmosphere"] = textured_plane(
            "krita_painted_atmosphere", a["krita_asset"], (8.8, 4.95), (0, 5.4, 2.7)
        )
    for i in range(4):
        h = 1.2 + (i % 3) * 0.5
        layers[f"bg_bld_{i}"] = flat_plane(f"bg_bld_{i}", (1.1, h), (-2.4 + i * 1.5, 4.6, h / 2),
                                           (0.42 + i * 0.03, 0.46, 0.55), bevel=0.02, roughness=0.85)
    layers["mid_ground"] = flat_plane("mid_ground", (8, 2.0), (0, 2.4, 0.0), (0.30, 0.42, 0.30),
                                      rotation=(math.radians(-90), 0, 0), bevel=0, roughness=0.9)
    layers["fg_frame_l"] = flat_plane("fg_frame_l", (0.9, 3.2), (-2.2, -1.0, 1.4), (0.08, 0.07, 0.09), bevel=0)
    layers["fg_plant"] = flat_plane("fg_plant", (0.7, 1.6), (1.9, -0.8, 0.75), (0.14, 0.32, 0.16), bevel=0.08)
    return layers


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

    world = bpy.data.worlds.new("il_world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.62, 0.68, 0.76, 1.0)
    bg.inputs["Strength"].default_value = 0.9

    build_depth_layers(a)
    parts = build_character(root_location=(0, 0.4, 0))
    animate_character(parts, start=a.get("gesture_start", 10), length=a.get("gesture_length", 45))

    frame_range = a.get("frame_range")
    if frame_range:
        scene.frame_start, scene.frame_end = frame_range

    sun = bpy.data.lights.new("il_sun", type="SUN")
    sun.energy = a.get("sun_energy", 2.2)
    sun.angle = 0.15
    sun_obj = bpy.data.objects.new("il_sun", sun)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = (math.radians(55), 0, math.radians(35))

    fill = bpy.data.lights.new("il_fill", type="AREA")
    fill.energy = 60
    fill.size = 4
    fill_obj = bpy.data.objects.new("il_fill", fill)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = (-2, -1.5, 2.5)
    fill_obj.rotation_euler = (math.radians(60), 0, math.radians(-30))

    cam_data = bpy.data.cameras.new("il_cam")
    cam_data.lens = a.get("lens", 42)
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = a.get("fstop", 2.0)
    cam_obj = bpy.data.objects.new("il_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    focus_empty = bpy.data.objects.new("il_focus", None)
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
    fs, fe = scene.frame_start, scene.frame_end
    for i in range(n_frames):
        t = fs + (fe - fs) * i / max(n_frames - 1, 1)
        scene.frame_set(int(round(t)))
        scene.render.filepath = str(out_dir / f"frame_{i:03d}.png")
        bpy.ops.render.render(write_still=True)
    print(f"K70_ILLUSTRATED25D_RENDER_OK {out_dir} frames={n_frames}")


if __name__ == "__main__":
    main()
