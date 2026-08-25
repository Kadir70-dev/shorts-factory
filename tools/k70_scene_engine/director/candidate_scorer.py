"""K70 AUTO SCENE DIRECTOR -- deterministic candidate scoring. Pure Python.

This is explicitly a DETERMINISTIC QUALITY FILTER, not an aesthetic AI
critic: it consumes the real geometry-based visibility_report produced by
_director_build_and_check.py (world_to_camera_view + ray_cast results) and
turns it into hard-reject decisions + category scores. It removes
obviously-bad candidates; it does not claim to judge beauty.

V5.1 ADDITION: `hard_reject`/`score_candidate` below are UNCHANGED (V5's
own driver script still calls them as-is). `visual_score()` is a new,
separate second stage: V5's winner (seed 2008) passed every one of these
existing structural/count-based checks with a 9.37 total yet still read
as visually worse than V4 -- a single flanking building filled ~28% of
frame at point-blank range with no sky/ground/depth visible in the crop,
because nothing here scored FRAMING, DEPTH LAYERING, or actual rendered
LIGHTING quality, only "is this required thing technically in frame."
visual_score() adds exactly those signals (subject dominance/framing,
fg/mg/bg depth-layer occupancy, composition balance with a hard cap on
any single non-hero object's screen dominance, and -- once a preview
image exists -- rendered luminance-based lighting/practical-light
scoring) and reuses score_candidate()'s existing sub-scores for the
categories it already measured reasonably (required-visibility,
occlusion, vegetation/sky)."""
from __future__ import annotations

from pathlib import Path


def _get(vis, prefix):
    return {k: v for k, v in vis.items() if k.startswith(prefix)}


def hard_reject(report: dict) -> list[str]:
    """Returns a list of reasons (empty list = not rejected). Mirrors the
    spec's explicit HARD REJECTION RULES -- any one of these means the
    candidate must never reach final render."""
    reasons = []
    vis = report["visibility"]

    hero = vis.get("hero")
    if hero is None or not hero["in_frame"]:
        reasons.append("hero not in frame")
    else:
        if hero["cropped"] and hero["screen_bbox"][3] > 0.985:
            reasons.append("hero head likely cropped (bbox touches top edge)")
        if hero["coverage"] < 0.02:
            reasons.append("hero mostly outside frame (coverage too low)")
        if hero["occluded"]:
            reasons.append("hero face/key-point occluded")

    npcs = _get(vis, "npc_")
    visible_npcs = [v for v in npcs.values() if v["in_frame"] and not v["occluded"] and v["coverage"] > 0.003]
    if len(visible_npcs) < 2:
        reasons.append(f"required NPC count not visible ({len(visible_npcs)} visible)")

    vehicles = _get(vis, "vehicle_")
    visible_vehicles = [v for v in vehicles.values() if v["in_frame"] and not v["occluded"] and v["coverage"] > 0.01]
    if len(visible_vehicles) < 1:
        reasons.append(f"required vehicle(s) not visible ({len(visible_vehicles)} visible)")

    signage = _get(vis, "signage_")
    if signage and not any(v["in_frame"] and not v["occluded"] for v in signage.values()):
        reasons.append("required sign not visible")

    if report.get("sky_occupancy", 0) > 0.85:
        reasons.append("excessive empty sky (>85% of sampled upper frame)")

    return reasons


