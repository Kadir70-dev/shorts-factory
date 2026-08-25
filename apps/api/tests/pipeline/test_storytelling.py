"""Story structure rotation and the variety planner.

The property these tests exist to protect is NOT "the code runs" — it is that a
channel's uploads stop looking like each other. Both subsystems are seeded and
ledger-backed, so the meaningful assertions are about DISTRIBUTION across many
videos, not about any single call.
"""
from __future__ import annotations

import pytest

from app import state
from app.brand import load_theme
from app.director import structures
from app.pipeline import variety


# --------------------------------------------------------------------------- #
# Library
# --------------------------------------------------------------------------- #
def test_library_meets_the_minimum_variety_requirement():
    lib = structures.library()
    assert len(lib) >= 6, "the brief asks for at least 6 storytelling structures"
    assert len({s.id for s in lib}) == len(lib), "structure ids must be unique"


def test_every_structure_is_usable():
    for s in structures.library():
        assert s.beats, f"{s.id} has no beats"
        assert s.beats[0].role == "hook", f"{s.id} must open on a hook"
        assert s.beats[-1].role == "cta", f"{s.id} must close on the CTA"
        lo, hi = s.scenes
        assert 3 <= lo <= hi <= 9, f"{s.id} scene range {s.scenes} is implausible"
        assert s.hook_styles and s.cta_styles


def test_named_structures_from_the_brief_exist():
    ids = {s.id for s in structures.library()}
    for wanted in ("mystery_reveal_lesson", "timeline_twist_conclusion",
                   "problem_solution_impact", "myth_vs_reality", "before_after",
                   "hidden_strategy"):
        assert wanted in ids


# --------------------------------------------------------------------------- #
# Rotation
# --------------------------------------------------------------------------- #
def test_rotation_avoids_back_to_back_repeats(isolated_state):
    picks = [structures.choose(f"v{i}", "ch", "usa_business").id for i in range(12)]
    repeats = sum(1 for a, b in zip(picks, picks[1:]) if a == b)
    assert repeats == 0, f"consecutive uploads shared a structure: {picks}"


def test_rotation_spreads_across_the_library(isolated_state):
    picks = [structures.choose(f"v{i}", "ch", "usa_business").id for i in range(20)]
    assert len(set(picks)) >= 6, (
        f"only {len(set(picks))} distinct structures in 20 uploads: {set(picks)}")


def test_choice_is_deterministic_for_a_video(isolated_state):
    a = structures.choose("vid_abc", "ch", "usa_business", record=False)
    b = structures.choose("vid_abc", "ch", "usa_business", record=False)
    assert (a.id, a.scene_count, a.hook_style) == (b.id, b.scene_count, b.hook_style)


def test_niche_restrictions_are_honoured(isolated_state):
    # hidden_strategy is restricted to business-ish niches
    picks = {structures.choose(f"h{i}", "ch", "usa_history").id for i in range(25)}
    assert "hidden_strategy" not in picks


def test_forced_structure_wins_and_is_not_recorded(isolated_state):
    c = structures.choose("v1", "ch", "usa_business", forced="myth_vs_reality")
    assert c.id == "myth_vs_reality"
    assert "myth_vs_reality" not in state.recent("ch", structures.DIMENSION)


def test_unknown_forced_structure_is_a_clear_error(isolated_state):
    with pytest.raises(ValueError, match="unknown story structure"):
        structures.choose("v1", "ch", "usa_business", forced="not_a_structure")


# --------------------------------------------------------------------------- #
# Beat expansion
# --------------------------------------------------------------------------- #
def test_expansion_preserves_the_hook_and_the_close():
    s = structures.get("mystery_reveal_lesson")
    for n in (3, 4, 5, 6, 7, 8):
        plan = s.expand(n)
        assert len(plan) == n
        assert plan[0].role == "hook"
        assert plan[-1].role == "cta"


def test_shrinking_keeps_the_data_beats():
    s = structures.get("one_number_story")
    plan = s.expand(min(s.scenes))
    assert any(b.wants_data for b in plan), (
        "the data beats are the ones that become charts; dropping them first "
        "defeats the structure")


# --------------------------------------------------------------------------- #
# Variety
# --------------------------------------------------------------------------- #
def test_variety_rotates_every_dimension(isolated_state):
    theme = load_theme("k70")
    plans = [variety.plan(f"v{i}", "ch", theme) for i in range(16)]
    for dim in ("caption_animation", "transitions", "motion", "zoom", "grade",
                "cta_style"):
        values = [getattr(p, dim) for p in plans]
        assert len(set(values)) >= 3, (
            f"{dim} only produced {set(values)} across 16 uploads — that is a "
            "visible pattern")
        repeats = sum(1 for a, b in zip(values, values[1:]) if a == b)
        assert repeats <= 3, f"{dim} repeated back-to-back {repeats} times"


def test_variety_is_deterministic(isolated_state):
    theme = load_theme("k70")
    a = variety.plan("vid_x", "ch", theme, record=False)
    b = variety.plan("vid_x", "ch", theme, record=False)
    assert a.as_dict() == b.as_dict()


def test_apply_sets_transitions_and_motion(isolated_state, graph):
    theme = load_theme("k70")
    p = variety.plan(graph.meta.video_id, "ch", theme)
    variety.apply(graph, p)
    assert graph.scenes[0].transition_in == "cut", "the hook must not fade in"
    assert len(p.scene_transitions) == len(graph.scenes)
    assert graph.variety["caption_animation"] == p.caption_animation


def test_chart_beats_get_no_camera_motion(isolated_state, graph):
    theme = load_theme("k70")
    graph.scenes[1].visual.type = "dataviz"
    variety.apply(graph, variety.plan("v", "ch", theme))
    assert graph.scenes[1].visual.motion == "none", (
        "a chart is already animating; Ken Burns on top of it is just wobble")


def test_structure_steers_the_music_family(isolated_state):
    theme = load_theme("k70")
    choice = structures.choose("v", "ch", "usa_history", forced="mystery_reveal_lesson")
    families = {variety.plan(f"v{i}", "ch", theme, choice, record=False).music_family
                for i in range(10)}
    assert families <= set(choice.structure.music), (
        f"a mystery spine drew {families}, outside its preferred beds")
