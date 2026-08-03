from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

import pytest

from app.config import settings
from app.pipeline import asset_engine, broll, scene_director as sd, storyboard
from app.schemas.scene import AssetCandidate
from app.schemas.video_spec import Niche, VideoSpec


def item(url: str, scene_id: str = "s1.b1", *, provider: str = "pexels",
         license_name: str = "Pexels License", commercial: str = "allowed",
         relevance: float = .9, specificity: float = .9) -> AssetCandidate:
    return AssetCandidate(
        source_url=url, provider_institution=provider, asset_type="image",
        license=license_name, commercial_use_status=commercial,
        attribution_requirement="Photographer Name", retrieval_date=date.today().isoformat(),
        scene_id=scene_id, relevance_score=relevance, confidence=.85,
        subject_specificity=specificity, visual_quality=.8, originality=.7,
        mobile_readability=.9)


def prepare(graph, monkeypatch):
    monkeypatch.setattr(settings(), "storyboard_engine_enabled", True)
    report = sd.decide(graph, VideoSpec(channel_id="k70_business",
        niche=Niche.business, topic="Costco", allow_ai_image=False))
    if graph.storyboard is None:
        graph.storyboard = storyboard.generate_semantic(graph, report)
    return graph


def test_query_uses_structured_storyboard_facts(graph, monkeypatch):
    prepare(graph, monkeypatch)
    beat = graph.storyboard.scenes[0]
    query = asset_engine.build_query(beat)
    assert "Costco" in query
    assert "1985" in query
    assert "hot dog" in query.lower()


def test_licensing_and_match_floor_reject_unsafe_or_thematic_stock():
    good = item("https://fixture/good.jpg")
    unclear = item("https://fixture/unclear.jpg", license_name="unknown",
                   commercial="unclear")
    generic = item("https://fixture/generic.jpg", relevance=.2, specificity=.1)
    ranked = asset_engine.rank([generic, unclear, good], minimum=.58)
    assert ranked == [good]
    assert asset_engine.rank_score(good) > asset_engine.rank_score(generic)


@pytest.mark.asyncio
async def test_content_addressed_cache_downloads_identical_url_once(tmp_path):
    calls = 0

    async def download(candidate, target):
        nonlocal calls
        calls += 1
        target.write_bytes(b"fixture image")
        return target

    candidate = item("https://fixture/exact.jpg")
    first = await asset_engine.cache(candidate, tmp_path, download)
    second = await asset_engine.cache(candidate.model_copy(), tmp_path, download)
    assert first == second
    assert calls == 1


@pytest.mark.asyncio
async def test_resolver_deduplicates_and_attaches_complete_provenance(
        graph, monkeypatch, tmp_path):
    prepare(graph, monkeypatch)
    shared = "https://fixture/shared.jpg"
    calls = []

    async def fetch(provider, query, beat):
        calls.append((beat.scene_id, provider))
        if provider != "government_public_domain":
            return []
        return [item(shared, beat.scene_id, provider=provider,
                     license_name="Public Domain"),
                item(f"https://fixture/{beat.scene_id}.jpg", beat.scene_id,
                     provider=provider, license_name="Public Domain", relevance=.82)]

    async def download(candidate, target):
        target.write_bytes(candidate.source_url.encode())
        return target

    paths = await asset_engine.resolve(graph, fetch, download, tmp_path)
    assert paths
    selected = [p.selected_source_url for p in graph.asset_provenance
                if p.status == "resolved"]
    assert len(selected) == len(set(selected))
    assert all(p.candidates and p.query and p.comparison
               for p in graph.asset_provenance)
    assert all(c.local_cache_path for p in graph.asset_provenance
               for c in p.candidates if c.source_url == p.selected_source_url)
    first_beat_calls = [provider for scene_id, provider in calls
                        if scene_id == graph.storyboard.scenes[0].scene_id]
    assert first_beat_calls == list(asset_engine.source_priority())[:-1]


@pytest.mark.asyncio
async def test_enabled_broll_refuses_unrelated_old_fallback(graph, monkeypatch):
    original = [(s.id, s.narration, s.duration_sec) for s in graph.scenes]
    monkeypatch.setattr(settings(), "multi_source_asset_engine_enabled", True)
    monkeypatch.setattr(settings(), "storyboard_engine_enabled", True)

    async def no_candidates(provider, query, beat):
        return []

    async def should_not_download(candidate, target):
        raise AssertionError("unresolved candidate must not download")

    monkeypatch.setattr(broll, "multi_source_candidates", no_candidates)
    monkeypatch.setattr(broll, "download_asset_candidate", should_not_download)
    spec = VideoSpec(channel_id="k70_business", niche=Niche.business,
                     topic="Costco", allow_ai_image=False)
    await broll.resolve_assets(graph, spec)
    assert all(scene.visual.type == "solid" and scene.visual.asset_path is None
               for scene in graph.scenes)
    assert all(item.status in {"ai_requested", "manual_review"}
               for item in graph.asset_provenance)
    assert all(item.candidates[-1].provider_institution == "ai_generation"
               for item in graph.asset_provenance)
    assert [(s.id, s.narration, s.duration_sec) for s in graph.scenes] == original


@pytest.mark.asyncio
async def test_disabled_gate_preserves_existing_resolver_call(graph, monkeypatch):
    monkeypatch.setattr(settings(), "multi_source_asset_engine_enabled", False)
    called = []

    async def existing(scene, idx, current_graph, spec, decision):
        called.append(scene.id)

    monkeypatch.setattr(broll, "_resolve", existing)
    await broll.resolve_assets(copy.deepcopy(graph), VideoSpec(
        channel_id="k70_business", niche=Niche.business, topic="Costco",
        allow_ai_image=False))
    assert called == [scene.id for scene in graph.scenes]
