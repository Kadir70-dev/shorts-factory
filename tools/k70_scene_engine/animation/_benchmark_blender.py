"""Runs inside Blender; isolated low-cost animation benchmarks only."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BLENDER_DIR = HERE.parent / "blender"
sys.path.insert(0, str(BLENDER_DIR))
sys.path.insert(0, str(HERE))


def args():
    i = sys.argv.index("--")
    return json.loads(Path(sys.argv[i + 1]).read_text(encoding="utf-8"))


def clean():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.actions, bpy.data.armatures, bpy.data.meshes, bpy.data.materials,
                  bpy.data.cameras, bpy.data.lights):
        if block is not bpy.data.actions:
            pass


def material(name, color):
    m = bpy.data.materials.new(name); m.diffuse_color = (*color, 1)
    return m


def stage():
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
    bpy.context.object.data.materials.append(material("ground", (.08, .09, .11)))
    bpy.ops.object.light_add(type="AREA", location=(3, -4, 6)); bpy.context.object.data.energy = 900
    bpy.context.object.data.shape = "DISK"; bpy.context.object.data.size = 5
    bpy.ops.object.light_add(type="AREA", location=(-4, 1, 3)); bpy.context.object.data.energy = 500
    bpy.context.object.data.color = (.3, .5, 1.0); bpy.context.object.data.size = 4
    bpy.ops.object.camera_add(location=(3.0, -5.0, 2.35)); cam = bpy.context.object
    direction = Vector((0, 0, 1.15)) - cam.location; cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 62; bpy.context.scene.camera = cam


def configure(out: Path, end: int):
    s = bpy.context.scene; s.frame_start = 1; s.frame_end = end; s.render.fps = 12
    s.render.engine = "BLENDER_EEVEE_NEXT"; s.render.resolution_x = 480; s.render.resolution_y = 270
    s.render.resolution_percentage = 100; s.render.image_settings.file_format = "PNG"
    s.render.filepath = str(out / "frame_")
    s.render.film_transparent = False; s.world.color = (.015, .02, .03)
    out.mkdir(parents=True, exist_ok=True)


def normalize_import(objects):
    meshes = [o for o in objects if o.type == "MESH"]
    coords = [o.matrix_world @ Vector(corner) for o in meshes for corner in o.bound_box]
    lo = Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
    hi = Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
    scale = 1.8 / max(hi.z - lo.z, 1e-6)
    anchor = bpy.data.objects.new("K70_Humanoid_Anchor", None); bpy.context.collection.objects.link(anchor)
    anchor.scale = (scale,) * 3; anchor.location = (-(lo.x + hi.x) * .5 * scale,
                                                    -(lo.y + hi.y) * .5 * scale, -lo.z * scale)
    imported = set(objects)
    for o in objects:
        if o.parent not in imported: o.parent = anchor
    return anchor


def add_strip(armature, action_name, start, end):
    action = bpy.data.actions.get(action_name)
    if not action: raise RuntimeError(f"missing Mesh2Motion action {action_name}")
    armature.animation_data_create(); track = armature.animation_data.nla_tracks.new()
    track.name = f"K70_{action_name}_{start}"; strip = track.strips.new(track.name, start, action)
    strip.action_frame_start, strip.action_frame_end = action.frame_range
    strip.frame_end = end; strip.extrapolation = "NOTHING"; strip.blend_type = "REPLACE"


def bone(arm, *names):
    return next((arm.pose.bones.get(name) for name in names if arm.pose.bones.get(name)), None)


def joint_world(arm, pose_bone):
    return arm.matrix_world @ pose_bone.head


def bake_foot_lock(anchor, arm, start, end):
    """World-space plant detection and anchor correction, derived from evaluated feet."""
    feet = [bone(arm, "foot_l"), bone(arm, "foot_r")]
    feet = [f for f in feet if f]
    target = None; planted_name = None; samples = []
    for frame in range(start, end + 1):
        bpy.context.scene.frame_set(frame); bpy.context.view_layer.update()
        points = [(f.name, joint_world(arm, f)) for f in feet]
        planted = min(points, key=lambda row: row[1].z)
        if planted_name != planted[0]:
            planted_name, target = planted[0], planted[1].copy()
        current = planted[1]
        anchor.location.x += target.x - current.x
        anchor.location.y += target.y - current.y
        # Ground is always derived from the lower evaluated foot.
        anchor.location.z += -min(p.z for _, p in points)
        anchor.keyframe_insert("location", frame=frame)
        bpy.context.view_layer.update()
        corrected = joint_world(arm, arm.pose.bones[planted_name])
        samples.append({"frame": frame, "planted": planted_name,
                        "x": corrected.x, "y": corrected.y, "z": corrected.z})
    return samples


def bake_chair_contact(anchor, arm, chair, start, hold_end, stand_end):
    pelvis = bone(arm, "pelvis", "hips")
    if not pelvis: raise RuntimeError("pelvis bone required for chair correction")
    top = max((chair.matrix_world @ Vector(c)).z for c in chair.bound_box)
    center = chair.matrix_world.translation.copy(); height = 1.8
    target = Vector((center.x, center.y - .10 * height, top + .08 * height))
    base = anchor.location.copy(); samples = []
    for frame in range(start, hold_end + 1):
        bpy.context.scene.frame_set(frame); bpy.context.view_layer.update()
        p = joint_world(arm, pelvis); weight = min(1.0, max(0.0, (frame-start) / 6.0))
        correction = (target - p) * weight; anchor.location += correction
        anchor.keyframe_insert("location", frame=frame); bpy.context.view_layer.update()
        p2 = joint_world(arm, pelvis); samples.append({"frame": frame, "distance": (p2-target).length})
    seated = anchor.location.copy()
    for frame in range(hold_end + 1, stand_end + 1):
        weight = (frame - hold_end) / max(1, stand_end - hold_end)
        anchor.location = seated.lerp(base, weight); anchor.keyframe_insert("location", frame=frame)
    return samples


def evaluated_qa(anchor, arm, frame_start, frame_end, foot_samples=None, chair_samples=None):
    feet = [bone(arm, "foot_l"), bone(arm, "foot_r")]; feet = [f for f in feet if f]
    ground_errors = []; extreme = 0; discontinuities = 0; previous_root = None
    for frame in range(frame_start, frame_end + 1):
        bpy.context.scene.frame_set(frame); bpy.context.view_layer.update()
        ground_errors.append(abs(min(joint_world(arm, f).z for f in feet)))
        for pb in arm.pose.bones:
            if pb.rotation_mode == "QUATERNION":
                angle = pb.rotation_quaternion.angle
            else: angle = max(abs(v) for v in pb.rotation_euler)
            extreme += angle > math.radians(165)
        root = anchor.matrix_world.translation.copy()
        if previous_root is not None: discontinuities += (root - previous_root).length > .55
        previous_root = root
    plant_velocities = []
    for a, b in zip(foot_samples or [], (foot_samples or [])[1:]):
        if a["planted"] == b["planted"]:
            plant_velocities.append(math.hypot(b["x"]-a["x"], b["y"]-a["y"]))
    return {"max_ground_error": max(ground_errors, default=0),
            "max_planted_foot_velocity": max(plant_velocities, default=0),
            "max_chair_contact_error": max((s["distance"] for s in chair_samples or []), default=0),
            "extreme_joint_rotations": extreme, "transition_discontinuities": discontinuities}


def humanoid(spec, kind):
    path = spec["mesh2motion_human"]
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=path)
    objects = [o for o in bpy.data.objects if o not in before]; anchor = normalize_import(objects)
    arm = next(o for o in objects if o.type == "ARMATURE")
    if kind == "A":
        actions = [("Idle_A_Armature", 1, 12), ("Walk_Formal_Armature", 13, 24),
                   ("Idle_A_Armature", 25, 36), ("Pistol_Shoot_Armature", 37, 48)]
        anchor.rotation_euler.z = 0; anchor.keyframe_insert("rotation_euler", frame=25)
        anchor.rotation_euler.z = math.radians(35); anchor.keyframe_insert("rotation_euler", frame=36)
    else:
        actions = [("Walk_Armature", 1, 12), ("Sitting_Enter_Armature", 13, 24),
                   ("Sitting_Talking_Armature", 25, 36), ("Sitting_Exit_Armature", 37, 48)]
        # A visible neutral chair makes sit/stand structurally and visually auditable.
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, .42)); seat = bpy.context.object
        seat.name = "K70_Benchmark_Chair_Seat"; seat.scale = (.58, .58, .12)
        seat.data.materials.append(material("chair", (.22, .15, .09)))
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, .30, .92)); back = bpy.context.object
        back.name = "K70_Benchmark_Chair_Back"; back.scale = (.58, .10, .9)
        back.data.materials.append(bpy.data.materials["chair"])
    for row in actions: add_strip(arm, *row)
    foot_samples = bake_foot_lock(anchor, arm, 13, 24) if kind == "A" else bake_foot_lock(anchor, arm, 1, 12)
    chair_samples = bake_chair_contact(anchor, arm, seat, 13, 36, 48) if kind == "C" else []
    qa = evaluated_qa(anchor, arm, 1, 48, foot_samples, chair_samples)
    return {"armature": arm.name, "actions": [a[0] for a in actions], "frames": 48, "qa": qa,
            "automatic_foot_lock": True, "automatic_chair_contact": kind == "C"}


def voxel():
    import _voxel_human_v3_script as v3
    root, joints = v3.build_voxel_human_v3("john", (0, 0, 0), 0)
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("john_")]
    pre = {o.name: hashlib.sha256(b"".join(float(x).hex().encode() for v in o.data.vertices for x in v.co)).hexdigest()
           for o in meshes}
    v3.animate_idle(root, joints, start=1, length=12)
    v3.animate_walk(root, joints, start=13, length=12, n_cycles=1, stride_deg=28, forward_dist=.45)
    root.rotation_euler.z = 0; root.keyframe_insert("rotation_euler", frame=25)
    root.rotation_euler.z = math.radians(35); root.keyframe_insert("rotation_euler", frame=36)
    v3.animate_point_present(root, joints, start=37, length=12)
    post = {o.name: hashlib.sha256(b"".join(float(x).hex().encode() for v in o.data.vertices for x in v.co)).hexdigest()
            for o in meshes}
    forbidden = [o.name for o in meshes if o.vertex_groups or any(m.type == "ARMATURE" for m in o.modifiers)]
    return {"frames": 49, "mesh_count": len(meshes), "vertex_hashes_unchanged": pre == post,
            "forbidden_deformers": forbidden, "rigid_geometry_preserved": pre == post and not forbidden,
            "actions": ["idle_neutral", "walk_normal", "turn_left", "point_screen"]}


def main():
    spec = args(); clean(); stage(); kind = spec["benchmark"]
    result = voxel() if kind == "B" else humanoid(spec, kind)
    configure(Path(spec["frames_dir"]), result["frames"])
    bpy.ops.wm.save_as_mainfile(filepath=spec["blend_path"])
    bpy.ops.render.render(animation=True)
    Path(spec["result_json"]).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("K70_LOCAL_ANIMATION_BENCHMARK_OK", kind)


main()
