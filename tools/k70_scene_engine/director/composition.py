"""K70 AUTO SCENE DIRECTOR -- composition planner. Pure Python, no bpy.

Given a resolved shot spec + integer seed, produces a concrete SCENE PLAN:
camera pose (chosen FIRST, from the hero's desired framing) and every
other entity (NPCs/vehicles/buildings/skyline/props) resolved from
shot_templates.LANES relative to that camera pose. This is what removes
the manual-nudging problem -- lanes are defined once, in camera-relative
space, and reused for every candidate/seed/shot instead of being
hand-picked per composition.
"""
from __future__ import annotations

import math
import random

from shot_templates import (LANES, NPC_ROLES, BUILDING_LETTERS, SKYSCRAPER_LETTERS,
                            VEHICLE_KINDS, VEHICLE_NATIVE_LENGTH, SIGN_KEYS, TIME_OF_DAY_PROFILES,
                            BUILDING_NATIVE_FOOTPRINT, SKYSCRAPER_NATIVE_FOOTPRINT,
                            BUILDING_TARGET_FOOTPRINT, SKYSCRAPER_TARGET_FOOTPRINT)


def _min_side_fraction(half_object_width, forward_dist, lens, margin=1.3):
    """Minimum |lateral_frac| needed to keep an object of the given
    half-width entirely clear of the camera's central sightline (where
    hero, and the ray to any other near-center entity, sits) at this
    forward distance -- plus a safety margin. Shared by every lane whose
    objects must not cross center (vehicles, NPCs, flanking buildings,
    vegetation): a fixed empirical fraction range only holds for one
    specific combination of object size/forward distance and silently
    breaks for any other (confirmed repeatedly during V5 debugging -- an
    SUV, then a tree, each dominated the frame and occluded hero despite
    lane ranges that looked reasonable on paper)."""
    half_w_frame = _half_width_at_dist(forward_dist, lens)
    return (half_object_width * margin) / half_w_frame


def _footprint_scale(native_footprint, target_range, rnd):
    """Scale factor that normalizes a wildly-varying-per-letter native
    asset footprint to a fixed target world-space size, so every letter
    frames consistently instead of some being 2-3x wider than others at
    the same nominal 'scale' value."""
    target = rnd.uniform(*target_range)
    return round(target / native_footprint, 3)


def _footprint_scale_screen_aware(native_footprint, target_screen_frac_range, forward_dist, lens, rnd,
                                  min_scale=0.5):
    """Scale chosen to hit a TARGET FRACTION of the frame's actual visible
    width AT THIS OBJECT'S OWN forward distance/lens -- not a fixed
    absolute meter size independent of distance (that was
    _footprint_scale's blind spot: at a mid/far depth band (4.3m+)
    combined with a narrow lens choice (28-30mm), the ENTIRE visible
    frame width at that distance can be as little as ~2m, so even a
    'normalized to 1.7-2.3m' building inevitably fills most of the
    frame regardless of lateral positioning -- confirmed via seed 5016:
    building 'l' at scale 1.466 (a fully in-range, reasonable-looking
    footprint) still covered 35% of frame because the visible width at
    its distance/lens was barely wider than the building itself).
    This is the general fix, applied to both buildings and vegetation."""
    target_frac = rnd.uniform(*target_screen_frac_range)
    frame_width_at_dist = 2.0 * _half_width_at_dist(forward_dist, lens)
    target_world_size = target_frac * frame_width_at_dist
    return max(min_scale, round(target_world_size / native_footprint, 3))


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _norm(a):
    m = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2) or 1.0
    return (a[0] / m, a[1] / m, a[2] / m)


# K70 renders are always portrait (9:16). Blender's camera sensor_fit=AUTO
# (the default, never overridden in _director_build_and_check.py) resolves
# to VERTICAL fit whenever width < height, meaning the vertical FOV is
# governed by sensor_height (Blender default 24mm) and the horizontal FOV
# is DERIVED from it via the aspect ratio -- it is much narrower than a
# naive "assume a wide horizontal FOV" guess produces. This must match
# setup_camera()'s actual cam_data settings (lens only; sensor_fit/width/
# height left at Blender defaults) or lane math and real projection will
# disagree again exactly like the original bug.
_ASPECT = 9.0 / 16.0  # width / height
_SENSOR_HEIGHT_MM = 24.0


