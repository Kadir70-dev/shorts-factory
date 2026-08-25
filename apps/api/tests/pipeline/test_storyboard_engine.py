from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from app.config import settings
from app.pipeline import scene_director as sd
from app.pipeline import storyboard
from app.schemas.scene import Scene, SceneGraph, SceneMeta, StoryboardData, StoryboardScene
from app.schemas.video_spec import Niche, VideoSpec


def spec() -> VideoSpec:
    return VideoSpec(channel_id="k70_business", niche=Niche.business,
                     topic="Costco", allow_ai_image=False)


def graph() -> SceneGraph:
    first = Scene(
        id="s1",
        narration=("Costco held the price at $1.50 in 1985. "
                   "Customers in the United States kept coming back."),
        duration_sec=6.0, beat_role="evidence", transition_in="fade")
    first.visual.visual_intent = "Show Costco's durable customer promise."
    first.visual.broll_keywords = ["Costco food court customers buying hot dogs"]
    second = Scene(
        id="s2",
        narration="The low price was never the whole business model because memberships drove the economics while renewals compounded over time.",
        duration_sec=5.0, beat_role="mechanism")
    second.visual.scene_visual_type = "abstract"
    return SceneGraph(
        meta=SceneMeta(video_id="storyboard_test", channel_id="k70_business",
                       niche="usa_business", title="Costco", hook="The price held"),
        scenes=[first, second])


def test_semantic_split_handles_sentences_and_long_clauses():
    beats = storyboard.semantic_beats(graph().scenes[0].narration)
    assert beats == ["Costco held the price at $1.50 in 1985.",
                     "Customers in the United States kept coming back."]
    assert all(len(beat.split()) <= 22 for beat in storyboard.semantic_beats(
        "One very long financial explanation " * 12))


def test_gate_is_off_and_disabled_path_does_not_attach_storyboard(monkeypatch):
    source = graph()
    before = copy.deepcopy(source)
    monkeypatch.setattr(settings(), "storyboard_engine_enabled", False)
    sd.decide(source, spec())
    assert source.storyboard is None
    # Existing Visual Intelligence fields may change; narration/timing never do.
    assert [(s.id, s.narration, s.duration_sec) for s in source.scenes] == [
        (s.id, s.narration, s.duration_sec) for s in before.scenes]


def test_enabled_engine_attaches_one_valid_scene_per_beat(monkeypatch):
    source = graph()
    monkeypatch.setattr(settings(), "storyboard_engine_enabled", True)
    sd.decide(source, spec())
    assert source.storyboard is not None
    assert [beat.scene_id for beat in source.storyboard.scenes] == [
        "s1.b1", "s1.b2", "s2.b1"]
    beat = source.storyboard.scenes[0]
    assert beat.company == "Costco"
    assert beat.year == 1985
    assert beat.financial_numbers == ["$1.50"]
    assert beat.visual_objective
    assert beat.asset_priority
    assert 0.0 <= beat.visual_confidence_score <= 1.0
    assert beat.transition == "fade"


def test_storyboard_passes_downstream_without_mutating_render_scenes(monkeypatch):
    source = graph()
    original = [(scene.id, scene.narration, scene.duration_sec)
                for scene in source.scenes]
    monkeypatch.setattr(settings(), "storyboard_engine_enabled", True)
    sd.decide(source, spec())
    assert [(scene.id, scene.narration, scene.duration_sec)
            for scene in source.scenes] == original
    restored = SceneGraph.model_validate_json(source.model_dump_json())
    assert restored.storyboard == source.storyboard


def test_storyboard_validation_rejects_invalid_confidence_and_duplicate_ids():
    fields = dict(
        scene_id="s1.b1", source_scene_id="s1", narration="A valid beat.",
        duration_estimate=1.0, visual_objective="Show the subject.",
        recommended_visual_type="real", asset_priority=["exact_footage"],
        visual_confidence_score=0.8)
    scene = StoryboardScene(**fields)
    with pytest.raises(ValidationError, match="unique"):
        StoryboardData(scenes=[scene, scene.model_copy()])
    with pytest.raises(ValidationError):
        StoryboardScene(**{**fields, "visual_confidence_score": 1.1})