def score_candidate(report: dict, plan: dict) -> dict:
    vis = report["visibility"]
    scores = {}

    hero = vis.get("hero", {})
    scores["HERO_VISIBILITY"] = 10.0 if hero.get("in_frame") and not hero.get("occluded") else 0.0
    hero_cov = hero.get("coverage", 0)
    target = 0.10  # reasonable full/near-full-body coverage target at 9:16
    scores["FACE_VISIBILITY"] = 10.0 if (hero.get("in_frame") and not hero.get("occluded")) else 0.0
    scores["COMPOSITION_BALANCE"] = max(0.0, 10.0 - abs(hero_cov - target) / target * 6.0) if hero_cov else 0.0
    # hero horizontal centering -- screen bbox center should sit in the
    # middle ~60% of frame width for a readable "hero" composition
    if hero.get("screen_bbox"):
        cx = (hero["screen_bbox"][0] + hero["screen_bbox"][2]) / 2
        scores["COMPOSITION_BALANCE"] -= abs(cx - 0.5) * 8.0
        scores["COMPOSITION_BALANCE"] = max(0.0, scores["COMPOSITION_BALANCE"])

    npcs = _get(vis, "npc_")
    visible_npcs = [v for v in npcs.values() if v["in_frame"] and not v["occluded"] and v["coverage"] > 0.003]
    scores["NPC_DISTRIBUTION"] = min(10.0, len(visible_npcs) * 3.0)

    vehicles = _get(vis, "vehicle_")
    visible_vehicles = [v for v in vehicles.values() if v["in_frame"] and not v["occluded"] and v["coverage"] > 0.01]
    scores["VEHICLE_VISIBILITY"] = min(10.0, len(visible_vehicles) * 5.0)

    buildings = _get(vis, "building_")
    visible_buildings = [v for v in buildings.values() if v["in_frame"] and v["coverage"] > 0.01]
    scores["REQUIRED_ASSET_VISIBILITY"] = min(10.0, len(visible_buildings) * 2.5)

    signage = _get(vis, "signage_")
    scores["SIGN_VISIBILITY"] = 10.0 if any(v["in_frame"] and not v["occluded"] for v in signage.values()) else 0.0

    veg = _get(vis, "vegetation_")
    scores["VEGETATION"] = 10.0 if any(v["in_frame"] and not v["occluded"] for v in veg.values()) else 3.0

    all_tracked = list(vis.values())
    occluded_frac = sum(1 for v in all_tracked if v["occluded"]) / max(len(all_tracked), 1)
    scores["OCCLUSION"] = round(10.0 * (1 - occluded_frac), 2)

    sky = report.get("sky_occupancy", 0.5)
    # some sky is fine/expected; penalize only excessive emptiness
    scores["SKY_OCCUPANCY"] = max(0.0, 10.0 - max(0.0, sky - 0.45) / 0.45 * 10.0)

    n_buildings = len(plan.get("buildings", [])) + len(plan.get("skyscrapers", []))
    n_props = len(plan.get("props", [])) + len(plan.get("vegetation", []))
    scores["SCENE_DENSITY"] = min(10.0, (n_buildings + n_props) * 0.9)

    light = vis.get("practical_light")
    scores["LIGHTING_CONTRAST"] = 10.0 if (light and light["in_frame"] and not light["occluded"]) else 5.0

    weights = {
        "HERO_VISIBILITY": 2.0, "FACE_VISIBILITY": 2.0, "COMPOSITION_BALANCE": 1.5,
        "NPC_DISTRIBUTION": 1.2, "VEHICLE_VISIBILITY": 1.3, "REQUIRED_ASSET_VISIBILITY": 1.0,
        "SIGN_VISIBILITY": 1.0, "VEGETATION": 0.6, "OCCLUSION": 1.4, "SKY_OCCUPANCY": 1.0,
        "SCENE_DENSITY": 0.8, "LIGHTING_CONTRAST": 0.6,
    }
    total_weight = sum(weights.values())
    total = sum(scores[k] * weights[k] for k in scores) / total_weight
    return {"categories": {k: round(v, 2) for k, v in scores.items()}, "total_score": round(total, 2)}


# ==========================================================================
# V5.1 -- premium cinematic composition scoring (visual_score / stage 2)
# ==========================================================================

DEPTH_LAYER_BY_KIND = {
    "hero": "midground", "npc": "midground", "signage": "midground",
    "vehicle": "foreground", "prop": "foreground", "vegetation": "foreground", "light": "foreground",
    "building": "background",
}


def _range_penalty(value, lo, hi, scale=10.0):
    """0 penalty inside [lo, hi]; scales up linearly outside it, in units
    of the range's own span so the same scale works across value types."""
    if lo <= value <= hi:
        return 0.0
    span = max(hi - lo, 1e-6)
    d = (lo - value) if value < lo else (value - hi)
    return min(scale, (d / span) * scale)


