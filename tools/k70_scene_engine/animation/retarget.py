"""Semantic skeleton mapping and content-addressed retarget-plan cache.

The Blender adapter consumes the returned plan; keeping discovery and mapping in
plain Python makes it testable without importing bpy into the production process.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ALIASES = {
    "root": ("root", "master", "origin"), "hips": ("hips", "pelvis", "hip"),
    "spine": ("spine", "spine_01"), "chest": ("chest", "spine_02", "spine_03"),
    "neck": ("neck", "neck_01"), "head": ("head",),
    "left_shoulder": ("shoulder_l", "clavicle_l", "upperarm_l"),
    "right_shoulder": ("shoulder_r", "clavicle_r", "upperarm_r"),
    "left_upper_arm": ("upper_arm_l", "upperarm_l", "arm_l"),
    "right_upper_arm": ("upper_arm_r", "upperarm_r", "arm_r"),
    "left_forearm": ("forearm_l", "lowerarm_l"), "right_forearm": ("forearm_r", "lowerarm_r"),
    "left_hand": ("hand_l", "wrist_l"), "right_hand": ("hand_r", "wrist_r"),
    "left_thigh": ("thigh_l", "upleg_l"), "right_thigh": ("thigh_r", "upleg_r"),
    "left_shin": ("shin_l", "calf_l", "leg_l"), "right_shin": ("shin_r", "calf_r", "leg_r"),
    "left_foot": ("foot_l", "ankle_l"), "right_foot": ("foot_r", "ankle_r"),
}


def _norm(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    value = value.replace("left", "l").replace("right", "r")
    return value


@dataclass(frozen=True)
class RetargetPlan:
    source_signature: str
    target_signature: str
    mapping: dict[str, str]
    source_fps: float
    target_fps: float
    scale: float
    forward_axis: str
    cache_hit: bool = False


def semantic_map(source_bones: list[str], target_bones: list[str]) -> dict[str, str]:
    src = {_norm(n): n for n in source_bones}; tgt = {_norm(n): n for n in target_bones}
    out: dict[str, str] = {}
    for semantic, aliases in ALIASES.items():
        s = next((src[_norm(a)] for a in aliases if _norm(a) in src), None)
        t = next((tgt[_norm(a)] for a in aliases if _norm(a) in tgt), None)
        if s and t: out[s] = t
    return out


def build_plan(source_bones: list[str], target_bones: list[str], *, source_fps=30.0,
               target_fps=30.0, source_height=1.0, target_height=1.0,
               forward_axis="-Y", cache_dir: Path | None = None) -> tuple[RetargetPlan, float]:
    started = time.perf_counter()
    cache_dir = cache_dir or Path(__file__).resolve().parents[3] / "data/assets/motions/cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {"source": source_bones, "target": target_bones, "source_fps": source_fps,
               "target_fps": target_fps, "source_height": source_height,
               "target_height": target_height, "forward_axis": forward_axis}
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    path = cache_dir / f"{key}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8")); data["cache_hit"] = True
        return RetargetPlan(**data), time.perf_counter() - started
    plan = RetargetPlan(key[:16], key[16:32], semantic_map(source_bones, target_bones),
                        source_fps, target_fps, target_height / max(source_height, 1e-6), forward_axis)
    path.write_text(json.dumps(asdict(plan), indent=2), encoding="utf-8")
    return plan, time.perf_counter() - started


def resample_frame(frame: float, source_fps: float, target_fps: float) -> float:
    return frame * target_fps / source_fps
