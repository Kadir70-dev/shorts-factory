"""Reusable cinematic camera shot presets, runs INSIDE Blender.

Replaces "one auto-framer, always dead-center, always the same angle" as
the engine's only camera language. Each preset picks a lens (focal
length), a distance multiplier relative to subject span, a framing
offset (rule-of-thirds bias, not dead-center), and whether depth of
field should isolate the subject from the background.
"""
from __future__ import annotations

from mathutils import Vector

import bpy

SHOTS = {
    "establishing_wide":  {"lens": 24, "distance_mult": 2.6, "height_frac": 0.55, "dof": False, "offset_frac": 0.0},
    "medium":              {"lens": 50, "distance_mult": 1.6, "height_frac": 0.45, "dof": True,  "offset_frac": 0.12, "fstop": 4.0},
    "medium_close_up":     {"lens": 85, "distance_mult": 1.15, "height_frac": 0.65, "dof": True,  "offset_frac": 0.15, "fstop": 2.8},
    "close_up":            {"lens": 105, "distance_mult": 0.85, "height_frac": 0.80, "dof": True,  "offset_frac": 0.1, "fstop": 2.0},
    "portrait":            {"lens": 85, "distance_mult": 1.3, "height_frac": 0.60, "dof": True,  "offset_frac": 0.0, "fstop": 2.8},
    "low_angle_architecture": {"lens": 20, "distance_mult": 1.8, "height_frac": 0.15, "dof": False, "offset_frac": 0.0, "low_angle": True},
    "desk_level_detail":   {"lens": 60, "distance_mult": 0.6, "height_frac": 0.5, "dof": True, "offset_frac": 0.0, "fstop": 2.0},
    "aerial_establishing": {"lens": 20, "distance_mult": 3.2, "height_frac": 1.4, "dof": False, "offset_frac": 0.0, "aerial": True},
    "object_insert":       {"lens": 100, "distance_mult": 0.5, "height_frac": 0.5, "dof": True, "offset_frac": 0.0, "fstop": 1.8},
}


def build_camera(shot: str, mins: Vector, maxs: Vector, *, angle: str = "three_quarter",
                 dof_target=None, name: str = "k70_cam") -> "bpy.types.Object":
    """`angle` picks the horizontal approach direction (front/three_quarter
    /left/right), same vocabulary as the rest of the engine, so camera
    ANGLE and camera SHOT (distance/lens/DoF) are independent choices --
    a director can say "medium close-up, three-quarter" without the two
    concerns being tangled in one function."""
    if shot not in SHOTS:
        raise ValueError(f"unknown camera shot '{shot}', expected one of {list(SHOTS)}")
    spec = SHOTS[shot]
    center = (mins + maxs) / 2
    span = max((maxs - mins).x, (maxs - mins).y, (maxs - mins).z, 0.5)
    distance = span * spec["distance_mult"]

    # rule-of-thirds bias: shift the LOOK-AT target off dead-center
    # horizontally by offset_frac * span, giving the subject look-room
    # instead of pinning it to the exact frame center every shot.
    lateral_bias = span * spec["offset_frac"]

    offsets = {
        "front": Vector((lateral_bias, -distance * 1.3, distance * spec["height_frac"])),
        "three_quarter": Vector((distance * 0.8 + lateral_bias, -distance * 1.05, distance * spec["height_frac"])),
        "left": Vector((-distance * 1.05 + lateral_bias, -distance * 0.65, distance * spec["height_frac"])),
        "right": Vector((distance * 1.05 + lateral_bias, -distance * 0.65, distance * spec["height_frac"])),
    }
    if spec.get("low_angle"):
        offsets = {k: Vector((v.x, v.y, span * 0.08)) for k, v in offsets.items()}
    if spec.get("aerial"):
        offsets = {k: Vector((v.x * 0.3, v.y * 0.3, distance)) for k, v in offsets.items()}

    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = spec["lens"]
    if spec.get("dof"):
        cam_data.dof.use_dof = True
        cam_data.dof.aperture_fstop = spec.get("fstop", 2.8)
        if dof_target is not None:
            cam_data.dof.focus_object = dof_target
        else:
            cam_data.dof.focus_distance = distance

    cam_obj = bpy.data.objects.new(name, cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = center + offsets.get(angle, offsets["three_quarter"])
    look_at = center + Vector((lateral_bias * 0.3, 0, 0))
    direction = look_at - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam_obj
    return cam_obj