def hero_composition_score(hero: dict) -> float:
    """Subject/framing dominance: John should read as visually important
    without dominating the frame or being pushed to its edges. Uses only
    the existing screen_bbox/coverage -- no new Blender-side data needed."""
    if not hero or not hero.get("in_frame"):
        return 0.0
    xmin, ymin, xmax, ymax = hero["screen_bbox"]
    height_ratio = max(0.0, ymax - ymin)
    area_ratio = hero.get("coverage", 0.0)
    center_offset = abs((xmin + xmax) / 2 - 0.5)
    headroom = 1.0 - ymax   # world_to_camera_view: y=0 bottom, y=1 top
    footroom = ymin
    score = 10.0
    score -= _range_penalty(height_ratio, 0.32, 0.62, scale=4.0)
    score -= _range_penalty(area_ratio, 0.05, 0.16, scale=2.5)
    score -= _range_penalty(center_offset, 0.0, 0.32, scale=2.0)
    score -= _range_penalty(headroom, 0.03, 0.20, scale=2.0)
    score -= _range_penalty(footroom, 0.0, 0.40, scale=1.5)
    if hero.get("cropped"):
        score -= 1.5
    if hero.get("occluded"):
        score -= 2.0
    return max(0.0, round(score, 2))


def environment_readability_score(vis: dict) -> float:
    """A technically-visible building isn't useful if John + foreground
    props eat so much of the frame the environment can't tell a story."""
    hero = vis.get("hero", {})
    fg_kinds = ("vehicle", "prop", "vegetation", "light")
    fg_cov = hero.get("coverage", 0.0) + sum(
        v.get("coverage", 0.0) for v in vis.values() if v.get("kind") in fg_kinds)
    bg_entities = [v for v in vis.values() if v.get("kind") in ("building", "signage")]
    bg_visible = sum(1 for v in bg_entities if v.get("in_frame") and v.get("coverage", 0.0) > 0.01)
    score = 10.0
    if fg_cov > 0.45:
        score -= min(6.0, (fg_cov - 0.45) * 20.0)
    if bg_entities:
        score -= (1.0 - bg_visible / len(bg_entities)) * 4.0
    return max(0.0, round(score, 2))


def depth_layer_scores(vis: dict) -> tuple[float, dict]:
    """Classify every visible tracked entity into fg/mg/bg by KIND (per
    the spec's own semantic definition -- vehicles/props/vegetation frame
    the shot, hero+NPCs ARE the midground story, buildings+skyline are
    background) and reward genuine presence in all three, rather than
    total object count (which V5's SCENE_DENSITY rewarded regardless of
    whether the layers actually separated)."""
    occ = {"foreground": 0.0, "midground": 0.0, "background": 0.0}
    for v in vis.values():
        layer = DEPTH_LAYER_BY_KIND.get(v.get("kind"))
        if layer and v.get("in_frame"):
            occ[layer] += v.get("coverage", 0.0)
    score = 10.0
    for val in occ.values():
        if val < 0.02:
            score -= 2.5
    total = sum(occ.values()) or 1e-6
    max_frac = max(occ.values()) / total
    if max_frac > 0.7:
        score -= (max_frac - 0.7) * 10.0
    return max(0.0, round(score, 2)), {k: round(v, 4) for k, v in occ.items()}


def foreground_framing_score(vis: dict) -> float:
    """Foreground should FRAME the shot (a partial vehicle/lamp/tree edge),
    not block it -- penalize any single foreground object whose own
    coverage is large enough that it reads as an obstruction."""
    score = 10.0
    for v in vis.values():
        if DEPTH_LAYER_BY_KIND.get(v.get("kind")) == "foreground" and v.get("in_frame"):
            cov = v.get("coverage", 0.0)
            if cov > 0.18:
                score -= min(6.0, (cov - 0.18) * 20.0)
    return max(0.0, round(score, 2))