def _half_width_at_dist(forward_dist, lens):
    vert_half_fov = math.atan(_SENSOR_HEIGHT_MM / (2.0 * lens))
    horiz_half_fov = math.atan(math.tan(vert_half_fov) * _ASPECT)
    return forward_dist * math.tan(horiz_half_fov)


def _lane_point(camera_pos, forward_dir, right_dir, forward_dist, lateral_frac, lens, ground_z=0.0):
    """lateral_frac is a fraction of the REAL projected half-frame-width at
    forward_dist (see _half_width_at_dist) -- not absolute meters -- so
    lanes stay correctly framed for whatever lens/distance the camera ends
    up using, instead of needing per-shot hand recalibration."""
    half_w = _half_width_at_dist(forward_dist, lens)
    lateral = lateral_frac * half_w
    p = _add(camera_pos, _scale(forward_dir, forward_dist))
    p = _add(p, _scale(right_dir, lateral))
    return (p[0], p[1], ground_z)


def _yaw_deg_facing(from_pt, to_pt) -> float:
    dx, dy = to_pt[0] - from_pt[0], to_pt[1] - from_pt[1]
    return math.degrees(math.atan2(dx, dy))  # 0 = facing +Y, matches K70 rig convention (root_rotation_z about Z)


def plan_scene(spec: dict, seed: int) -> dict:
    rnd = random.Random(seed)
    density = spec["density_targets"]

    # ---- 1. Hero placed at world origin, facing +Y (a fixed, known anchor -- ---- #
    # everything else is computed relative to this and to the camera, never
    # to arbitrary absolute coordinates).
    hero_pos = (0.0, 0.0, 0.0)
    hero_facing_deg = rnd.choice([-20, -10, 0, 10, 20])

    # ---- 2. Camera derived from desired hero screen framing ---- #
    # forward_dist is solved directly from Blender's real vertical FOV
    # (sensor_fit=AUTO -> VERTICAL fit for our always-portrait renders, so
    # vertical FOV depends only on sensor_height/lens, no aspect term
    # needed here -- see _half_width_at_dist for the horizontal/aspect
    # case). The previous version used an empirical proportionality
    # constant (base_lens=34/base_dist=5.0/base_frac=0.55) copied from old
    # V3/V4 renders that did not go through this same geometry pipeline;
    # it measured only ~32% actual frame-height coverage against a 55%
    # target. Solving H = 2 * d * tan(vert_half_fov) * target_frac for d
    # is exact for any lens instead of an approximate ratio.
    K70_HERO_HEIGHT_M = 1.75
    shot_tightness = {"wide_establishing": 0.42, "medium_tracking": 0.55, "close": 0.72}.get(
        spec.get("camera", "medium_tracking"), 0.55)
    target_frac = shot_tightness * rnd.uniform(0.9, 1.08)
    lens = rnd.choice([28, 30, 32, 34, 36, 38])
    vert_half_fov = math.atan(_SENSOR_HEIGHT_MM / (2.0 * lens))
    forward_dist = K70_HERO_HEIGHT_M / (2.0 * target_frac * math.tan(vert_half_fov))
    cam_height = 1.3 + rnd.uniform(-0.15, 0.25)
    lateral_jitter = rnd.uniform(-0.4, 0.4)

    hero_back_dir = (math.sin(math.radians(hero_facing_deg + 180)), math.cos(math.radians(hero_facing_deg + 180)), 0)
    camera_pos = _add(hero_pos, _scale(hero_back_dir, forward_dist))
    camera_pos = (camera_pos[0] + lateral_jitter, camera_pos[1], cam_height)
    look_at = (hero_pos[0], hero_pos[1], 1.15)

    forward_dir = _norm((look_at[0] - camera_pos[0], look_at[1] - camera_pos[1], 0.0))
    right_dir = _norm((forward_dir[1], -forward_dir[0], 0.0))  # 90deg CW in XY -> camera's screen-right

    fstop = {"wide_establishing": 4.5, "medium_tracking": 3.4, "close": 2.4}.get(
        spec.get("camera", "medium_tracking"), 3.2)

    plan = {
        "seed": seed,
        "hero": {"role": spec.get("hero", "john"), "location": hero_pos, "rotation_z_deg": hero_facing_deg},
        "camera": {"location": camera_pos, "look_at": look_at, "focus_at": (hero_pos[0], hero_pos[1], 1.0),
                  "lens": lens, "fstop": fstop, "forward_dir": forward_dir, "right_dir": right_dir,
                  "target_hero_frac": target_frac},
        "npcs": [], "vehicles": [], "buildings": [], "skyscrapers": [], "skyline": [], "props": [], "signage": [],
    }

    def lane_pt(lane_name, ground_z=0.0, forward_bias=None, lateral_bias=None):
        lane = LANES[lane_name]
        f = forward_bias if forward_bias is not None else rnd.uniform(*lane["forward"])
        l = lateral_bias if lateral_bias is not None else rnd.uniform(*lane["lateral"])
        return _lane_point(camera_pos, forward_dir, right_dir, f, l, lens, ground_z)

    # ---- NPCs ---- #
    # npc_close's forward range used to be a fixed (2.3, 3.6)m band --
    # ALWAYS closer to camera than hero's own computed distance (~4-5.5m
    # depending on lens/target_frac), so NPCs systematically projected
    # larger on screen than hero by basic perspective (a same-height
    # person ~1.5-2x closer projects ~2.5-4x more screen AREA) -- this
    # was the actual root cause of V5.2's "hero upstaged by a closer NPC"
    # failure, a placement-geometry problem, not just a missing score.
    # Fixed: NPC forward distance is now relative to hero's own actual
    # computed forward_dist, keeping them roughly at/near hero's own
    # depth (some slightly nearer, some slightly farther) instead of
    # always dramatically closer.
    #
    # A near-zero lateral fraction would still put an NPC almost exactly
    # on the camera-to-hero sightline, occluding hero's face/key point --
    # same analytic fix as vehicles: solve for the minimum lateral
    # fraction that clears an approximate human half-width at the NPC's
    # own drawn forward distance, plus a safety margin.
    # NPC_SLOTS: distinct (side, margin_range) bands, cycled by index --
    # V5.2's polish pass found heads/shoulders crowded together even
    # though each NPC individually cleared the hero sightline, because
    # side/margin were each drawn fully independently per NPC, so several
    # could land on the same side at similar distances from center with
    # no minimum gap between THEM specifically (only vs. hero). Cycling
    # through fixed, increasingly-wide bands guarantees real separation
    # between every NPC and between each NPC and hero, while still
    # varying the exact position within each band per seed.
    NPC_HALF_WIDTH_M = 0.25
    NPC_SLOTS = [(-1, (1.3, 1.6)), (1, (1.3, 1.6)), (-1, (2.1, 2.5)), (1, (2.1, 2.5))]
    roles = rnd.sample(NPC_ROLES, k=min(density["npcs"], len(NPC_ROLES)))
    for i, role in enumerate(roles):
        side, margin_range = NPC_SLOTS[i % len(NPC_SLOTS)]
        # Biased slightly FARTHER than hero on average (mean ~1.11x, not
        # 1.0x) -- even at equal distance, an NPC mid-stride (walk
        # animation spreads limbs) reads as a slightly larger bounding
        # box than hero's own idle pose, so a symmetric (0.90,1.15) range
        # still left every NPC a bit larger than hero on this seed.
        f = forward_dist * rnd.uniform(0.98, 1.24)
        half_w = _half_width_at_dist(f, lens)
        min_frac = (NPC_HALF_WIDTH_M * 1.3) / half_w
        frac = side * min_frac * rnd.uniform(*margin_range)
        pos = _lane_point(camera_pos, forward_dir, right_dir, f, frac, lens)
        facing = _yaw_deg_facing(pos, hero_pos) + rnd.uniform(-40, 40)
        anim = "walk" if rnd.random() < 0.4 else "idle"
        plan["npcs"].append({"role": role, "location": pos, "rotation_z_deg": facing, "animation": anim})

    # ---- vehicles ---- #
    # Vehicles are rotated broadside to the camera (their LENGTH axis, not
    # their 1.5m-native width, spans across the frame -- see `facing`
    # below, which aligns the vehicle's nose with the camera's right_dir).
    # A fixed lateral-fraction range can't reliably clear the camera-to-
    # hero sightline for every vehicle kind/forward-distance combination
    # (a 2.5-3.25m-long vehicle at a close forward distance dwarfs the
    # narrow portrait FOV's visible half-width no matter where in a
    # hand-picked range it lands -- confirmed via debug_occlusion.py: an
    # SUV at forward=2.07m filled the entire frame and occluded every
    # other tracked entity, hero included). Instead, solve analytically
    # for the minimum lateral fraction that clears the vehicle's own
    # broadside half-length at whatever forward distance gets drawn, then
    # add a safety margin -- this is correct for any lens/distance/kind
    # instead of needing a re-tuned range per case.
    lanes_cycle = ["vehicle_fg", "vehicle_mid"]
    for i in range(density["vehicles"]):
        lane = lanes_cycle[i % len(lanes_cycle)]
        f = rnd.uniform(*LANES[lane]["forward"])
        kind_file, color = rnd.choice(VEHICLE_KINDS)
        scale = 1.0
        half_len = VEHICLE_NATIVE_LENGTH[kind_file] * scale / 2.0
        half_w = _half_width_at_dist(f, lens)
        min_frac = (half_len * 1.35) / half_w  # 35% margin past the vehicle's own broadside half-length
        side = rnd.choice([-1, 1])
        frac = side * rnd.uniform(min_frac, min_frac * 1.3)
        pos = _lane_point(camera_pos, forward_dir, right_dir, f, frac, lens)
        facing = math.degrees(math.atan2(right_dir[0], right_dir[1])) + rnd.choice([0, 180]) + rnd.uniform(-8, 8)
        plan["vehicles"].append({"file": kind_file, "color": color, "location": pos,
                                 "rotation_z_deg": facing, "scale": scale, "lane": lane})

    # ---- buildings (storefront row always present for the "storefront" requirement) ---- #
    # Explicit near/mid/far depth bands (not one flat row with a small
    # forward nudge per index) so buildings genuinely separate in camera-
    # space depth -- both to look like a real deep city block, and to
    # feed the depth-layer scorer real distance separation instead of a
    # single crowded band where one near building can dominate the frame.
    SIGN_HALF_WIDTH_M = 0.375  # matches build_signboard's default w=0.75
    # Only ONE building in the crowded near zone (the shopfront, i=0) --
    # putting a second near building competed for the same close depth
    # NPCs/vehicles/signage occupy, substantially raising occlusion odds.
    BUILDING_DEPTH_CYCLE = ["near", "mid", "mid", "far", "far"]
    letters = rnd.sample(BUILDING_LETTERS, k=min(density["buildings"], len(BUILDING_LETTERS)))
    for i, letter in enumerate(letters):
        side_lr = "L" if i % 2 == 0 else "R"
        depth_band = BUILDING_DEPTH_CYCLE[i % len(BUILDING_DEPTH_CYCLE)]
        lane = f"building_{depth_band}_{side_lr}"
        f = rnd.uniform(*LANES[lane]["forward"])
        # Screen-fraction-aware, not a fixed meter target (see
        # _footprint_scale_screen_aware's docstring) -- a fixed 1.7-2.3m
        # target still dominated the frame at mid/far distances with a
        # narrow lens, since the frame's own visible width there can be
        # barely wider than the building itself.
        scale = _footprint_scale_screen_aware(BUILDING_NATIVE_FOOTPRINT[letter], (0.22, 0.38), f, lens, rnd)
        half_w_obj = (BUILDING_NATIVE_FOOTPRINT[letter] * scale) / 2.0
        min_frac = _min_side_fraction(half_w_obj, f, lens)
        side = -1 if side_lr == "L" else 1
        frac = side * rnd.uniform(min_frac, min_frac * 1.3)
        pos = _lane_point(camera_pos, forward_dir, right_dir, f, frac, lens)
        facing = math.degrees(math.atan2(-forward_dir[0], -forward_dir[1]))
        shopfront = (i == 0)
        plan["buildings"].append({"letter": letter, "location": pos, "rotation_z_deg": facing,
                                  "scale": scale, "shopfront": shopfront, "depth_band": depth_band,
                                  "sign_key": rnd.choice(SIGN_KEYS) if shopfront else None})
        if shopfront:
            # The sign is a small, independently-readable object -- it must
            # NOT inherit the flanking building's far-off-center placement
            # (that placement is deliberately wide so only the building's
            # EDGE peeks into frame; a tiny sign at that same fraction
            # projects far outside frame entirely, since its own angular
            # half-width is nowhere near large enough to reach back to
            # center). Give it its own tight analytic placement instead --
            # same side/forward distance (stays visually associated with
            # the storefront) but only just past the sign's own, much
            # smaller, minimum clearance.
            # Pull the sign forward of the building's own front face -- at
            # the building's own center forward_dist it can end up seated
            # inside the building's solid volume (Kenney buildings are
            # roughly as deep as they are wide), which self-occludes it
            # from the camera's viewpoint.
            sign_f = f - (half_w_obj + 0.2)
            sign_min_frac = _min_side_fraction(SIGN_HALF_WIDTH_M, sign_f, lens)
            sign_frac = side * sign_min_frac * 1.05
            sign_pos = _lane_point(camera_pos, forward_dir, right_dir, sign_f, sign_frac, lens, ground_z=2.3)
    if plan["buildings"]:
        plan["signage"].append({"sign_key": plan["buildings"][0]["sign_key"], "attached_to": 0,
                                "location": sign_pos})

    # ---- skyscrapers + far skyline ---- #
    for i in range(2):
        letter = rnd.choice(SKYSCRAPER_LETTERS)
        pos = lane_pt("skyscraper")
        scale = _footprint_scale(SKYSCRAPER_NATIVE_FOOTPRINT[letter], SKYSCRAPER_TARGET_FOOTPRINT, rnd)
        plan["skyscrapers"].append({"letter": letter, "location": pos, "scale": scale})
    for i in range(5):
        letter = rnd.choice(BUILDING_LETTERS)
        pos = lane_pt("skyline_far")
        plan["skyline"].append({"letter": letter, "location": pos, "scale": rnd.uniform(2.0, 3.0)})

    # ---- street props + vegetation ---- #
    prop_kinds = rnd.choices(["streetlamp", "traffic_light", "bin", "planter"], k=density["props"])
    for i, kind in enumerate(prop_kinds):
        lane = "streetprop_near" if i % 2 == 0 else "streetprop_far"
        pos = lane_pt(lane)
        plan["props"].append({"kind": kind, "location": pos})
    TREE_NATIVE_WIDTH_M = 0.6
    veg_lane = LANES["vegetation"]
    veg_f = rnd.uniform(*veg_lane["forward"])
    # Screen-fraction-aware, not a flat 1.6-2.2 scale range independent of
    # distance/lens -- the tree was covering ~41% of frame (seed 5016)
    # despite a "reasonable" scale value, because vegetation's close
    # forward range (1.8-3.2m) combined with a narrow lens choice made
    # even a modest absolute size fill most of the visible frame. A tree
    # is meant to be a light foreground ACCENT, so its target fraction is
    # deliberately much smaller than a building's.
    veg_scale = _footprint_scale_screen_aware(TREE_NATIVE_WIDTH_M, (0.10, 0.18), veg_f, lens, rnd)
    veg_half_w = (TREE_NATIVE_WIDTH_M * veg_scale) / 2.0
    veg_min_frac = _min_side_fraction(veg_half_w, veg_f, lens)
    veg_side = rnd.choice([-1, 1])
    veg_frac = veg_side * rnd.uniform(veg_min_frac, veg_min_frac * 1.3)
    veg_pos = _lane_point(camera_pos, forward_dir, right_dir, veg_f, veg_frac, lens)
    plan["vegetation"] = [{"location": veg_pos, "scale": veg_scale}]

    # ---- lighting ---- #
    tod = spec.get("time_of_day", "day")
    plan["lighting"] = {"mode": "block_world_v31", **TIME_OF_DAY_PROFILES.get(tod, TIME_OF_DAY_PROFILES["day"])}
    plan["practical_light"] = {"location": lane_pt("practical_light", ground_z=1.2)}

    return plan
