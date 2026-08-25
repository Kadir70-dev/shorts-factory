"""K70 VFX Director -- semantic VFX presets. Pure Python, no bpy/Natron
dependency (importable from the orchestrator process).

This is a HELPER LAYER, not a 10th K70 visual mode: it consumes ALREADY-
RENDERED frames from any compatible K70 visual mode/animation output and
adds story-appropriate cinematic VFX on top via two real compositing
engines -- Blender's native 2D compositor (Glare/Sun Beams/Color
Balance -- genuinely Blender-native effects, not reimplemented) and
Natron/OpenFX (confirmed-real plugin IDs from GMIC/Misc bundles, verified
via LIVE introspection against this actual install, not guessed -- see
_introspect_params.py's dump).

Every numeric value below is a BASE amount at intensity=1.0; vfx_director
scales them by the caller's requested intensity (0..1+) and quality
level. Deterministic mapping only -- no LLM/API/cloud dependency.
"""
from __future__ import annotations

# Each preset's "blender" block configures ONE compositor pass:
#   glare_mode: None | "FOG_GLOW" | "STREAKS" | "GHOSTS" (Blender's real
#     Glare node modes -- FOG_GLOW reads as atmospheric bloom/haze,
#     STREAKS reads as sparkle/light-accent streaks)
#   glare_strength: 0..1 base strength
#   sun_beams: bool -- Blender's real "Sun Beams" (god-rays) node
#   sun_beams_strength: 0..1
#   color_balance: base RGB "gain" multiplier (a gentle push toward warm
#     or cool before the Natron grade does the heavier lifting)
#   vignette: 0..1 base strength (a soft radial-mask darken, built from
#     primitive compositor nodes -- Blender has no single "Vignette" node)
#
# Each preset's "natron" block configures the OpenFX chain (real plugin
# IDs: eu.gmic.RainSnow, eu.gmic.LightGlow, eu.gmic.Vignette,
# eu.gmic.AddGrain, net.sf.openfx.GradePlugin):
#   rain: bool, rain_density/rain_speed/rain_angle (eu.gmic.RainSnow)
#   vignette_strength: 0..1 (eu.gmic.Vignette "Strength")
#   grain_opacity: 0..1 (eu.gmic.AddGrain "Opacity")
#   grade_multiply: (r,g,b) base color multiply (net.sf.openfx.GradePlugin "multiply")
#   grade_offset: (r,g,b) base offset (net.sf.openfx.GradePlugin "offset")
#   glow: None | {"tint": (r,g,b), "amplitude": 0..1} (eu.gmic.LightGlow)
#   chromatic_aberration: 0..1 (eu.gmic.ChromaticAberrations "Amplitude"-style knob)