def composition_balance_score(vis: dict) -> float:
    """Screen-space visual-weight approximation (left/right balance) PLUS
    a hard dominance cap on the SINGLE WORST non-hero object -- this is
    the direct fix for V5's failure mode: a background building at 28%
    coverage scored perfectly on every V5 category because nothing
    capped how much frame ANY one non-hero object could occupy.

    V5.2 FIX: an earlier version summed this penalty across every
    qualifying object instead of taking the worst one -- in a "high
    density" scene (5 buildings, several routinely 22-35% coverage each
    just by being reasonably-sized real elements of a busy street) that
    made the score collapse to near-zero for essentially EVERY candidate
    regardless of actual composition quality (validated: 16/16 test
    candidates scored under 6.0). The dominance cap should catch ONE
    egregious object crowding the frame, not penalize a normally-dense
    scene for containing multiple medium-large elements."""
    score = 10.0
    left_w = right_w = 0.0
    max_dominant_cov = 0.0
    for v in vis.values():
        if not v.get("in_frame"):
            continue
        cov = v.get("coverage", 0.0)
        cx = (v["screen_bbox"][0] + v["screen_bbox"][2]) / 2
        if cx < 0.5:
            left_w += cov
        else:
            right_w += cov
        if v.get("kind") != "hero":
            max_dominant_cov = max(max_dominant_cov, cov)
    if max_dominant_cov > 0.24:
        score -= min(6.0, (max_dominant_cov - 0.24) * 16.0)
    total_w = left_w + right_w
    if total_w > 0.05:
        score -= (abs(left_w - right_w) / total_w) * 3.0
    return max(0.0, round(score, 2))


def sky_occupancy_score_v2(sky_frac: float, density: str = "high") -> float:
    """Density-aware sky scoring: a dense financial-district shot should
    penalize featureless empty sky more than a low-density/establishing
    shot would -- V5 used one flat threshold (0.45) regardless of shot
    density."""
    target_max = {"low": 0.55, "medium": 0.45, "high": 0.35}.get(density, 0.45)
    if sky_frac <= target_max:
        return 10.0
    return max(0.0, 10.0 - (sky_frac - target_max) / max(1.0 - target_max, 0.01) * 10.0)


def rule_of_thirds_bonus(hero: dict) -> float:
    """SOFT preference only (per spec section 8) -- a small bonus, not a
    hard requirement, for John's horizontal center sitting near a
    rule-of-thirds line."""
    if not hero or not hero.get("in_frame"):
        return 0.0
    cx = (hero["screen_bbox"][0] + hero["screen_bbox"][2]) / 2
    d = min(abs(cx - 1 / 3), abs(cx - 2 / 3))
    return max(0.0, 2.0 - d * 8.0)


def leading_line_score(hero: dict) -> float:
    """Practical proxy (per spec section 9's explicit 'does not need
    sophisticated computer vision, use known scene geometry' allowance):
    the street/road is built directly along the camera's own forward
    axis and John stands on that same axis by construction, so the
    road's vanishing point already converges near John whenever he's
    reasonably centered -- rewarding that centering is a lightweight
    stand-in for genuine leading-line detection without needing per-tile
    road screen-projection data."""
    if not hero or not hero.get("in_frame"):
        return 0.0
    cx = (hero["screen_bbox"][0] + hero["screen_bbox"][2]) / 2
    return max(0.0, 10.0 - abs(cx - 0.5) * 20.0)


def _luminance_in_bbox(image_path: str, screen_bbox: list[float]) -> float | None:
    """Mean perceptual luminance (0-255) of the pixels inside a normalized
    (0,0)-bottom-left/(1,1)-top-right screen_bbox, read from an actual
    rendered preview -- the practical proxy the spec asks for in place of
    a full lighting simulator (section 12/13's 'rendered-preview luminance
    or another practical proxy')."""
    try:
        from PIL import Image
    except ImportError:
        return None
    if not Path(image_path).exists():
        return None
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    xmin, ymin, xmax, ymax = screen_bbox
    px0, px1 = max(0, int(xmin * w)), min(w, int(xmax * w))
    py0, py1 = max(0, int((1 - ymax) * h)), min(h, int((1 - ymin) * h))
    if px1 <= px0 or py1 <= py0:
        return None
    pixels = list(img.crop((px0, py0, px1, py1)).getdata())
    if not pixels:
        return None
    return sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels) / len(pixels)


