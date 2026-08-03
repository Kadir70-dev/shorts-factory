from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.brand import load_theme
from app.config import settings
from app.pipeline import broll, finance_motion, threejs_engine
from app.schemas.scene import MotionGraphicsRenderProvenance, StoryboardScene
from app.schemas.video_spec import Niche, VideoSpec


def beat(text: str, numbers: list[str] | None = None, *, year=None,
         secondary: list[str] | None = None) -> StoryboardScene:
    return StoryboardScene(
        scene_id="s1.b1", source_scene_id="s1", narration=text,
        duration_estimate=.8, visual_objective=text, primary_entity="Acme",
        secondary_entities=secondary or [], company="Acme", year=year,
        financial_numbers=numbers or [], recommended_visual_type="motion_gfx",
        motion_graphics_needed=True, threejs_candidate=True,
        asset_priority=["local_graphics"], visual_confidence_score=.95)


@pytest.mark.parametrize(("candidate", "template"), [
    (beat("Revenue reached $4.2 billion.", ["$4.2 billion"]), "stat_card"),
    (beat("Revenue and costs compare at $10M and $6M.", ["$10M", "$6M"]), "bar_chart_comparison"),
    (beat("Founders own a 35% stake.", ["35%", "65%"]), "percentage_split"),
    (beat("Since 1985 the timeline changed.", year=1985), "timeline_events"),
    (beat("Before $4M and after $9M.", ["$4M", "$9M"]), "before_after"),
    (beat("Revenue and profit waterfall: $10M and $4M.", ["$10M", "$4M"]), "revenue_profit_waterfall"),
    (beat("Price inflation moved from $2 to $3.", ["$2", "$3"]), "price_inflation"),
    (beat("The 2024 SEC annual report document showed $8M.", ["$8M"], year=2024), "document_highlight"),
    (beat('The CEO said “discipline compounds.”'), "quote_card"),
    (beat("The company ecosystem links suppliers and its platform.",
          secondary=["Supplier One", "Platform Two", "Retailers"]), "company_ecosystem"),
])
def test_all_templates_map_only_real_storyboard_values(candidate, template):
    mapped = finance_motion.map_template(candidate)
    assert mapped is not None and mapped.template == template
    if candidate.financial_numbers:
        assert mapped.values


def test_unfounded_template_is_refused():
    assert finance_motion.map_template(beat("A generic office scene.")) is None


def test_seeded_frames_are_byte_deterministic(graph):
    candidate = beat("Revenue reached $4.2 billion.", ["$4.2 billion"])
    spec = finance_motion.map_template(candidate)
    theme = load_theme(graph.brand_id)
    a = list(finance_motion._frames(theme, spec, 120, 214, 2, 1.0, 77))
    b = list(finance_motion._frames(theme, spec, 120, 214, 2, 1.0, 77))
    assert [hashlib.sha256(frame.to_rgba()).hexdigest() for frame in a] == [
        hashlib.sha256(frame.to_rgba()).hexdigest() for frame in b]


def test_mobile_readability_contract(graph):
    candidate = beat("Revenue reached $4.2 billion.", ["$4.2 billion"])
    candidate.company = "X" * 120
    spec = finance_motion.map_template(candidate)
    assert len(spec.title) <= 56
    theme = load_theme(graph.brand_id)
    filters = finance_motion._filters(theme, spec, 360, 640, 1.0)
    assert filters
    assert theme.size("source", 640) >= 8
    assert finance_motion.dimensions("final") == (1080, 1920)


@pytest.mark.asyncio
async def test_cache_reuse_and_brand_provenance(graph, monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), "data_dir", tmp_path)
    candidate = beat("Revenue reached $4.2 billion.", ["$4.2 billion"])
    spec = finance_motion.map_template(candidate)
    key = finance_motion.cache_key(graph, graph.scenes[0], candidate,
                                   spec, "preview", 4)
    output = tmp_path / "cache" / "finance_motion" / key / "render.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"cached motion render")
    result = await finance_motion.render(graph, graph.scenes[0], candidate,
                                         quality="preview", seed=4)
    assert result.status == "cache_hit"
    assert result.render_path == str(output)
    assert result.brand_fingerprint and result.brand_id == graph.brand_id


@pytest.mark.asyncio
async def test_failure_is_unresolved(monkeypatch, graph, tmp_path):
    monkeypatch.setattr(settings(), "data_dir", tmp_path)

    async def fail(*args, **kwargs):
        raise RuntimeError("ffmpeg unavailable")

    monkeypatch.setattr(finance_motion, "write_video", fail)
    result = await finance_motion.render(
        graph, graph.scenes[0], beat("Revenue reached $4.2 billion.", ["$4.2B"]),
        quality="preview", seed=1)
    assert result.status == "unresolved"
    assert result.render_path is None
    assert "ffmpeg unavailable" in result.error


@pytest.mark.asyncio
async def test_2d_is_preferred_to_threejs_when_equally_clear(graph, monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), "motion_graphics_engine_enabled", True)
    monkeypatch.setattr(settings(), "threejs_visual_engine_enabled", True)
    monkeypatch.setattr(settings(), "multi_source_asset_engine_enabled", False)
    monkeypatch.setattr(settings(), "storyboard_engine_enabled", True)
    graph.scenes[0].narration = "Revenue reached $4.2 billion."
    fixture = tmp_path / "motion.mp4"; fixture.write_bytes(b"fixture")

    async def rendered(current_graph, scene, candidate, quality, seed):
        return MotionGraphicsRenderProvenance(
            scene_id=scene.id, storyboard_scene_id=candidate.scene_id,
            template="stat_card", template_version="test", status="rendered",
            render_path=str(fixture), cache_key="k", seed=seed, fps=30,
            width=360, height=640, quality="preview", brand_id="k70",
            brand_fingerprint="brand", render_ms=1, peak_rss_mb=1,
            clarity_reason="2D is clearer")

    async def forbidden(*args, **kwargs):
        raise AssertionError("Three.js must not replace an equally clear 2D graphic")

    monkeypatch.setattr(finance_motion, "render", rendered)
    monkeypatch.setattr(threejs_engine, "render", forbidden)
    await broll.resolve_assets(graph, VideoSpec(
        channel_id="k70_business", niche=Niche.business, topic="Revenue",
        allow_ai_image=False))
    assert graph.scenes[0].visual.type == "motion_gfx"
    assert graph.motion_graphics_provenance


@pytest.mark.asyncio
async def test_disabled_gate_preserves_phase4_path(graph, monkeypatch):
    monkeypatch.setattr(settings(), "motion_graphics_engine_enabled", False)
    monkeypatch.setattr(settings(), "threejs_visual_engine_enabled", False)
    monkeypatch.setattr(settings(), "multi_source_asset_engine_enabled", False)
    calls = []

    async def existing(scene, idx, current_graph, spec, decision):
        calls.append(scene.id)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Phase 5 may not run while disabled")

    monkeypatch.setattr(broll, "_resolve", existing)
    monkeypatch.setattr(finance_motion, "render", forbidden)
    await broll.resolve_assets(graph, VideoSpec(
        channel_id="k70_business", niche=Niche.business, topic="test",
        allow_ai_image=False))
    assert calls == [scene.id for scene in graph.scenes]
    assert graph.motion_graphics_provenance == []
