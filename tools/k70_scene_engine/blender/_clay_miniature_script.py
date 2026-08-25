"""K70 Visual Engine V2 -- Style 4: Clay / Miniature 3D. Runs inside Blender.

Pure Blender (no new external repository required -- the brief's own
Stop-Motion addon is evaluated separately and only adopted if it improves
on a plain scripted approach without destabilizing automation; this script
deliberately does NOT depend on it, so it stands on its own).

Reuses the beveled-box construction technique proven in
_voxel_human_script.py (same _beveled_box helper, same direct-object-
keyframe animation philosophy) with a NEW clay-look material system:
matte/rough Principled BSDF + a bump-mapped noise texture for imperfect,
hand-worked surfaces (not shiny generic CGI), plus miniature/macro-feeling
lighting (small, close, soft area lights + shallow DOF) instead of the
architectural HDRI lighting used for the voxel cinematic style.

    blender --background --python _clay_miniature_script.py -- <args.json>
"""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _clay_miniature_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def clay_material(name, color, roughness=0.75, bump_strength=0.06):
    """The core of the 'clay' look: matte diffuse (no specular pop), a
    noise-driven bump for hand-worked/imperfect surface variation (real
    clay is never perfectly smooth), and zero metallic -- everything a
    shiny-generic-CGI material is not."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.0
    if "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = 0.15  # subtle soft-surface sheen, not gloss

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 28.0
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.65
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _beveled_box(name, size, location, material, bevel=0.03, segments=4):
    """Same technique as _voxel_human_script.py's _beveled_box (deselect ->
    create -> scale directly since primitive_cube_add(size=1) is already a
    unit cube -> live bevel modifier), with more bevel segments for a
    softer, more hand-formed silhouette than the voxel style's sharper
    premium-blocky look."""
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
    bpy.ops.object.select_all(action='DESELECT')
    return obj


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


def build_savings_growth(stage, base_mat, coin_mat):
    """The brief's own test metaphor: 'small savings stack -> grows ->
    produces additional money blocks.' Built entirely from clay-material
    beveled boxes, staged on a small clay 'table' base so the miniature/
    macro framing has a clear foreground surface.

    Real defect found and fixed during testing: an earlier version dropped
    each not-yet-arrived block in from high above its final resting spot,
    keyed to hold there via constant extrapolation -- since every future
    block's "waiting" position is simultaneously visible for most of the
    timeline, this read as a broken staircase of floating slabs, not a
    clay stop-motion arrival. Fixed the same way the voxel finance shot's
    savings pillar was proven to work: pop-in-place via a scale key (from
    squashed/flat to full size) at each block's OWN final resting
    location -- nothing is ever visible anywhere but its true position."""
    table = _beveled_box("clay_table", (1.6, 1.2, 0.12), (0, 0, 0.06), base_mat, bevel=0.04, segments=6)

    blocks = []
    f_each = stage.get("f_each", 12)
    n_blocks = stage.get("n_blocks", 5)
    for i in range(n_blocks):
        h = 0.09
        z = 0.12 + h / 2 + i * h
        b = _beveled_box(f"clay_block_{i}", (0.30, 0.20, h), (0, 0, z), coin_mat, bevel=0.02, segments=4)
        f_appear = i * f_each
        # squash-and-pop arrival AT the true resting position -- the
        # "stop-motion"/hand-placed feeling via an overshoot-then-settle
        # scale curve, never a translated drop from elsewhere.
        key(b, max(0, f_appear - 4), scale=(1.2, 1.2, 0.05))
        key(b, f_appear, scale=(1.0, 1.0, 1.0))
        blocks.append(b)
    return table, blocks


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

    backdrop_mat = clay_material("clay_backdrop", (0.20, 0.19, 0.22), roughness=0.9, bump_strength=0.03)
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.data.materials.append(backdrop_mat)

    table_mat = clay_material("clay_table_mat", (0.55, 0.42, 0.30), roughness=0.8)
    coin_mat = clay_material("clay_coin_mat", (0.75, 0.58, 0.20), roughness=0.55, bump_strength=0.08)

    stage = a.get("growth_stage", {})
    build_savings_growth(stage, table_mat, coin_mat)

    frame_range = a.get("frame_range")
    if frame_range:
        scene.frame_start, scene.frame_end = frame_range

    # Miniature/macro lighting: small, CLOSE, soft area lights (not a big
    # HDRI dome) -- this is what reads as "tabletop miniature photography"
    # rather than architectural scale.
    key_light = bpy.data.lights.new("clay_key", type="AREA")
    key_light.energy = a.get("key_energy", 60)
    key_light.size = 0.5
    key_obj = bpy.data.objects.new("clay_key", key_light)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = (0.9, -0.9, 1.1)
    key_obj.rotation_euler = (0.9, 0, 0.7)

    fill_light = bpy.data.lights.new("clay_fill", type="AREA")
    fill_light.energy = a.get("fill_energy", 15)
    fill_light.size = 0.8
    fill_obj = bpy.data.objects.new("clay_fill", fill_light)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = (-1.0, -0.5, 0.7)
    fill_obj.rotation_euler = (1.1, 0, -0.6)

    world = bpy.data.worlds.new("clay_world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.03, 0.03, 0.035, 1.0)
    bg.inputs["Strength"].default_value = 0.4

    cam_data = bpy.data.cameras.new("clay_cam")
    cam_data.lens = a.get("lens", 85)  # longer macro-feeling lens
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = a.get("fstop", 1.4)  # shallow -- macro/miniature signature
    cam_obj = bpy.data.objects.new("clay_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    focus_empty = bpy.data.objects.new("clay_focus", None)
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
    print(f"K70_CLAY_MINIATURE_RENDER_OK {out_dir} frames={n_frames}")


if __name__ == "__main__":
    main()