def hero_lighting_score_from_image(image_path: str, hero: dict) -> float:
    """John's face must stay readable under golden-hour lighting, not
    fall into silhouette. Samples the upper ~35% of his screen bbox (the
    head/face region) for mean luminance and scores against a mid-bright
    target -- too dark (silhouette) or blown out are both penalized."""
    if not hero or not hero.get("in_frame"):
        return 0.0
    xmin, ymin, xmax, ymax = hero["screen_bbox"]
    face_ymin = ymax - (ymax - ymin) * 0.35  # top ~35% of the bbox, in this y-up convention
    lum = _luminance_in_bbox(image_path, [xmin, face_ymin, xmax, ymax])
    if lum is None:
        return 6.0  # no image available yet (cheap check stage) -- neutral placeholder
    target = 140.0
    return max(0.0, round(10.0 - abs(lum - target) / target * 10.0, 2))


def practical_light_score_from_image(image_path: str, light: dict | None) -> float:
    """A practical light must ACTUALLY read as lit in the rendered image,
    not merely exist as an emissive material (the exact V4/V5 failure
    mode this is meant to catch)."""
    if not light or not light.get("in_frame"):
        return 4.0
    lum = _luminance_in_bbox(image_path, light["screen_bbox"])
    if lum is None:
        return 6.0
    if lum < 90:
        return round(max(0.0, lum / 90 * 6.0), 2)
    if lum > 240:
        return 6.0  # blown out -- visible but not the subtle golden-hour glow wanted
    return round(6.0 + min(4.0, (lum - 90) / 60.0), 2)


def visual_score(report: dict, plan: dict, preview_image_path: str | None = None) -> dict:
    """Stage-2 VISUAL score -- only run on candidates that already passed
    hard_reject() (the STRUCTURAL gate, unchanged). Reuses
    score_candidate()'s existing sub-scores for the categories it already
    measured reasonably (required-object visibility, occlusion,
    vegetation) instead of recomputing them from scratch."""
    vis = report["visibility"]
    hero = vis.get("hero", {})
    structural = score_candidate(report, plan)
    sc = structural["categories"]

    cats = {}
    cats["HERO_COMPOSITION"] = hero_composition_score(hero)
    cats["ENVIRONMENT_READABILITY"] = environment_readability_score(vis)
    depth_score, depth_occ = depth_layer_scores(vis)
    cats["DEPTH_LAYERING"] = depth_score
    cats["COMPOSITION_BALANCE"] = composition_balance_score(vis)
    cats["FOREGROUND_FRAMING"] = foreground_framing_score(vis)
    cats["REQUIRED_VISIBILITY"] = round(
        (sc["NPC_DISTRIBUTION"] + sc["VEHICLE_VISIBILITY"] + sc["REQUIRED_ASSET_VISIBILITY"] + sc["SIGN_VISIBILITY"])
        / 4.0, 2)
    cats["OCCLUSION"] = sc["OCCLUSION"]
    cats["SKY_BACKGROUND"] = round(
        (sky_occupancy_score_v2(report.get("sky_occupancy", 0.0), plan.get("density", "high")) + sc["VEGETATION"])
        / 2.0, 2)
    # COHERENCE has no automated visual-style classifier in this pipeline
    # (would need an actual image-recognition model, explicitly out of
    # scope per the spec's "no new AI stack" instruction elsewhere in this
    # project) -- held at a constant reflecting that every asset in this
    # scene is either an original K70 pixel-art texture or a verified-CC0
    # Kenney asset run through the same flat-shaded/nearest-neighbor
    # adapter, so style coherence is guaranteed by construction, not by
    # per-candidate measurement.
    cats["COHERENCE"] = 9.5

    if preview_image_path:
        cats["HERO_LIGHTING"] = hero_lighting_score_from_image(preview_image_path, hero)
        cats["PRACTICAL_LIGHT"] = practical_light_score_from_image(preview_image_path, vis.get("practical_light"))
    else:
        cats["HERO_LIGHTING"] = 6.0
        cats["PRACTICAL_LIGHT"] = 6.0
    cats["LIGHTING"] = round(cats["HERO_LIGHTING"] * 0.6 + cats["PRACTICAL_LIGHT"] * 0.4, 2)

    weights = {
        "HERO_COMPOSITION": 15, "ENVIRONMENT_READABILITY": 10, "DEPTH_LAYERING": 15,
        "COMPOSITION_BALANCE": 15, "LIGHTING": 20, "FOREGROUND_FRAMING": 5,
        "REQUIRED_VISIBILITY": 5, "OCCLUSION": 5, "SKY_BACKGROUND": 5, "COHERENCE": 5,
    }
    total_w = sum(weights.values())
    base_total = sum(cats[k] * weights[k] for k in weights) / total_w
    bonus = rule_of_thirds_bonus(hero) * 0.1 + leading_line_score(hero) * 0.05
    total = min(10.0, base_total + bonus)
    return {"categories": {k: round(v, 2) for k, v in cats.items()}, "depth_occupancy": depth_occ,
            "total_score": round(total, 2), "has_image_score": preview_image_path is not None}