PRESETS = {
    "clean_cinematic": {
        "story": "Neutral baseline -- a light cinematic pass with no story-specific atmosphere.",
        "blender": {"glare_mode": "FOG_GLOW", "glare_strength": 0.12, "sun_beams": False,
                   "sun_beams_strength": 0.0, "color_balance_gain": (1.0, 1.0, 1.0), "vignette": 0.12},
        "natron": {"rain": False, "rain_density": 0.0, "rain_speed": 0.0, "rain_angle": 0.0,
                  "vignette_strength": 0.15, "grain_opacity": 0.05,
                  "grade_multiply": (1.0, 1.0, 1.0), "grade_offset": (0.0, 0.0, 0.0),
                  "glow": None, "chromatic_aberration": 0.0},
    },
    "golden_hour": {
        "story": "Warm low-angle exterior glow -- matches the K70 voxel director's own golden-hour lighting.",
        "blender": {"glare_mode": "FOG_GLOW", "glare_strength": 0.25, "sun_beams": True,
                   "sun_beams_strength": 0.2, "color_balance_gain": (1.06, 1.0, 0.9), "vignette": 0.18},
        "natron": {"rain": False, "rain_density": 0.0, "rain_speed": 0.0, "rain_angle": 0.0,
                  "vignette_strength": 0.2, "grain_opacity": 0.05,
                  "grade_multiply": (1.05, 1.0, 0.9), "grade_offset": (0.01, 0.0, -0.01),
                  "glow": {"tint": (1.0, 0.8, 0.55), "amplitude": 0.2}, "chromatic_aberration": 0.0},
    },
    "financial_crisis": {
        "story": "Markets collapsed overnight -- subtle rain, cold atmospheric haze, a colder grade, "
                "and a faint warning-amber glow accent (never a full red wash -- must stay readable).",
        "blender": {"glare_mode": "FOG_GLOW", "glare_strength": 0.4, "sun_beams": False,
                   "sun_beams_strength": 0.0, "color_balance_gain": (0.93, 0.97, 1.05), "vignette": 0.35},
        "natron": {"rain": True, "rain_density": 0.45, "rain_speed": 0.55, "rain_angle": 12.0,
                  "vignette_strength": 0.32, "grain_opacity": 0.12,
                  "grade_multiply": (0.9, 0.94, 1.05), "grade_offset": (-0.015, -0.01, 0.0),
                  "glow": {"tint": (1.0, 0.4, 0.15), "amplitude": 0.18}, "chromatic_aberration": 0.0},
    },
    "market_crash": {
        "story": "A sharper, more acute version of financial_crisis -- for the single worst-moment shot "
                "of a downturn sequence, not the whole sequence.",
        "blender": {"glare_mode": "FOG_GLOW", "glare_strength": 0.5, "sun_beams": False,
                   "sun_beams_strength": 0.0, "color_balance_gain": (0.9, 0.95, 1.08), "vignette": 0.42},
        "natron": {"rain": True, "rain_density": 0.65, "rain_speed": 0.75, "rain_angle": 18.0,
                  "vignette_strength": 0.4, "grain_opacity": 0.16,
                  "grade_multiply": (0.86, 0.91, 1.08), "grade_offset": (-0.02, -0.015, 0.0),
                  "glow": {"tint": (1.0, 0.3, 0.1), "amplitude": 0.28}, "chromatic_aberration": 0.05},
    },
    "wealth_growth": {
        "story": "His investment grew to $1M -- controlled light-streak accents, a warm/gold glow, "
                "and a positive, slightly saturated grade. No debris/rain/haze -- an UP story.",
        "blender": {"glare_mode": "STREAKS", "glare_strength": 0.5, "sun_beams": False,
                   "sun_beams_strength": 0.0, "color_balance_gain": (1.06, 1.02, 0.92), "vignette": 0.12},
        "natron": {"rain": False, "rain_density": 0.0, "rain_speed": 0.0, "rain_angle": 0.0,
                  "vignette_strength": 0.12, "grain_opacity": 0.04,
                  "grade_multiply": (1.07, 1.03, 0.9), "grade_offset": (0.01, 0.005, -0.01),
                  "glow": {"tint": (1.0, 0.85, 0.4), "amplitude": 0.32}, "chromatic_aberration": 0.0},
    },
    "night_city": {
        "story": "Cool blue-hour/night exterior -- practical window glow, deeper shadows.",
        "blender": {"glare_mode": "FOG_GLOW", "glare_strength": 0.3, "sun_beams": False,
                   "sun_beams_strength": 0.0, "color_balance_gain": (0.88, 0.95, 1.15), "vignette": 0.4},
        "natron": {"rain": False, "rain_density": 0.0, "rain_speed": 0.0, "rain_angle": 0.0,
                  "vignette_strength": 0.38, "grain_opacity": 0.1,
                  "grade_multiply": (0.85, 0.92, 1.18), "grade_offset": (-0.01, -0.005, 0.02),
                  "glow": {"tint": (0.5, 0.7, 1.0), "amplitude": 0.3}, "chromatic_aberration": 0.0},
    },
    "rainy_city": {
        "story": "Wet-street exterior -- heavier, more literal rain than financial_crisis, neutral (not "
                "necessarily negative) grade.",
        "blender": {"glare_mode": "FOG_GLOW", "glare_strength": 0.35, "sun_beams": False,
                   "sun_beams_strength": 0.0, "color_balance_gain": (0.95, 0.98, 1.05), "vignette": 0.3},
        "natron": {"rain": True, "rain_density": 0.7, "rain_speed": 0.8, "rain_angle": 10.0,
                  "vignette_strength": 0.3, "grain_opacity": 0.08,
                  "grade_multiply": (0.94, 0.97, 1.04), "grade_offset": (0.0, 0.0, 0.0),
                  "glow": None, "chromatic_aberration": 0.0},
    },
    "future_banking": {
        "story": "The future of banking -- atmospheric depth, cool practical/emissive glow, and a "
                "subtle futuristic treatment (faint chromatic aberration) rather than heavy sci-fi VFX.",
        "blender": {"glare_mode": "FOG_GLOW", "glare_strength": 0.38, "sun_beams": True,
                   "sun_beams_strength": 0.25, "color_balance_gain": (0.95, 1.0, 1.08), "vignette": 0.25},
        "natron": {"rain": False, "rain_density": 0.0, "rain_speed": 0.0, "rain_angle": 0.0,
                  "vignette_strength": 0.24, "grain_opacity": 0.03,
                  "grade_multiply": (0.94, 1.0, 1.09), "grade_offset": (0.0, 0.0, 0.01),
                  "glow": {"tint": (0.4, 0.8, 1.0), "amplitude": 0.3}, "chromatic_aberration": 0.15},
    },
    "dramatic_reveal": {
        "story": "A single beat-change/reveal shot -- strong sun-beam/god-ray emphasis, punchier "
                "contrast. Meant for ONE shot, not a whole sequence.",
        "blender": {"glare_mode": "FOG_GLOW", "glare_strength": 0.35, "sun_beams": True,
                   "sun_beams_strength": 0.45, "color_balance_gain": (1.02, 1.0, 0.98), "vignette": 0.3},
        "natron": {"rain": False, "rain_density": 0.0, "rain_speed": 0.0, "rain_angle": 0.0,
                  "vignette_strength": 0.28, "grain_opacity": 0.06,
                  "grade_multiply": (1.02, 1.0, 0.98), "grade_offset": (0.0, 0.0, 0.0),
                  "glow": {"tint": (1.0, 0.95, 0.85), "amplitude": 0.3}, "chromatic_aberration": 0.0},
    },
    "economic_recovery": {
        "story": "Things are improving -- a gentler, hopeful cousin of wealth_growth (less glow/streak "
                "intensity, warm but subdued grade -- for a 'recovering', not 'triumphant', beat).",
        "blender": {"glare_mode": "FOG_GLOW", "glare_strength": 0.22, "sun_beams": False,
                   "sun_beams_strength": 0.0, "color_balance_gain": (1.03, 1.01, 0.96), "vignette": 0.15},
        "natron": {"rain": False, "rain_density": 0.0, "rain_speed": 0.0, "rain_angle": 0.0,
                  "vignette_strength": 0.15, "grain_opacity": 0.04,
                  "grade_multiply": (1.03, 1.01, 0.96), "grade_offset": (0.005, 0.0, -0.005),
                  "glow": {"tint": (1.0, 0.9, 0.7), "amplitude": 0.15}, "chromatic_aberration": 0.0},
    },
}

