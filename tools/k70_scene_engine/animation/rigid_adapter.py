"""Rigid joint transforms for block characters—never mesh deformation."""
from __future__ import annotations

RIGID_JOINT_MAP = {
    "hips": "root", "chest": "torso", "head": "head",
    "left_upper_arm": "upper_arm.L", "right_upper_arm": "upper_arm.R",
    "left_forearm": "forearm.L", "right_forearm": "forearm.R",
    "left_hand": "hand.L", "right_hand": "hand.R",
    "left_thigh": "thigh.L", "right_thigh": "thigh.R",
    "left_shin": "shin.L", "right_shin": "shin.R",
    "left_foot": "foot.L", "right_foot": "foot.R",
}


def validate_rigid_character(parts) -> list[str]:
    errors = []
    for part in parts:
        if getattr(part, "type", None) != "MESH": continue
        if getattr(part, "vertex_groups", None) and len(part.vertex_groups):
            errors.append(f"{part.name}: vertex groups would permit skin deformation")
        if any(getattr(m, "type", "") == "ARMATURE" for m in getattr(part, "modifiers", ())):
            errors.append(f"{part.name}: armature modifier forbidden")
    return errors


def apply_joint_samples(joints: dict, samples: dict[str, list[dict]], frame_offset=0):
    """Apply rotation/translation samples to Empty pivots inside Blender."""
    for semantic, frames in samples.items():
        joint = joints.get(RIGID_JOINT_MAP.get(semantic, semantic))
        if joint is None: continue
        for sample in frames:
            frame = frame_offset + int(sample["frame"])
            if "rotation_euler" in sample:
                joint.rotation_euler = sample["rotation_euler"]
                joint.keyframe_insert("rotation_euler", frame=frame)
            if "location" in sample:
                joint.location = sample["location"]
                joint.keyframe_insert("location", frame=frame)