# ==========================================================================
# V5.2 -- composition hard-veto, REAL camera-space depth, establishing-shot
# gate, on top of V5.1's visual_score (kept unmodified for compatibility).
#
# V5.1's winner (seed 3017, score 8.62) still had a badly unbalanced frame
# (COMPOSITION_BALANCE=4.43) and a close background object masquerading as
# "depth" (DEPTH_LAYERING=10.0 despite no real recession) because: (a) a
# weak category can always be outvoted by strong ones in a single weighted
# average, (b) DEPTH_LAYERING classified by KIND, not actual measured
# distance, so a close object of a "background" kind scored as if it were
# genuinely far away, and (c) nothing REQUIRED an establishing-shot's
# breadth (visible sky + ground + reasonable hero framing) -- V5.1's own
# scoring could and did converge on an even tighter crop than V5.
# ==========================================================================

import re


def _plan_location_for(name: str, plan: dict):
    """Maps a visibility-report entity key (e.g. 'npc_0_banker',
    'building_2', 'vehicle_1') back to its plan-space location, so real
    camera-space depth can be computed from the SAME location data used
    to place it -- no new Blender-side capture needed."""
    if name == "hero":
        return plan["hero"]["location"]
    if name == "practical_light":
        light = plan.get("practical_light")
        return light["location"] if light else None
    for prefix, list_key in (("npc", "npcs"), ("vehicle", "vehicles"), ("building", "buildings"),
                             ("signage", "signage"), ("prop", "props"), ("vegetation", "vegetation")):
        if name.startswith(prefix + "_"):
            m = re.match(rf"^{prefix}_(\d+)", name)
            if not m:
                continue
            idx = int(m.group(1))
            items = plan.get(list_key, [])
            if idx < len(items):
                return items[idx]["location"]
    return None


def real_forward_dist(name: str, plan: dict) -> float | None:
    """Actual camera-space depth (meters along the camera's own forward
    axis) for a tracked entity -- computed from plan location data, not
    guessed from its KIND. This is what lets the depth scorer tell a
    genuinely-distant skyline building apart from a close building that
    merely happens to be classified as 'background' by type."""
    loc = _plan_location_for(name, plan)
    if loc is None:
        return None
    cam = plan["camera"]
    cx, cy, _ = cam["location"]
    fx, fy, _ = cam["forward_dir"]
    return (loc[0] - cx) * fx + (loc[1] - cy) * fy


REAL_FOREGROUND_MAX_M = 3.0
REAL_MIDGROUND_MAX_M = 6.5


def _real_depth_layer(fdist: float | None) -> str | None:
    if fdist is None:
        return None
    if fdist < REAL_FOREGROUND_MAX_M:
        return "foreground"
    if fdist < REAL_MIDGROUND_MAX_M:
        return "midground"
    return "background"


