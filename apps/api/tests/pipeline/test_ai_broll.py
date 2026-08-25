from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings
from app.pipeline import ai_broll, broll
from app.schemas.scene import (AIBrollRenderProvenance, StoryboardData,
                               StoryboardScene)
from app.schemas.video_spec import Niche, VideoSpec


def beat(text: str = "Show a symbolic supply-chain bottleneck.", *, sid="s1.b1",
         source="s1") -> StoryboardScene:
    return StoryboardScene(
        scene_id=sid, source_scene_id=source, narration=text,
        duration_estimate=2, visual_objective=text, primary_entity="Supply chain",
        secondary_entities=["Factory", "Port"], company="Acme",
        location="United States", year=2024, financial_numbers=["$4 billion"],
        emotion="tense", recommended_visual_type="ai_image",
        threejs_candidate=False, ai_broll_candidate=True,
        asset_priority=["ai_recreation"], visual_confidence_score=.82)


class Adapter:
    name = "fixture_provider"

    def __init__(self, path: Path, *, fail=False):
        self.path, self.fail, self.calls = path, fail, 0

    def available(self): return True
    def model(self): return "fixture-v1"

    async def generate(self, prompt, scene, quality):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider offline")
        self.path.write_bytes(b"synthetic fixture")
        return ai_broll.GeneratedAsset(str(self.path), self.model(), "image")


def test_prompt_contains_complete_cinematic_contract(graph):
    spec = ai_broll.prompt_spec(graph, graph.scenes[0], beat())
    assert "Supply chain" in spec.cinematic_prompt
    assert "fabricated evidence" in spec.negative_prompt
    assert spec.camera_angle and spec.focal_length and spec.lighting
    assert len(spec.color_palette) >= 4
    assert spec.composition and spec.movement and spec.mood
    assert spec.realism_level == "photorealistic"
    assert spec.brand_style and spec.duration == graph.scenes[0].duration_sec
    assert spec.aspect_ratio == "9:16"


def test_provider_selection_is_configurable_and_plugin_based(monkeypatch, tmp_path):
    adapter = Adapter(tmp_path / "asset.png")
    monkeypatch.setitem(ai_broll._REGISTRY, adapter.name, adapter)
    monkeypatch.setattr(settings(), "ai_broll_provider_priority",
                        "missing,fixture_provider,flux")
    selected = ai_broll.select_providers()
    assert selected[0] is adapter


def test_continuity_reuses_seed_palette_lighting_lens_and_camera(graph):
    first = ai_broll.prompt_spec(graph, graph.scenes[0], beat())
    second = ai_broll.prompt_spec(
        graph, graph.scenes[1], beat("Show a quiet warehouse at night.",
                                    sid="s2.b1", source="s2"))
    assert first.continuity_seed == second.continuity_seed
    assert first.color_palette == second.color_palette
    assert first.lighting == second.lighting
    assert first.focal_length == second.focal_length
    assert first.camera_angle == second.camera_angle
    assert first.movement == second.movement


@pytest.mark.asyncio
async def test_generation_provenance_and_content_cache(graph, monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), "data_dir", tmp_path)
    adapter = Adapter(tmp_path / "provider.png")
    monkeypatch.setitem(ai_broll._REGISTRY, adapter.name, adapter)
    monkeypatch.setattr(settings(), "ai_broll_provider_priority", adapter.name)
    first = await ai_broll.generate(graph, graph.scenes[0], beat(), quality="preview")
    second = await ai_broll.generate(graph, graph.scenes[0], beat(), quality="preview")
    assert first.status == "rendered" and first.synthetic is True
    assert first.provider == adapter.name and first.model == "fixture-v1"
    assert first.render_path and Path(first.render_path).is_file()
    assert first.prompt_generation_ms >= 0 and first.provider_dispatch_ms >= 0
    assert second.status == "cache_hit"
    assert second.cache_key == first.cache_key
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_provider_failure_is_unresolved(graph, monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), "data_dir", tmp_path)
    adapter = Adapter(tmp_path / "never.png", fail=True)
    monkeypatch.setitem(ai_broll._REGISTRY, adapter.name, adapter)
    monkeypatch.setattr(settings(), "ai_broll_provider_priority", adapter.name)
    result = await ai_broll.generate(graph, graph.scenes[0], beat())
    assert result.status == "unresolved"
    assert result.render_path is None
    assert "provider offline" in result.error


