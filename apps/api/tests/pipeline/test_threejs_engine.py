from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings
from app.pipeline import broll, threejs_engine
from app.schemas.scene import StoryboardScene
from app.schemas.video_spec import Niche, VideoSpec


def beat(narration: str, numbers: list[str], *, year=None) -> StoryboardScene:
    return StoryboardScene(
        scene_id="s1.b1", source_scene_id="s1", narration=narration,
        duration_estimate=2, visual_objective=narration,
        primary_entity="Acme", company="Acme", year=year,
        financial_numbers=numbers, recommended_visual_type="dataviz",
        motion_graphics_needed=True, threejs_candidate=True,
        asset_priority=["local_graphics"], visual_confidence_score=.9)


@pytest.mark.parametrize(("source", "numbers", "year", "template"), [
    ("Revenue reached $4.2 billion.", ["$4.2 billion"], None, "number_counter"),
    ("Revenue compared with profit.", ["$10M", "$4M"], None, "comparison_towers"),
    ("Insiders own a 35% stake.", ["35%", "65%"], None, "share_ownership"),
    ("The dividend cash flow reached $2M.", ["$2M"], None, "dividend_cashflow"),
    ("Since 1985 the business changed.", [], 1985, "timeline_flythrough"),
    ("Ten percent compounded growth.", ["10%"], None, "compound_growth"),
])
def test_schema_maps_all_focused_templates(source, numbers, year, template):
    mapped = threejs_engine.map_template(beat(source, numbers, year=year))
    assert mapped is not None and mapped.template == template


def test_non_candidate_or_unhelpful_beat_is_not_mapped():
    candidate = beat("The office opened.", [])
    assert threejs_engine.map_template(candidate) is None
    assert threejs_engine.map_template(candidate.model_copy(
        update={"threejs_candidate": False})) is None


def test_cache_key_is_seeded_deterministic_and_brand_sensitive(graph):
    candidate = beat("Revenue reached $4.2 billion.", ["$4.2 billion"])
    mapped = threejs_engine.map_template(candidate)
    first = threejs_engine.cache_key(graph, graph.scenes[0], candidate,
                                     mapped, "preview", 70)
    second = threejs_engine.cache_key(graph, graph.scenes[0], candidate,
                                      mapped, "preview", 70)
    changed = threejs_engine.cache_key(graph, graph.scenes[0], candidate,
                                       mapped, "preview", 71)
    assert first == second
    assert first != changed
    assert len(first) == 64


@pytest.mark.asyncio
async def test_cache_reuse_and_brand_provenance(graph, monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), "data_dir", tmp_path)
    candidate = beat("Revenue reached $4.2 billion.", ["$4.2 billion"])
    mapped = threejs_engine.map_template(candidate)
    key = threejs_engine.cache_key(graph, graph.scenes[0], candidate,
                                   mapped, "preview", 12)
    output = tmp_path / "cache" / "threejs" / key / "render.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"cached-render")
    result = await threejs_engine.render(graph, graph.scenes[0], candidate,
                                         quality="preview", seed=12)
    assert result.status == "cache_hit"
    assert result.render_path == str(output)
    assert result.brand_id == graph.brand_id
    assert result.brand_fingerprint
    assert (result.width, result.height) == (360, 640)


@pytest.mark.asyncio
async def test_render_failure_is_explicitly_unresolved(graph, monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), "data_dir", tmp_path)

    async def fail(_payload):
        raise RuntimeError("browser unavailable")

    monkeypatch.setattr(threejs_engine, "_worker_render", fail)
    result = await threejs_engine.render(
        graph, graph.scenes[0], beat("Revenue reached $4.2 billion.", ["$4.2B"]),
        quality="preview", seed=99)
    assert result.status == "unresolved"
    assert result.render_path is None
    assert "browser unavailable" in result.error


@pytest.mark.asyncio
async def test_disabled_gate_preserves_existing_asset_path(graph, monkeypatch, isolated_state):
    monkeypatch.setattr(settings(), "threejs_visual_engine_enabled", False)
    monkeypatch.setattr(settings(), "multi_source_asset_engine_enabled", False)
    calls = []

    async def existing(scene, idx, current_graph, spec, decision):
        calls.append(scene.id)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Three.js may not run while disabled")

    monkeypatch.setattr(broll, "_resolve", existing)
    monkeypatch.setattr(threejs_engine, "render", forbidden)
    await broll.resolve_assets(graph, VideoSpec(
        channel_id="k70_business", niche=Niche.business, topic="test",
        allow_ai_image=False))
    assert calls == [scene.id for scene in graph.scenes]
    assert graph.threejs_provenance == []


def test_mobile_text_contract_and_final_dimensions(graph):
    candidate = beat("Revenue reached $4.2 billion.", ["$4.2B"])
    candidate.company = "A" * 100
    candidate.overlay_text = ["B" * 200]
    mapped = threejs_engine.map_template(candidate)
    assert len(mapped.title) <= 48 and len(mapped.label) <= 72
    assert threejs_engine._quality_dimensions(graph, "final") == (
        graph.width, graph.height)