def real_depth_score(vis: dict, plan: dict) -> tuple[float, dict]:
    """REAL camera-space depth/recession scoring (V5.2): classifies every
    visible entity by its ACTUAL measured forward distance (not its kind),
    rewards genuine presence in all three real-distance bands, and
    -- the key fix over V5.1's DEPTH_LAYERING -- penalizes when the
    'background' entities are all clustered at one close distance instead
    of actually spanning a real depth range (a single nearby object being
    technically classified as 'background' should NOT score as if a deep
    city were visible behind the hero)."""
    occ = {"foreground": 0.0, "midground": 0.0, "background": 0.0}
    bg_dists = []
    for name, v in vis.items():
        if not v.get("in_frame"):
            continue
        fdist = real_forward_dist(name, plan)
        layer = _real_depth_layer(fdist)
        if layer:
            occ[layer] += v.get("coverage", 0.0)
        if layer == "background":
            bg_dists.append(fdist)
    score = 10.0
    for val in occ.values():
        if val < 0.02:
            score -= 3.0
    total = sum(occ.values()) or 1e-6
    max_frac = max(occ.values()) / total
    if max_frac > 0.65:
        score -= (max_frac - 0.65) * 12.0
    if len(bg_dists) >= 2:
        spread = max(bg_dists) - min(bg_dists)
        if spread < 2.0:
            score -= (2.0 - spread) * 2.0
    elif bg_dists and bg_dists[0] < REAL_MIDGROUND_MAX_M + 1.0:
        score -= 2.0  # only one "background" entity and it isn't genuinely far
    return max(0.0, round(score, 2)), {
        "occupancy": {k: round(v, 4) for k, v in occ.items()},
        "background_distances_m": [round(d, 2) for d in bg_dists],
    }


def composition_hard_veto(categories: dict, threshold: float = 6.0) -> bool:
    """A single weak category should never be outvotable by strong ones
    elsewhere in a weighted average -- V5.1's winner had
    COMPOSITION_BALANCE=4.43 and still won on lighting/depth alone. Any
    candidate whose COMPOSITION_BALANCE falls below `threshold` is
    vetoed from the visual-ranking pool entirely, full stop."""
    return categories.get("COMPOSITION_BALANCE", 10.0) < threshold


def hero_prominence_score(vis: dict) -> float:
    """V5.2's winner (seed 5016) passed every existing check -- hero
    in-frame, correctly sized in isolation (coverage 0.086, within the
    0.05-0.16 HERO_COMPOSITION target range) -- yet visually read as
    upstaged by a closer, larger NPC standing next to him, because
    nothing compared John's screen presence to any OTHER human in the
    same frame. This measures exactly that: the largest NPC's coverage
    relative to hero's own."""
    hero = vis.get("hero")
    if not hero or not hero.get("in_frame"):
        return 0.0
    hero_cov = hero.get("coverage", 0.0)
    npc_covs = [v.get("coverage", 0.0) for v in vis.values() if v.get("kind") == "npc" and v.get("in_frame")]
    if not npc_covs:
        return 10.0
    max_npc_cov = max(npc_covs)
    score = 10.0
    if max_npc_cov > hero_cov:
        ratio = max_npc_cov / max(hero_cov, 1e-6)
        score -= min(8.0, (ratio - 1.0) * 6.0)
    elif max_npc_cov > hero_cov * 0.85:
        score -= 2.0  # NPC nearly as large as hero -- borderline, mild penalty
    return max(0.0, round(score, 2))