@pytest.mark.asyncio
async def test_real_people_and_documents_are_rejected(graph, monkeypatch):
    monkeypatch.setattr(settings(), "ai_broll_provider_priority", "")
    person = await ai_broll.generate(
        graph, graph.scenes[0], beat("The CEO Warren Buffett entered the room."))
    document = await ai_broll.generate(
        graph, graph.scenes[0], beat("Show the leaked document as historical evidence."))
    assert person.status == "rejected"
    assert document.status == "rejected"


@pytest.mark.asyncio
async def test_failed_ai_never_uses_stock_for_primary_scene(graph, monkeypatch):
    monkeypatch.setattr(settings(), "ai_broll_engine_enabled", True)
    monkeypatch.setattr(settings(), "multi_source_asset_engine_enabled", False)
    monkeypatch.setattr(settings(), "motion_graphics_engine_enabled", False)
    monkeypatch.setattr(settings(), "threejs_visual_engine_enabled", False)
    graph.storyboard = StoryboardData(scenes=[beat()])
    stock_scenes = []

    async def unresolved(current_graph, scene, candidate, quality=None):
        prompt = ai_broll.prompt_spec(current_graph, scene, candidate)
        return AIBrollRenderProvenance(
            scene_id=scene.id, storyboard_scene_id=candidate.scene_id,
            status="unresolved", provider="fixture", model="offline",
            asset_type="image", cache_key="key", prompt_spec=prompt,
            quality="final", prompt_generation_ms=1, provider_dispatch_ms=1,
            peak_rss_mb=1, error="offline")

    async def no_video(terms, duration, index):
        stock_scenes.append(index); return None

    async def no_image(terms, index): return None
    monkeypatch.setattr(ai_broll, "generate", unresolved)
    monkeypatch.setattr(broll, "_video", no_video)
    monkeypatch.setattr(broll, "_image", no_image)
    await broll.resolve_assets(graph, VideoSpec(
        channel_id="k70_business", niche=Niche.business, topic="Supply chain",
        allow_ai_image=True))
    # The guarantee this test is named for: a failed AI beat must NEVER be
    # papered over with unrelated stock footage.
    assert 0 not in stock_scenes
    assert graph.scenes[0].visual.type not in ("broll", "image")
    # It must also not be left blank. `solid` used to be the outcome here, which
    # shipped an empty frame; the dispatcher now falls the beat to a
    # self-rendered visual that still explains the line.
    assert graph.scenes[0].visual.type != "solid"
    assert graph.ai_broll_provenance[0].status == "unresolved"


@pytest.mark.asyncio
async def test_disabled_gate_preserves_phase5_path(graph, monkeypatch, isolated_state):
    monkeypatch.setattr(settings(), "ai_broll_engine_enabled", False)
    monkeypatch.setattr(settings(), "multi_source_asset_engine_enabled", False)
    monkeypatch.setattr(settings(), "motion_graphics_engine_enabled", False)
    monkeypatch.setattr(settings(), "threejs_visual_engine_enabled", False)
    called = []

    async def existing(scene, idx, current_graph, spec, decision): called.append(scene.id)
    async def forbidden(*args, **kwargs): raise AssertionError("AI B-roll ran while disabled")
    monkeypatch.setattr(broll, "_resolve", existing)
    monkeypatch.setattr(ai_broll, "generate", forbidden)
    await broll.resolve_assets(graph, VideoSpec(
        channel_id="k70_business", niche=Niche.business, topic="test",
        allow_ai_image=True))
    assert called == [scene.id for scene in graph.scenes]
    assert graph.ai_broll_provenance == []
