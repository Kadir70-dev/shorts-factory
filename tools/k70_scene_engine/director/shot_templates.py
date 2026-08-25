"""K70 AUTO SCENE DIRECTOR -- shot templates & composition lanes.

Pure Python, no bpy dependency (importable from the orchestrator process).

THE STRUCTURAL FIX for V4's 18+ manual-nudge problem: every lane below is
defined in CAMERA-RELATIVE coordinates (forward distance along the
camera's own view direction, lateral offset along the camera's own right
vector) instead of raw world X/Y. V4's actual failures were ALWAYS a
version of "this object's absolute X is fine for a FAR object but wrong
for a CLOSE one" -- because close objects need a small lateral offset
relative to the CAMERA to stay in frame, while far objects tolerate a
much wider one. Resolving every lane relative to the camera's pose
(chosen first, from the hero's desired framing) makes that relationship
automatic instead of something a human has to rediscover by trial and
error for every single prop.
"""
from __future__ import annotations

# Each lane: (forward_min, forward_max) distance in front of camera along
# its view direction, (lateral_min, lateral_max) offset along camera right
# vector, and a rough "ground_z" (0 = street level; lanes at ground level
# for props/vehicles).
#
# IMPORTANT: lateral is a FRACTION of the camera's real projected
# half-frame-width AT THAT FORWARD DISTANCE (-1.0 = exactly the left edge
# of frame, +1.0 = exactly the right edge, 0 = center), not absolute
# meters. Blender's portrait (9:16) renders use sensor_fit=AUTO, which
# resolves to VERTICAL fit since width<height -- the resulting horizontal
# FOV is much narrower than a naive "meters of lateral offset" guess
# assumes. The original meter-based lanes (e.g. vehicle_fg up to +0.9m at
# a ~1.6-2.6m forward distance) were 2-3x wider than the true visible
# half-width at that distance, which is why every V5 candidate had
# vehicles/NPCs projecting far outside the 0-1 screen range. Expressing
# lanes as frame-width fractions makes them automatically correct for
# ANY camera lens/distance the director ends up choosing -- see
# composition._half_width_at_dist / _lane_point.
LANES = {
    "hero":            {"forward": (2.6, 3.4), "lateral": (-0.05, 0.05)},
    "npc_close":       {"forward": (2.3, 3.6), "lateral": (-0.55, 0.55)},
    # Vehicle lateral offset is NOT drawn from here -- composition.py
    # computes it analytically per-instance from the vehicle's real
    # broadside length and the frame's actual half-width at the drawn
    # forward distance (see VEHICLE_NATIVE_LENGTH), guaranteeing the
    # camera-to-hero sightline stays clear regardless of which vehicle
    # kind or distance gets picked. Only "forward" is used for vehicles.
    "vehicle_fg":      {"forward": (2.0, 3.0), "lateral": (0.0, 0.0)},
    "vehicle_mid":     {"forward": (3.2, 4.4), "lateral": (0.0, 0.0)},
    # building_L/building_R/vegetation carry large scale factors (buildings
    # 2.0-2.8x, vegetation 1.6-2.2x of their native ~1m/~0.6m footprints),
    # so their fraction magnitude must clear their OWN half-footprint, not
    # just reach the frame edge -- a fraction that only just reaches 1.0
    # still puts a multi-meter-wide object's CENTER near the view axis,
    # walling off everything behind it (this is what produced the
    # coverage=1.0 / sky_occupancy=0.0 / everything-occluded symptom after
    # the FOV fix alone). Pushing these lanes' centers past the edge (>1.0)
    # keeps only their near edge peeking into frame, as flanking elements.
    "building_L":      {"forward": (2.8, 5.5), "lateral": (-1.7, -1.05)},
    "building_R":      {"forward": (3.2, 6.0), "lateral": (1.05, 1.7)},
    # explicit depth bands so buildings aren't all bunched at one distance
    # (a single near building at max analytic-clearance scale was
    # dominating ~28% of frame in V5's winner -- V5.1 spreads buildings
    # across near/mid/far so no one building carries that much weight,
    # and the depth-layer scorer has real distance separation to reward).
    # near band pushed a bit past vehicle_fg (2.0-3.0) / npc_close
    # (2.3-3.6)'s own forward ranges -- V5.1's first attempt overlapped
    # those ranges almost entirely, which roughly doubled the structural
    # rejection rate (buildings occluding NPCs/vehicles/signage far more
    # often than V5's single wider band did).
    "building_near_L": {"forward": (3.3, 4.2), "lateral": (-1.7, -1.05)},
    "building_near_R": {"forward": (3.4, 4.3), "lateral": (1.05, 1.7)},
    "building_mid_L":  {"forward": (4.3, 5.4), "lateral": (-1.6, -1.0)},
    "building_mid_R":  {"forward": (4.4, 5.5), "lateral": (1.0, 1.6)},
    "building_far_L":  {"forward": (6.2, 8.0), "lateral": (-1.6, -1.0)},
    "building_far_R":  {"forward": (6.3, 8.1), "lateral": (1.0, 1.6)},
    "skyscraper":      {"forward": (7.0, 10.0), "lateral": (-1.6, 1.6)},
    "skyline_far":      {"forward": (11.0, 16.0), "lateral": (-1.8, 1.8)},
    "streetprop_near": {"forward": (1.2, 2.4), "lateral": (-1.1, -0.65)},
    "streetprop_far":  {"forward": (2.5, 4.0), "lateral": (0.6, 1.0)},
    "vegetation":      {"forward": (1.8, 3.2), "lateral": (-1.5, -0.95)},
    "practical_light": {"forward": (2.2, 3.8), "lateral": (-0.6, 0.6)},
}

