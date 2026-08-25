"""K70 VOXEL V3 -- premium block-world character. Runs inside Blender.

This is a NEW, separate script (does NOT modify or replace
_voxel_human_script.py, which Day 06 and every prior benchmark already
depend on and which is explicitly NOT to be re-rendered). Same rig
topology/animation philosophy as the original (Empty-driven joints, no
armature -- "Thomas Rig" is untouched, irrelevant here) -- the actual
V3 change is swapping flat-color beveled boxes for zero-bevel, flat-
shaded, K70-pixel-texture-atlas boxes via _k70_block_kit.textured_box().

Hair is no longer a separate floating primitive -- it's part of the head
texture atlas (front/back/side/top all painted in gen_k70_skin.py), so
the head is a single textured box.

    blender --background --python _voxel_human_v3_script.py -- <args.json>
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _k70_block_kit as bk

import bpy
from mathutils import Vector


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _voxel_human_v3_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


# Body proportions -- same values as _voxel_human_script.py (already
# reasonable; V3's job is textures/geometry-hardness, not a re-proportion).
H = 1.75
HEAD = 0.30
NECK = 0.04
TORSO_H = 0.55
TORSO_W = 0.42
TORSO_D = 0.22
HIP_W = 0.36
LEG_UP_H = 0.42
LEG_LO_H = 0.40
FOOT_H = 0.10
ARM_UP_H = 0.34
ARM_LO_H = 0.30
ARM_W = 0.13
HAND = 0.13

BEVEL_V3 = 0.0  # hard block edges -- the whole point of V3


def build_voxel_human_v3(role: str, root_location=(0, 0, 0), root_rotation_z=0.0):
    root = bpy.data.objects.new(f"{role}_root", None)
    root.empty_display_size = 0.05
    bpy.context.collection.objects.link(root)
    root.location = root_location
    root.rotation_euler = (0, 0, root_rotation_z)

    floor_z = root_location[2]
    feet_z = floor_z
    hip_z = feet_z + LEG_LO_H + LEG_UP_H
    shoulder_z = hip_z + TORSO_H
    head_center_z = shoulder_z + NECK + HEAD / 2

    joints = {}

    torso = bk.textured_box(f"{role}_torso", (TORSO_W, TORSO_D, TORSO_H),
                            (0, 0, hip_z + TORSO_H / 2 - root_location[2]),
                            bk.char_tex(role, "torso"), bevel=BEVEL_V3)
    torso.parent = root

    neck_empty = bpy.data.objects.new(f"{role}_neck", None)
    bpy.context.collection.objects.link(neck_empty)
    neck_empty.parent = root
    neck_empty.location = (0, 0, shoulder_z - root_location[2])
    joints["head"] = neck_empty

    head = bk.textured_box(f"{role}_head", (HEAD, HEAD * 0.9, HEAD), (0, 0, NECK + HEAD / 2),
                           bk.char_tex(role, "head"), bevel=BEVEL_V3)
    head.parent = neck_empty

    # shoulders / arms
    for side, sx in (("L", -1), ("R", 1)):
        sh_empty = bpy.data.objects.new(f"{role}_shoulder_{side}", None)
        bpy.context.collection.objects.link(sh_empty)
        sh_empty.parent = root
        sh_empty.location = (sx * (TORSO_W / 2 + ARM_W / 2 * 0.6), 0, shoulder_z - root_location[2] - 0.03)
        joints[f"shoulder_{side}"] = sh_empty

        upper_arm = bk.textured_box(f"{role}_upperarm_{side}", (ARM_W, ARM_W, ARM_UP_H), (0, 0, -ARM_UP_H / 2),
                                    bk.char_tex(role, "arm"), bevel=BEVEL_V3)
        upper_arm.parent = sh_empty

        elbow_empty = bpy.data.objects.new(f"{role}_elbow_{side}", None)
        bpy.context.collection.objects.link(elbow_empty)
        elbow_empty.parent = sh_empty
        elbow_empty.location = (0, 0, -ARM_UP_H)
        joints[f"elbow_{side}"] = elbow_empty

        lower_arm = bk.textured_box(f"{role}_lowerarm_{side}", (ARM_W * 0.9, ARM_W * 0.9, ARM_LO_H), (0, 0, -ARM_LO_H / 2),
                                    bk.char_tex(role, "arm"), bevel=BEVEL_V3)
        lower_arm.parent = elbow_empty

        hand = bk.textured_box(f"{role}_hand_{side}", (HAND * 0.8, HAND * 0.6, HAND), (0, 0, -ARM_LO_H - HAND / 2),
                               bk.char_tex(role, "hand"), bevel=BEVEL_V3)
        hand.parent = elbow_empty

    # hips / legs
    for side, sx in (("L", -1), ("R", 1)):
        hip_empty = bpy.data.objects.new(f"{role}_hip_{side}", None)
        bpy.context.collection.objects.link(hip_empty)
        hip_empty.parent = root
        hip_empty.location = (sx * HIP_W / 2, 0, hip_z - root_location[2])
        joints[f"hip_{side}"] = hip_empty

        upper_leg = bk.textured_box(f"{role}_upperleg_{side}", (0.16, 0.17, LEG_UP_H), (0, 0, -LEG_UP_H / 2),
                                    bk.char_tex(role, "leg"), bevel=BEVEL_V3)
        upper_leg.parent = hip_empty

        knee_empty = bpy.data.objects.new(f"{role}_knee_{side}", None)
        bpy.context.collection.objects.link(knee_empty)
        knee_empty.parent = hip_empty
        knee_empty.location = (0, 0, -LEG_UP_H)
        joints[f"knee_{side}"] = knee_empty

        lower_leg = bk.textured_box(f"{role}_lowerleg_{side}", (0.14, 0.15, LEG_LO_H), (0, 0, -LEG_LO_H / 2),
                                    bk.char_tex(role, "leg"), bevel=BEVEL_V3)
        lower_leg.parent = knee_empty

        foot = bk.textured_box(f"{role}_foot_{side}", (0.16, 0.26, FOOT_H), (0, 0.05, -LEG_LO_H - FOOT_H / 2),
                               bk.char_tex(role, "foot"), bevel=BEVEL_V3)
        foot.parent = knee_empty

    joints["root"] = root
    return root, joints


def deg(x):
    return math.radians(x)


def key(obj, frame, euler=None, loc=None, scale=None):
    bpy.context.scene.frame_set(frame)
    if euler is not None:
        obj.rotation_euler = euler
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert(data_path="location", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)


def animate_idle(root, joints, start=0, length=48):
    for f, sway in ((start, 0.0), (start + length // 2, 3.0), (start + length, 0.0)):
        key(root, f, euler=(0, 0, root.rotation_euler[2] + deg(sway * 0.3)))
    for f, tilt in ((start, 0.0), (start + length // 2, -3.0), (start + length, 0.0)):
        key(joints["head"], f, euler=(0, deg(tilt * 0.4), deg(tilt)))
    for side, sgn in (("L", 1), ("R", -1)):
        for f, swing in ((start, 0.0), (start + length // 2, sgn * 4.0), (start + length, 0.0)):
            key(joints[f"shoulder_{side}"], f, euler=(deg(swing * 0.5), 0, 0))


def animate_walk(root, joints, start=0, length=24, n_cycles=3, stride_deg=32, forward_dist=0.0):
    base = Vector(root.location)
    for c in range(n_cycles + 1):
        f = start + c * length
        t = c / max(n_cycles, 1)
        loc = base + Vector((0, forward_dist * t, 0))
        bob = abs(math.sin(c * math.pi)) * 0.015
        key(root, f, loc=(loc.x, loc.y, loc.z + bob))
    half = length // 2
    for side, phase in (("L", 0), ("R", half)):
        for c in range(n_cycles + 1):
            base_f = start + c * length
            key(joints[f"hip_{side}"], base_f + phase, euler=(deg(stride_deg), 0, 0))
            key(joints[f"hip_{side}"], base_f + phase + half, euler=(deg(-stride_deg), 0, 0))
            key(joints[f"knee_{side}"], base_f + phase, euler=(deg(8), 0, 0))
            key(joints[f"knee_{side}"], base_f + phase + half // 2, euler=(deg(-45), 0, 0))
            key(joints[f"knee_{side}"], base_f + phase + half, euler=(deg(8), 0, 0))
        for c in range(n_cycles + 1):
            base_f = start + c * length
            key(joints[f"shoulder_{side}"], base_f + phase, euler=(deg(-stride_deg * 0.6), 0, 0))
            key(joints[f"shoulder_{side}"], base_f + phase + half, euler=(deg(stride_deg * 0.6), 0, 0))


def animate_point_present(root, joints, start=0, length=60):
    for f, e in ((start, (0, 0, 0)), (start + int(length * 0.3), (deg(-70), deg(10), deg(-15))),
                 (start + int(length * 0.7), (deg(-75), deg(-5), deg(-10))), (start + length, (0, 0, 0))):
        key(joints["shoulder_R"], f, euler=e)
    for f, e in ((start, (0, 0, 0)), (start + int(length * 0.3), (deg(-20), 0, 0)),
                 (start + int(length * 0.7), (deg(-15), 0, 0)), (start + length, (0, 0, 0))):
        key(joints["elbow_R"], f, euler=e)
    for f, tilt in ((start, 0.0), (start + int(length * 0.4), -4.0), (start + length, 0.0)):
        key(joints["head"], f, euler=(0, 0, deg(tilt)))


def animate_sit(root, joints, start=0, length=40, seat_height=0.46):
    base = Vector(root.location)
    drop = max(0.0, (LEG_LO_H + LEG_UP_H) - seat_height)
    for f, t in ((start, 0.0), (start + length, 1.0)):
        loc = base - Vector((0, 0, drop * t))
        key(root, f, loc=(loc.x, loc.y, loc.z))
    for side in ("L", "R"):
        for f, e in ((start, (0, 0, 0)), (start + length, (deg(-95), 0, 0))):
            key(joints[f"hip_{side}"], f, euler=e)
        for f, e in ((start, (0, 0, 0)), (start + length, (deg(100), 0, 0))):
            key(joints[f"knee_{side}"], f, euler=e)
    for f, tilt in ((start, 0.0), (start + length, -2.0)):
        key(joints["head"], f, euler=(0, deg(tilt * 0.3), deg(tilt)))


def animate_sit_point(root, joints, length=48, **_):
    animate_sit(root, joints, start=0, length=length)
    animate_point_present(root, joints, start=int(length * 0.35), length=int(length * 0.65))


ANIMATIONS = {"idle": animate_idle, "walk": animate_walk, "point": animate_point_present,
             "sit": animate_sit, "sit_point": animate_sit_point}


def main() -> None:
    a = _args()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    render = a["render"]
    scene = bpy.context.scene
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

    characters = {}
    for spec in a.get("characters", []):
        root, joints = build_voxel_human_v3(spec["role"], root_location=tuple(spec["location"]),
                                            root_rotation_z=deg(spec.get("rotation_z_deg", 0)))
        characters[spec["role"]] = (root, joints)
        anim = spec.get("animation")
        if anim:
            ANIMATIONS[anim["type"]](root, joints, **anim.get("params", {}))

    frame_range = a.get("frame_range")
    if frame_range:
        scene.frame_start, scene.frame_end = frame_range

    # Environment: built entirely from the block kit. `env_pieces` is
    # generic -- each entry names any _k70_block_kit function (simple
    # boxes or composite builders like build_house/build_streetlamp/
    # build_desk/etc.) and its kwargs, so the benchmark script can dress
    # each shot declaratively without this file needing per-prop code.
    for spec in a.get("env_pieces", []):
        fn = getattr(bk, spec["fn"])
        fn(**spec["kwargs"])
    for spec in a.get("env_boxes", []):  # back-compat simple form
        bk.simple_textured_box(spec["name"], tuple(spec["size"]), tuple(spec["location"]),
                               bk.env_tex(spec["material"]), bevel=spec.get("bevel", 0.0))

    lighting = a.get("lighting", {})
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if lighting.get("mode") == "block_world_v31":
        import lighting_presets as lp
        kwargs = {k: v for k, v in lighting.items() if k != "mode"}
        lp.setup_block_world_v31(**kwargs)
    elif lighting.get("mode") == "block_world_v3":
        import lighting_presets as lp
        lp.setup_block_world_v3(
            sun_rotation=lighting.get("sun_rotation", [0.9, 0, 0.6]),
            sun_energy=lighting.get("sun_energy", 4.0),
            ambient_preset=lighting.get("ambient_preset", "exterior_day"),
            ambient_strength=lighting.get("ambient_strength", 0.18),
            sky_color=lighting.get("sky_color", [0.55, 0.68, 0.85]),
        )
    else:
        from lighting_presets import apply_hdri_world
        apply_hdri_world(a.get("lighting_preset", "exterior_day"), rotation_z=deg(a.get("hdri_rotation_deg", 0)),
                         strength_override=a.get("hdri_strength"))

    cam_data = bpy.data.cameras.new("k70_cam")
    cam_data.lens = a.get("lens", 50)
    cam_data.dof.use_dof = a.get("dof", False)
    if a.get("dof"):
        cam_data.dof.aperture_fstop = a.get("fstop", 2.0)
    cam_obj = bpy.data.objects.new("k70_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)

    def aim_camera(location, look_at_pt):
        cam_obj.location = location
        cam_obj.rotation_euler = (Vector(look_at_pt) - Vector(location)).to_track_quat("-Z", "Y").to_euler()

    camera_keyframes = a.get("camera_keyframes")
    focus_empty = None
    if a.get("dof"):
        focus_empty = bpy.data.objects.new("focus", None)
        bpy.context.collection.objects.link(focus_empty)
        cam_data.dof.focus_object = focus_empty

    if camera_keyframes:
        for kf in camera_keyframes:
            scene.frame_set(kf["frame"])
            aim_camera(kf["location"], kf["look_at"])
            cam_obj.keyframe_insert(data_path="location", frame=kf["frame"])
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=kf["frame"])
            if focus_empty is not None:
                focus_empty.location = kf["look_at"]
                focus_empty.keyframe_insert(data_path="location", frame=kf["frame"])
        for fc in cam_obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'BEZIER'
                kp.handle_left_type = 'AUTO_CLAMPED'
                kp.handle_right_type = 'AUTO_CLAMPED'
        if focus_empty is not None and focus_empty.animation_data:
            for fc in focus_empty.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = 'BEZIER'
    else:
        aim_camera(tuple(a["camera"]["location"]), tuple(a["camera"]["look_at"]))
        if focus_empty is not None:
            focus_empty.location = tuple(a["camera"]["look_at"])
    bpy.context.scene.camera = cam_obj

    out_dir = Path(render["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    n_frames = a.get("n_frames", 1)

    def _done(p: Path) -> bool:
        return p.exists() and p.stat().st_size > 1024

    if n_frames == 1:
        out_path = out_dir / "frame_000.png"
        if not _done(out_path):
            scene.render.filepath = str(out_path)
            bpy.ops.render.render(write_still=True)
    else:
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
    print(f"K70_VOXEL_V3_RENDER_OK {out_dir} frames={n_frames}")


if __name__ == "__main__":
    main()