def hero_prominence_hard_veto(vis: dict, max_npc_to_hero_ratio: float = 1.6) -> bool:
    """Hard VETO (mirrors composition_hard_veto) for the clear-cut,
    egregious case: an NPC is CLEARLY larger on screen than the hero
    (the V5.2 winner's actual upstaging NPC looked roughly 2x+ hero's
    size) -- this should never be allowed to win purely because other
    categories (lighting, depth) happened to score well. Moderate size
    variance (an NPC 10-50% larger, common with natural placement
    variety) is left to hero_prominence_score's soft ranking penalty
    instead -- an earlier, much stricter 1.15x threshold vetoed every
    single candidate in a 24-seed test, since NPCs are routinely placed
    at a somewhat different depth than hero by design."""
    hero = vis.get("hero")
    if not hero or not hero.get("in_frame"):
        return True
    hero_cov = hero.get("coverage", 0.0)
    for v in vis.values():
        if v.get("kind") == "npc" and v.get("in_frame") and v.get("coverage", 0.0) > hero_cov * max_npc_to_hero_ratio:
            return True
    return False


def establishing_shot_reject(vis: dict, report: dict) -> list[str]:
    """Hard GATE (not a soft score) for establishing-shot breadth: V5.1's
    scoring could converge on an even tighter crop than V5 because nothing
    REQUIRED a wide shot to win -- only rewarded one softly. Any candidate
    failing these is rejected outright, the same way hard_reject()
    rejects structurally-invalid candidates."""
    reasons = []
    hero = vis.get("hero")
    if not hero or not hero.get("in_frame"):
        return ["no hero to evaluate for establishing-shot framing"]
    xmin, ymin, xmax, ymax = hero["screen_bbox"]
    height_ratio = max(0.0, ymax - ymin)
    headroom = 1.0 - ymax
    footroom = ymin
    if height_ratio > 0.68:
        reasons.append(f"hero too large for an establishing shot (height_ratio={height_ratio:.2f} > 0.68)")
    if headroom < 0.02:
        reasons.append(f"insufficient headroom ({headroom:.3f} < 0.02) -- head crowds the top edge")
    if footroom < 0.03:
        reasons.append(f"insufficient footroom ({footroom:.3f} < 0.03) -- no visible ground below hero")
    sky = report.get("sky_occupancy", 0.0)
    if sky < 0.02:
        reasons.append(f"no visible sky ({sky:.3f} < 0.02) -- shot reads as a claustrophobic close-up, not establishing")
    return reasons


def visual_score_v52(report: dict, plan: dict, preview_image_path: str | None = None) -> dict:
    """V5.2 visual score: identical to visual_score() (V5.1) except
    DEPTH_LAYERING is replaced by REAL_DEPTH (measured camera-space
    distance, not kind-based classification), plus a new HERO_PROMINENCE
    category (V5.2 fix-2: seed 5016 passed every check yet read as
    upstaged by a closer, larger NPC -- nothing compared hero's screen
    presence to any other human in frame). Composition hard-veto,
    hero-prominence hard-veto, and the establishing-shot hard gate are
    applied by the caller (auto_scene_director.run_director_v3) BEFORE a
    candidate reaches this function, exactly like hard_reject() gates
    entry to visual_score()."""
    base = visual_score(report, plan, preview_image_path=preview_image_path)
    cats = dict(base["categories"])
    real_depth, real_depth_detail = real_depth_score(report["visibility"], plan)
    del cats["DEPTH_LAYERING"]
    cats["REAL_DEPTH"] = real_depth
    cats["HERO_PROMINENCE"] = hero_prominence_score(report["visibility"])

    weights = {
        "HERO_COMPOSITION": 14, "HERO_PROMINENCE": 12, "ENVIRONMENT_READABILITY": 9, "REAL_DEPTH": 14,
        "COMPOSITION_BALANCE": 14, "LIGHTING": 18, "FOREGROUND_FRAMING": 5,
        "REQUIRED_VISIBILITY": 5, "OCCLUSION": 4, "SKY_BACKGROUND": 5, "COHERENCE": 5,
    }
    total_w = sum(weights.values())
    hero = report["visibility"].get("hero", {})
    base_total = sum(cats[k] * weights[k] for k in weights) / total_w
    bonus = rule_of_thirds_bonus(hero) * 0.1 + leading_line_score(hero) * 0.05
    total = min(10.0, base_total + bonus)
    return {"categories": {k: round(v, 2) for k, v in cats.items()}, "real_depth_detail": real_depth_detail,
            "total_score": round(total, 2), "has_image_score": preview_image_path is not None}