# What "required_visible" keywords map to in terms of lane usage + counts.
REQUIRED_VISIBLE_MAP = {
    "john": {"kind": "hero"},
    "3_npcs": {"kind": "npc", "count": 3, "lane": "npc_close"},
    "2_vehicles": {"kind": "vehicle", "count": 2, "lanes": ["vehicle_fg", "vehicle_mid"]},
    "storefront": {"kind": "building", "count": 1, "lane": "building_L", "shopfront": True},
    "street_sign": {"kind": "signage", "count": 1},
    "skyline": {"kind": "skyline", "lane": "skyline_far"},
}

NPC_ROLES = ["sarah", "worker", "banker", "investor"]

BUILDING_LETTERS = list("abcdefghijklmn")
SKYSCRAPER_LETTERS = list("abcde")

# Native XY footprint (max horizontal world-space dimension at scale=1.0),
# measured directly from each Kenney asset (see measure_all.py probe used
# during V5 debugging). Letters vary from ~0.9m to 2.3m natively -- a flat
# random scale range applied uniformly (as originally used) produced
# wildly inconsistent footprints: building-e at a 2.0-2.8x "normal" scale
# is 3.3-4.6m wide, which cannot be framed as a side-flanking building at
# any reasonable lateral offset and instead fills the whole shot. Buildings
# are scaled to hit a FIXED target footprint instead, so every letter
# reads as a similarly-sized building regardless of which one is picked.
BUILDING_NATIVE_FOOTPRINT = {
    "a": 0.94, "b": 0.97, "c": 1.09, "d": 0.9, "e": 1.64, "f": 1.03,
    "g": 0.97, "h": 1.008, "i": 1.302, "j": 2.084, "k": 2.084, "l": 1.402,
    "m": 1.242, "n": 2.32,
}
SKYSCRAPER_NATIVE_FOOTPRINT = {"a": 1.36, "b": 1.36, "c": 1.388, "d": 1.388, "e": 1.295}
BUILDING_TARGET_FOOTPRINT = (1.7, 2.3)
SKYSCRAPER_TARGET_FOOTPRINT = (2.0, 2.6)

VEHICLE_KINDS = [
    ("taxi.glb", (0.85, 0.72, 0.10)),
    ("delivery.glb", None),
    ("sedan.glb", (0.55, 0.15, 0.15)),
    ("suv.glb", (0.25, 0.35, 0.45)),
    ("police.glb", None),
]

# Vehicles are rotated broadside to the camera (their length axis, not
# their 1.5m-native width, faces across the frame -- see composition.py's
# vehicle placement), so LENGTH is the dimension that matters for
# clearing the camera-to-hero sightline. Measured natively (scale=1.0) via
# the same Blender-probe technique used for BUILDING_NATIVE_FOOTPRINT.
VEHICLE_NATIVE_LENGTH = {
    "taxi.glb": 2.75, "delivery.glb": 3.25, "sedan.glb": 2.55,
    "suv.glb": 2.7, "police.glb": 3.1,
}

SIGN_KEYS = ["sign_cafe", "sign_k70bank", "sign_market", "sign_office"]

TIME_OF_DAY_PROFILES = {
    # golden_hour uses the V2 golden-hour system (setup_golden_hour_v2):
    # sun direction is derived from the CAMERA's own forward/right basis
    # (a 3/4 back-light) rather than a fixed absolute rotation, so these
    # params are azimuth/elevation relative to camera, not a raw Euler.
    "golden_hour": {"mode": "golden_hour_v2", "azimuth_deg": 145.0, "elevation_deg": 19.0,
                    "sun_energy": 6.0, "sun_color": [1.0, 0.60, 0.32],
                    "sky_horizon": [0.92, 0.56, 0.38], "sky_zenith": [0.33, 0.42, 0.62],
                    "fill_color": [0.42, 0.52, 0.85], "exposure": 0.35},
    "morning":     {"sun_rotation": [1.05, 0, 0.5], "sun_energy": 3.8,
                    "sky_color": [0.55, 0.68, 0.85], "sun_color": [1.0, 0.94, 0.85],
                    "fill_color": [0.6, 0.68, 0.85]},
    "day":         {"sun_rotation": [0.95, 0, 0.75], "sun_energy": 4.4,
                    "sky_color": [0.55, 0.65, 0.80], "sun_color": [1.0, 0.97, 0.92],
                    "fill_color": [0.55, 0.62, 0.82]},
    "overcast":    {"sun_rotation": [0.8, 0, 0.6], "sun_energy": 2.4,
                    "sky_color": [0.62, 0.63, 0.65], "sun_color": [0.92, 0.93, 0.95],
                    "fill_color": [0.6, 0.61, 0.63]},
    "office":      {"sun_rotation": [0.9, 0, 0.4], "sun_energy": 2.0,
                    "sky_color": [0.6, 0.62, 0.66], "sun_color": [0.95, 0.94, 0.9],
                    "fill_color": [0.7, 0.72, 0.78]},
}


def resolve_shot_spec(spec: dict) -> dict:
    """Fills in defaults for any high-level fields the caller omitted --
    the whole point is the caller should NOT need to supply coordinates."""
    out = dict(spec)
    out.setdefault("density", "medium")
    out.setdefault("camera", "medium_tracking")
    out.setdefault("time_of_day", "day")
    out.setdefault("required_visible", ["john", "3_npcs", "2_vehicles", "storefront", "street_sign", "skyline"])
    density_targets = {
        "low": {"buildings": 2, "vehicles": 1, "npcs": 2, "props": 2},
        "medium": {"buildings": 3, "vehicles": 2, "npcs": 3, "props": 4},
        "high": {"buildings": 5, "vehicles": 3, "npcs": 4, "props": 6},
    }
    out["density_targets"] = density_targets.get(out["density"], density_targets["medium"])
    return out
