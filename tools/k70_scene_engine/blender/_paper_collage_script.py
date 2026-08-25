"""K70 Visual Engine V2 -- Style 3: Paper-Cut / Editorial Collage. Runs
inside Blender.

Integration note: Krita (GPL-3.0, license-clear) is the brief's named
candidate for authoring the paper-texture layer art, but Krita is GUI-
first with no `--background`-equivalent render loop (flagged as a real
automation risk in V2_LICENSE_MANIFEST.md before this style was ever
attempted). Per this session's explicit "the STYLE must work, a
particular repository does not have to," this builds the paper-cut look
directly in Blender: flat cutout shapes (money, documents, buildings,
map) with a real paper-grain material (noise-driven roughness/bump, same
technique proven for the Clay style, tuned to read as paper not clay),
placed at distinct Z-depths, with a perspective camera dolly THROUGH the
layers for genuine parallax -- the actual differentiator from the flat
orthographic Vector style.

    blender --background --python _paper_collage_script.py -- <args.json>
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
        raise SystemExit("usage: blender --background --python _paper_collage_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def paper_material(name, color, roughness=0.88, grain_scale=90.0, grain_strength=0.012):
    """Flat-lit paper look: mostly-diffuse Principled BSDF (very low
    specular via high roughness) + a fine noise bump for paper grain --
    same technique family as the Clay style's material but tuned for a
    much finer, flatter grain (paper, not hand-worked clay)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.0
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = grain_scale
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.55
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = grain_strength
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def cutout(name, size, location, color, rotation=(0.0, 0.0, 0.0), corner_bevel=0.02):
    """A single flat paper-cutout shape on the XZ plane (Y = depth). Real
    paper cutouts have slightly irregular, hand-cut edges -- approximated
    here with a small bevel (crisp die-cut look is the OTHER valid paper
    aesthetic; a future pass could add per-vertex jitter for a rougher
    hand-torn look)."""
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
    bev = obj.modifiers.new("bevel", type="BEVEL")
    bev.width = min(size) * corner_bevel
    bev.segments = 2
    bpy.ops.object.modifier_apply(modifier="bevel")
    obj.data.materials.append(paper_material(f"{name}_mat", color))
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
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


def build_scene(a):
    """Layered financial-documentary paper collage: a background 'map'
    card, a midground 'newspaper' masthead + a 'document' (loan/contract),
    a 'house' silhouette cutout, and foreground 'money' bills -- the
    brief's own required element list, each at a distinct Y depth."""
    objs = {}
    objs["map"] = cutout("map", (3.0, 1.9), (0, 3.2, 1.0), (0.82, 0.78, 0.66), corner_bevel=0.01)
    objs["news"] = cutout("news", (1.6, 1.1), (-0.9, 2.4, 1.15), (0.92, 0.90, 0.84))
    objs["news_headline"] = cutout("news_headline", (1.3, 0.18), (-0.9, 2.35, 1.5), (0.15, 0.15, 0.16))
    objs["doc"] = cutout("doc", (1.1, 1.4), (0.9, 1.6, 0.85), (0.96, 0.95, 0.90))
    objs["doc_line1"] = cutout("doc_line1", (0.8, 0.05), (0.9, 1.55, 1.1), (0.35, 0.35, 0.38))
    objs["doc_line2"] = cutout("doc_line2", (0.8, 0.05), (0.9, 1.55, 0.95), (0.35, 0.35, 0.38))
    objs["house"] = cutout("house", (1.3, 1.3), (-0.7, 0.9, 0.75), (0.55, 0.30, 0.24),
                           rotation=(0, 0, math.radians(-4)))
    for i in range(3):
        objs[f"bill_{i}"] = cutout(f"bill_{i}", (0.55, 0.28), (0.3 + i * 0.28, 0.15, 0.35 - i * 0.02),
                                   (0.20, 0.48, 0.30), rotation=(0, 0, math.radians(-8 + i * 6)))
    return objs


def animate_scene(objs, a):
    stage = a.get("stage", {})
    f_bills = stage.get("f_bills", 10)
    f_doc = stage.get("f_doc", 24)
    f_house = stage.get("f_house", 40)
    for i in range(3):
        b = objs[f"bill_{i}"]
        base_loc = tuple(b.location)
        key(b, max(0, f_bills - 6 + i * 3), loc=(base_loc[0], base_loc[1] - 0.4, base_loc[2] - 0.5), scale=(0.6, 0.6, 0.6))
        key(b, f_bills + i * 3, loc=base_loc, scale=(1, 1, 1))
    doc = objs["doc"]
    key(doc, max(0, f_doc - 8), scale=(0.85, 0.85, 0.02))
    key(doc, f_doc, scale=(1, 1, 1))
    house = objs["house"]
    base = tuple(house.location)
    key(house, max(0, f_house - 10), loc=(base[0], base[1] + 0.3, base[2] - 0.15), scale=(0.9, 0.9, 0.9))
    key(house, f_house, loc=base, scale=(1, 1, 1))


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

    world = bpy.data.worlds.new("paper_world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.12, 0.11, 0.10, 1.0)
    bg.inputs["Strength"].default_value = 0.5

    objs = build_scene(a)
    animate_scene(objs, a)

    frame_range = a.get("frame_range")
    if frame_range:
        scene.frame_start, scene.frame_end = frame_range

    key_light = bpy.data.lights.new("paper_key", type="AREA")
    key_light.energy = a.get("key_energy", 120)
    key_light.size = 2.0
    key_obj = bpy.data.objects.new("paper_key", key_light)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = (1.5, 0.5, 2.6)
    key_obj.rotation_euler = (math.radians(35), 0, math.radians(35))

    fill_light = bpy.data.lights.new("paper_fill", type="AREA")
    fill_light.energy = a.get("fill_energy", 30)
    fill_light.size = 3.0
    fill_obj = bpy.data.objects.new("paper_fill", fill_light)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = (-1.5, -1.0, 1.8)
    fill_obj.rotation_euler = (math.radians(60), 0, math.radians(-40))

    cam_data = bpy.data.cameras.new("paper_cam")
    cam_data.lens = a.get("lens", 45)
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = a.get("fstop", 2.2)
    cam_obj = bpy.data.objects.new("paper_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    focus_empty = bpy.data.objects.new("paper_focus", None)
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
    print(f"K70_PAPER_COLLAGE_RENDER_OK {out_dir} frames={n_frames}")


if __name__ == "__main__":
    main()
