"""Ranked multi-source extension for the existing b-roll resolver.

This module only discovers, validates, ranks and caches candidates. Rendering,
composition, motion graphics and branding remain owned by their existing stages.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from ..config import settings
from ..schemas.scene import (AssetCandidate, AssetResolution, SceneGraph,
                             StoryboardScene)

SOURCE_PRIORITY = (
    "government_public_domain", "sec_regulatory", "company_ir",
    "wikimedia_commons", "pexels", "pixabay", "ai_generation",
)
SAFE_LICENSES = {
    "public domain", "us government work", "cc0", "cc by 2.0", "cc by 3.0",
    "cc by 4.0", "cc by-sa 2.0", "cc by-sa 3.0", "cc by-sa 4.0",
    "pexels license", "pixabay content license", "company press use",
}
Fetcher = Callable[[str, str, StoryboardScene], Awaitable[list[AssetCandidate]]]
Downloader = Callable[[AssetCandidate, Path], Awaitable[Path | None]]


def source_priority() -> tuple[str, ...]:
    configured = tuple(value.strip() for value in
                       settings().multi_source_asset_priority.split(",")
                       if value.strip())
    allowed = tuple(value for value in configured if value in SOURCE_PRIORITY)
    missing = tuple(value for value in SOURCE_PRIORITY if value not in allowed)
    return allowed + missing


def build_query(beat: StoryboardScene) -> str:
    """Build a subject-first query from structured facts, not generic themes."""
    fields: list[str] = [beat.company, beat.primary_entity]
    fields.extend(beat.secondary_entities[:2])
    fields.extend([beat.location, str(beat.year or "")])
    fields.extend(beat.financial_numbers[:2])
    # The narration carries the event/action that Phase 2 does not model separately.
    event = " ".join(re.findall(r"[A-Za-z][\w'-]+", beat.narration)[:12])
    fields.append(event)
    seen: set[str] = set()
    return " ".join(value.strip() for value in fields
                    if value and not (value.lower() in seen or seen.add(value.lower())))


def legal(candidate: AssetCandidate) -> bool:
    return (candidate.commercial_use_status == "allowed"
            and candidate.license.strip().lower() in SAFE_LICENSES)


def rank_score(candidate: AssetCandidate) -> float:
    """Narration and legal safety dominate the editorial quality dimensions."""
    safety = 1.0 if legal(candidate) else 0.0
    return round(
        candidate.relevance_score * .38 + safety * .24
        + candidate.subject_specificity * .14 + candidate.visual_quality * .10
        + candidate.originality * .07 + candidate.mobile_readability * .07, 6)


def eligible(candidate: AssetCandidate, minimum: float | None = None) -> bool:
    floor = settings().multi_source_asset_min_match if minimum is None else minimum
    return legal(candidate) and candidate.relevance_score >= floor


def rank(candidates: list[AssetCandidate], minimum: float | None = None
         ) -> list[AssetCandidate]:
    provider_order = {name: index for index, name in enumerate(source_priority())}
    return sorted((c for c in candidates if eligible(c, minimum)),
                  key=lambda c: (-rank_score(c),
                                 provider_order.get(c.provider_institution, 999),
                                 c.source_url))


def cache_path(candidate: AssetCandidate, cache_dir: Path) -> Path:
    """Content-address by source URL so duplicate downloads collapse globally."""
    suffix = Path(urlparse(candidate.source_url).path).suffix.lower()
    if suffix not in {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".pdf"}:
        suffix = {"video": ".mp4", "image": ".jpg", "document": ".pdf"}.get(
            candidate.asset_type, ".json")
    digest = hashlib.sha256(candidate.source_url.encode()).hexdigest()[:24]
    return cache_dir / f"asset_{digest}{suffix}"


async def cache(candidate: AssetCandidate, cache_dir: Path,
                downloader: Downloader) -> Path | None:
    target = cache_path(candidate, cache_dir)
    if target.is_file() and target.stat().st_size:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        downloaded = await downloader(candidate, target)
    except Exception:  # one source outage must become unresolved, not kill render
        downloaded = None
    if not downloaded or not downloaded.is_file() or not downloaded.stat().st_size:
        target.unlink(missing_ok=True)
        return None
    if downloaded != target:
        shutil.copy2(downloaded, target)
    return target


async def resolve(graph: SceneGraph, fetcher: Fetcher, downloader: Downloader,
                  cache_dir: Path | None = None,
                  providers: tuple[str, ...] | None = None) -> dict[str, str]:
    """Resolve semantic beats and return source-scene paths for broll.py."""
    if graph.storyboard is None:
        return {}
    root = cache_dir or settings().data_dir / "cache" / "multi_source"
    used_urls: set[str] = set()
    resolved_paths: dict[str, str] = {}
    provenance: list[AssetResolution] = []
    today = date.today().isoformat()
    for beat in graph.storyboard.scenes:
        query = build_query(beat)
        all_candidates: list[AssetCandidate] = []
        search_providers = providers or tuple(
            p for p in source_priority() if p != "ai_generation")
        for provider in search_providers:
            try:
                found = await fetcher(provider, query, beat)
            except Exception:  # provider isolation mirrors the established resolver
                found = []
            for candidate in found:
                # Provider adapters cannot omit or falsify the owning beat/date.
                candidate.scene_id = beat.scene_id
                candidate.retrieval_date = candidate.retrieval_date or today
            all_candidates.extend(found)
        ordered = rank(all_candidates)
        selected = next((c for c in ordered if c.source_url not in used_urls), None)
        local = await cache(selected, root, downloader) if selected else None
        if selected and local:
            selected.local_cache_path = str(local)
            used_urls.add(selected.source_url)
            resolved_paths.setdefault(beat.source_scene_id, str(local))
            status, selected_url = "resolved", selected.source_url
        else:
            status = "ai_requested" if beat.ai_broll_candidate else "manual_review"
            selected_url = None
            all_candidates.append(AssetCandidate(
                source_url=f"ai-request://{beat.scene_id}",
                provider_institution="ai_generation", asset_type="ai_request",
                license="pending generation", commercial_use_status="unclear",
                retrieval_date=today, scene_id=beat.scene_id, relevance_score=1.0,
                confidence=0.0, synthetic_status="requested"))
        provenance.append(AssetResolution(
            scene_id=beat.scene_id, query=query, status=status,
            selected_source_url=selected_url, candidates=all_candidates,
            comparison=("enhanced selected narration-specific licensed asset"
                        if selected_url else
                        "enhanced refused old generic-stock fallback")))
    graph.asset_provenance = provenance
    return resolved_paths
