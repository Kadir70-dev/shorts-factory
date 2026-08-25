from __future__ import annotations

import copy

from app.config import settings
from app.pipeline import scene_director as sd
from app.schemas.scene import Scene, SceneGraph, SceneMeta
from app.schemas.video_spec import Niche, VideoSpec


def graph_with(scene: Scene) -> SceneGraph:
    return SceneGraph(
        meta=SceneMeta(video_id="vi_test", channel_id="k70_business",
                       niche="usa_business", title="Visual intelligence", hook="Hook"),
        scenes=[scene, Scene(id="cta", narration="Follow for more.")])


def spec() -> VideoSpec:
    return VideoSpec(channel_id="k70_business", niche=Niche.business,
                     topic="visual intelligence", allow_ai_image=False)


def precise_scene() -> Scene:
    scene = Scene(id="literal", narration="Customers felt the pressure immediately.")
    scene.visual.broll_keywords = ["families comparing grocery prices at checkout"]
    scene.visual.visual_intent = "A family compares grocery prices at checkout."
    return scene


def test_feature_gate_is_off_by_default():
    assert settings().visual_intelligence_enabled is False


def test_disabled_public_path_is_identical_to_existing_policy(monkeypatch):
    original = graph_with(precise_scene())
    expected_graph = copy.deepcopy(original)
    actual_graph = copy.deepcopy(original)
    monkeypatch.setattr(settings(), "visual_intelligence_enabled", False)
    expected = sd._decide_existing(expected_graph, spec())
    actual = sd.decide(actual_graph, spec())
    assert actual == expected
    assert actual_graph == expected_graph


def test_enhanced_path_uses_precise_authored_subject(monkeypatch):
    graph = graph_with(precise_scene())
    monkeypatch.setattr(settings(), "visual_intelligence_enabled", True)
    report = sd.decide(graph, spec())
    assert graph.scenes[0].visual.strategy == sd.REAL
    assert "visual-intelligence" in graph.scenes[0].visual.decision_reason
    assert report.comparison is not None
    assert report.comparison.changed_scenes == ("literal",)


def test_generic_stock_phrase_is_not_promoted(monkeypatch):
    scene = Scene(id="generic", narration="Companies adapted quickly.")
    scene.visual.broll_keywords = ["business meeting", "corporate growth"]
    graph = graph_with(scene)
    monkeypatch.setattr(settings(), "visual_intelligence_enabled", True)
    sd.decide(graph, spec())
    assert graph.scenes[0].visual.strategy != sd.REAL


def test_comparison_is_read_only_and_reports_cost():
    graph = graph_with(precise_scene())
    before = copy.deepcopy(graph)
    report = sd.compare(graph, spec())
    assert graph == before
    assert report.changed_scenes == ("literal",)
    assert report.existing_ms >= 0 and report.enhanced_ms >= 0
    assert report.enhanced.score >= report.existing.score