QUALITY_LEVELS = {
    # grain_scale: independent per-tier grain multiplier (on top of the
    # preset's own grain_opacity) -- LOW/MEDIUM previews don't need full
    # grain fidelity, so this also shaves a little GMIC cost there.
    #
    # sun_beams: Blender's real CompositorNodeSunBeams is a genuine
    # radial-blur atmosphere effect but is the dominant cost in any preset
    # that uses it -- profiled directly (_profile_blender.py-style test):
    # 12.24s/frame with sun_beams vs 1.45s/frame without at HERO
    # (1080x1920), an ~8.4x cost multiplier, while Glare(FOG_GLOW) alone
    # only costs ~0.46s/frame. Sun Beams is reserved for HERO (rare,
    # important shots); LOW/MEDIUM fall back to Glare(FOG_GLOW) alone for
    # atmosphere/depth, which is visually close at a fraction of the cost.
    "LOW": {"scale": 0.35, "blender_samples": 1, "grain_scale": 0.3, "sun_beams": False},
    "MEDIUM": {"scale": 0.6, "blender_samples": 1, "grain_scale": 0.7, "sun_beams": False},
    "HERO": {"scale": 1.0, "blender_samples": 1, "grain_scale": 1.0, "sun_beams": True},
}


def resolve_preset(name: str, intensity: float = 1.0) -> dict:
    """Scale a preset's numeric knobs by `intensity` (0..1+) around each
    knob's neutral value -- 0 strength/vignette/grain/glow, and (1,1,1)
    for grade multiplies/color_balance_gain -- so intensity=0 is a no-op
    pass-through and intensity=1 is exactly the preset's authored look."""
    if name not in PRESETS:
        raise ValueError(f"unknown VFX preset '{name}', expected one of {sorted(PRESETS)}")
    base = PRESETS[name]

    def scale_scalar(v):
        return v * intensity

    def scale_triplet_from_one(t):
        return tuple(1.0 + (v - 1.0) * intensity for v in t)

    def scale_triplet_from_zero(t):
        return tuple(v * intensity for v in t)

    b = base["blender"]
    n = base["natron"]
    resolved = {
        "name": name, "intensity": intensity, "story": base["story"],
        "blender": {
            "glare_mode": b["glare_mode"], "glare_strength": scale_scalar(b["glare_strength"]),
            "sun_beams": b["sun_beams"], "sun_beams_strength": scale_scalar(b["sun_beams_strength"]),
            "color_balance_gain": scale_triplet_from_one(b["color_balance_gain"]),
            "vignette": scale_scalar(b["vignette"]),
        },
        "natron": {
            "rain": n["rain"], "rain_density": scale_scalar(n["rain_density"]),
            "rain_speed": n["rain_speed"], "rain_angle": n["rain_angle"],
            "vignette_strength": scale_scalar(n["vignette_strength"]),
            "grain_opacity": scale_scalar(n["grain_opacity"]),
            "grade_multiply": scale_triplet_from_one(n["grade_multiply"]),
            "grade_offset": scale_triplet_from_zero(n["grade_offset"]),
            "glow": ({"tint": n["glow"]["tint"], "amplitude": scale_scalar(n["glow"]["amplitude"])}
                    if n["glow"] else None),
            "chromatic_aberration": scale_scalar(n["chromatic_aberration"]),
        },
    }
    return resolved
