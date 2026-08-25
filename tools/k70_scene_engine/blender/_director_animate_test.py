"""K70 AUTO SCENE DIRECTOR -- ONE 5-second animation test of the V5.2
winning still-image scene. Runs inside Blender.

Reuses, UNMODIFIED:
  - _director_build_and_check.py's build_ground_and_road/build_vehicles/
    build_buildings/build_skyline/build_props (static set-dressing --
    none of it needs per-frame animation)
  - _voxel_human_v3_script.py's build_voxel_human_v3/animate_idle/
    animate_walk (same rig/animation functions Day 06 and every prior
    K70 voxel benchmark used)
  - lighting_presets.setup_golden_hour_v2 (the V5.1/V5.2 lighting system)

Does NOT touch Thomas Rig, Day 06, or any other production video. This
is a bounded, one-off test of ONE clip from the already-approved
still-image winning scene -- not a new video pipeline.

    blender --background --python _director_animate_test.py -- <args.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
from mathutils import Vector

import _director_build_and_check as dbc
import _voxel_human_v3_script as vh
import lighting_presets as lp


def _args():
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def build_hero_animated(plan, total_frames):
    h = plan["hero"]
    root, joints = vh.build_voxel_human_v3(h["role"], root_location=tuple(h["location"]),
                                          root_rotation_z=vh.deg(h["rotation_z_deg"]))
    # Natural subtle stroll across the whole clip, not the single static
    # pose build_hero() bakes for the still-image check/render passes.
    cycle_len = max(8, total_frames // 3)
    vh.animate_walk(root, joints, start=0, length=cycle_len, n_cycles=3, stride_deg=14, forward_dist=0.22)
    return root


def build_npcs_animated(plan, total_frames):
    for i, npc in enumerate(plan.get("npcs", [])):
        root, joints = vh.build_voxel_human_v3(npc["role"], root_location=tuple(npc["location"]),
                                               root_rotation_z=vh.deg(npc["rotation_z_deg"]))
        if npc.get("animation") == "walk":
            cycle_len = max(8, total_frames // 3)
            vh.animate_walk(root, joints, start=0, length=cycle_len, n_cycles=3, stride_deg=12, forward_dist=0.14)
        else:
            vh.animate_idle(root, joints, start=0, length=total_frames)


def setup_camera_animated(plan, total_frames):
    cam = plan["camera"]
    cam_data = bpy.data.cameras.new("director_cam")
    cam_data.lens = cam["lens"]
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = cam["fstop"]
    cam_obj = bpy.data.objects.new("director_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    focus = bpy.data.objects.new("focus", None)
    bpy.context.collection.objects.link(focus)
    cam_data.dof.focus_object = focus
    focus.location = Vector(cam["focus_at"])

    loc = Vector(cam["location"])
    look_at = Vector(cam["look_at"])
    rot = (look_at - loc).to_track_quat("-Z", "Y").to_euler()
    fwd = Vector(cam["forward_dir"])

    # Subtle cinematic push-in: a small forward dolly over the whole
    # clip, rotation held constant (a straight push-in reads as
    # deliberate camera work; rotating too would risk looking like
    # accidental drift for a 5s test clip).
    dolly_end = loc + fwd * 0.22

    scene = bpy.context.scene
    scene.frame_set(0)
    cam_obj.location = loc
    cam_obj.rotation_euler = rot
    cam_obj.keyframe_insert(data_path="location", frame=0)
    cam_obj.keyframe_insert(data_path="rotation_euler", frame=0)
    scene.frame_set(total_frames - 1)
    cam_obj.location = dolly_end
    cam_obj.rotation_euler = rot
    cam_obj.keyframe_insert(data_path="location", frame=total_frames - 1)
    cam_obj.keyframe_insert(data_path="rotation_euler", frame=total_frames - 1)
    scene.frame_set(0)
    return cam_obj


def main():
    a = _args()
    plan = a["plan"]
    fps = a.get("fps", 24)
    duration_sec = a.get("duration_sec", 5)
    total_frames = int(round(fps * duration_sec))
    W, H = a.get("width", 1080), a.get("height", 1920)
    samples = a.get("samples", 24)
    output_dir = Path(a["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = W
    scene.render.resolution_y = H
    scene.render.image_settings.file_format = "PNG"
    scene.eevee.taa_render_samples = samples
    scene.eevee.use_raytracing = True
    scene.frame_start = 0
    scene.frame_end = total_frames - 1

    dbc.build_ground_and_road(plan)
    build_hero_animated(plan, total_frames)
    build_npcs_animated(plan, total_frames)
    dbc.build_vehicles(plan)
    dbc.build_buildings(plan)
    dbc.build_skyline(plan)
    dbc.build_props(plan)

    lighting_params = {k: v for k, v in plan["lighting"].items() if k != "mode"}
    if plan["lighting"].get("mode") == "golden_hour_v2":
        lp.setup_golden_hour_v2(plan["camera"]["forward_dir"], plan["camera"]["right_dir"], **lighting_params)
    else:
        lp.setup_block_world_v31(**lighting_params)

    if plan.get("practical_light"):
        loc = plan["practical_light"]["location"]
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        o = bpy.context.active_object
        o.scale = (0.16, 0.02, 0.10)
        bpy.ops.object.transform_apply(scale=True)
        mat = bpy.data.materials.new("practical_glow")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (1.0, 0.8, 0.45, 1.0)
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (1.0, 0.78, 0.4, 1.0)
            bsdf.inputs["Emission Strength"].default_value = a.get("practical_emission", 2.3)
        o.data.materials.append(mat)

    setup_camera_animated(plan, total_frames)
    bpy.context.view_layer.update()

    for f in range(total_frames):
        frame_path = output_dir / f"frame_{f:04d}.png"
        if frame_path.exists():
            continue
        scene.frame_set(f)
        scene.render.filepath = str(frame_path)
        bpy.ops.render.render(write_still=True)
        print(f"K70_ANIM_FRAME_OK {f}")

    print("K70_ANIM_RENDER_DONE")


if __name__ == "__main__":
    main()
