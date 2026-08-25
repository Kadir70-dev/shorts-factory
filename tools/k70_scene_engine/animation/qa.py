from __future__ import annotations

import math


def analyze_samples(samples: list[dict], *, ground_z=0.0, max_joint_degrees=150.0) -> dict:
    feet = [s for s in samples if s.get("joint") in {"left_foot", "right_foot"}]
    below = sum(float(s.get("z", 0)) < ground_z - .025 for s in feet)
    floating = sum(float(s.get("z", 0)) > ground_z + .15 for s in feet)
    extreme = sum(abs(float(v)) > math.radians(max_joint_degrees)
                  for s in samples for v in s.get("rotation", ()))
    discontinuities = sum(abs(float(b.get("root_x", 0))-float(a.get("root_x", 0))) > .5
                          for a, b in zip(samples, samples[1:]))
    return {"feet_below_ground": below, "floating_feet": floating,
            "extreme_joint_rotations": extreme, "root_discontinuities": discontinuities,
            "pass": not any((below, floating, extreme, discontinuities))}
