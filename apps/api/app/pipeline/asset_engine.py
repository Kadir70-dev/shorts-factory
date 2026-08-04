"""Ranked multi-source extension for the existing b-roll resolver.

This module only discovers, validates, ranks and caches candidates. Rendering,
composition, motion graphics and branding remain owned by their existing stages.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from ..config import settings
from ..schemas.scene import (AssetCandidate, AssetResolution, SceneGraph,
                             StoryboardScene)

# Only providers with a live adapter. government_public_domain, sec_regulatory
# and company_ir sat at the FRONT of this chain and returned [] on every call —
# there is no universal media API behind them that can supply explicit licence
# metadata, so they were placeholders. Each cost a scheduled discovery job per
# beat (3 providers x N beats of pure latency) and, worse, made the priority
# order a lie: the first three entries could never win. They come back when an
# institution-specific connector exists to fill them.
SOURCE_PRIORITY = (
    "wikimedia_commons", "pexels", "pixabay", "ai_generation",
)

# What the compositor can actually put on screen. A PDF ranks and downloads
# perfectly well and then fails at the ffmpeg stage, so it is rejected at
# selection time rather than after spending the bandwidth.
RENDERABLE_SUFFIXES = {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp"}
RENDERABLE_TYPES = {"image", "video"}
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


# Fashion nouns an archive actually indexes: material, process, facility and
# supply-chain stage. A query of "Zara two weeks store data" finds nothing in
# Wikimedia; "Zara garment factory sewing Spain" finds the real photograph.
_FASHION_SUBJECT = re.compile(
    r"\b(cotton|denim|leather|wool|silk|linen|cashmere|polyester|nylon|viscose|"
    r"yarn|fabric|textile|dye|dyed|undyed|greige|loom|weaving|knitting|"
    r"stitch\w*|sewing|seam|pattern|cutting|tailor\w*|atelier|workshop|factory|"
    r"mill|tannery|warehouse|distribution|container|freight|shipping|port|"
    r"logistics|sourcing|batch|sample|prototype|runway|collection|boutique|"
    r"retail|store|garment|apparel|shoe|sneaker|inspection)\b", re.I)


def build_query(beat: StoryboardScene) -> str:
    """Build a subject-first query from structured facts, not generic themes."""
    fields: list[str] = [beat.company, beat.primary_entity]
    fields.extend(beat.secondary_entities[:2])
    fields.extend([beat.location, str(beat.year or "")])
    fields.extend(beat.financial_numbers[:2])
    # Concrete subject nouns ahead of the narration text, so the archive search
    # keys off the thing being filmed rather than the sentence's grammar.
    fields.extend(list(dict.fromkeys(
        m.group(0).lower() for m in
        _FASHION_SUBJECT.finditer(f"{beat.narration} {beat.visual_objective}")))[:4])
    # The narration carries the event/action that Phase 2 does not model
    # separately. Six words, not twelve: `narration_match` scores an archive hit
    # by how much of THIS query it covers, so every extra grammar word lowered
    # the score of a perfectly good photograph until it fell under the floor.
    event = " ".join(re.findall(r"[A-Za-z][\w'-]+", beat.narration)[:6])
    fields.append(event)
    seen: set[str] = set()
    return " ".join(value.strip() for value in fields
                    if value and not (value.lower() in seen or seen.add(value.lower())))


def subject_query(beat: StoryboardScene) -> str:
    """Nouns only — the retry query. Brand/place/year plus the physical subject
    (material, process, facility, supply-chain stage), with no narration grammar
    to dilute the match score."""
    fields = [beat.company, beat.primary_entity, beat.location,
              str(beat.year or "")]
    fields.extend(list(dict.fromkeys(
        m.group(0).lower() for m in
        _FASHION_SUBJECT.finditer(f"{beat.narration} {beat.visual_objective}")))[:3])
    seen: set[str] = set()
    return " ".join(v.strip() for v in fields
                    if v and not (v.lower() in seen or seen.add(v.lower())))


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


def renderable(candidate: AssetCandidate) -> bool:
    """Can the compositor put this on screen at all?

    Checked BEFORE the download so a PDF costs nothing. The URL suffix is the
    only signal available pre-fetch; when it carries no extension the declared
    asset_type decides, which keeps API-served images (no suffix in the URL)
    reachable while still excluding anything typed as a document.
    """
    suffix = Path(urlparse(candidate.source_url).path).suffix.lower()
    if suffix:
        return suffix in RENDERABLE_SUFFIXES
    return candidate.asset_type in RENDERABLE_TYPES


async def cache(candidate: AssetCandidate, cache_dir: Path,
                downloader: Downloader) -> Path | None:
    if not renderable(candidate):
        return None
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
        # The provider cache already holds these exact bytes under sha1(url);
        # copying them again stored every asset twice. A hard link gives the
        # second name for free and cannot drift from the first. copy2 remains
        # the fallback for a cache on a different filesystem.
        try:
            target.unlink(missing_ok=True)
            os.link(downloaded, target)
        except OSError:
            shutil.copy2(downloaded, target)
    return target


def intent_key(beat: StoryboardScene) -> str:
    """What this beat is ASKING for, independent of which asset won.

    Both queries plus the owning scene — exactly the inputs that decide what is
    searched for. Unchanged intent means the licensed asset already chosen is
    still the right one, so re-running the search would spend the network to
    arrive back where it started.
    """
    body = json.dumps({"query": build_query(beat), "retry": subject_query(beat),
                       "scene": beat.source_scene_id},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def _reuse_candidate(record: dict) -> AssetCandidate | None:
    """Rebuild the recorded selection, licence and attribution intact.

    Every provenance field is restored verbatim from the manifest — nothing is
    re-derived or defaulted — so a reused asset carries exactly the licence,
    attribution requirement, institution and retrieval date it was originally
    accepted under.
    """
    local = record.get("local_cache_path", "")
    if not local or not Path(local).is_file() or not Path(local).stat().st_size:
        return None
    try:
        return AssetCandidate.model_validate(record["candidate"])
    except (KeyError, ValueError):
        return None


async def resolve(graph: SceneGraph, fetcher: Fetcher, downloader: Downloader,
                  cache_dir: Path | None = None,
                  providers: tuple[str, ...] | None = None) -> dict[str, str]:
    """Resolve semantic beats and return source-scene paths for broll.py."""
    if graph.storyboard is None:
        return {}
    manifest_path = (settings().data_dir / "jobs" / graph.meta.video_id
                     / "asset_manifest.json")
    prior_assets: dict[str, dict] = {}
    try:
        prior_assets = json.loads(manifest_path.read_text()).get("beats", {})
    except (OSError, ValueError):
        prior_assets = {}
    asset_records: dict[str, dict] = {}
    reused_count = 0
    root = cache_dir or settings().data_dir / "cache" / "multi_source"
    used_urls: set[str] = set()
    resolved_paths: dict[str, str] = {}
    provenance: list[AssetResolution] = []
    today = date.today().isoformat()
    search_providers = providers or tuple(
        p for p in source_priority() if p != "ai_generation")
    discovered: dict[tuple[str, str], list[AssetCandidate]] = {}
    if settings().production_optimizer_enabled:
        from .production_optimizer import scheduler
        jobs = [(beat, provider) for beat in graph.storyboard.scenes
                for provider in search_providers]
        async def discover(beat, provider):
            try: return await fetcher(provider, build_query(beat), beat)
            except Exception: return []
        results = await scheduler.map("asset_discovery", [
            (lambda beat=beat, provider=provider: discover(beat, provider))
            for beat, provider in jobs], kind="io", memory_mb=80)
        discovered = {(beat.scene_id, provider): found
                      for (beat, provider), found in zip(jobs, results)}
    for beat in graph.storyboard.scenes:
        query = build_query(beat)
        all_candidates: list[AssetCandidate] = []

        # Unchanged intent + the licensed file still on disk = keep it. This
        # skips discovery entirely, which is the whole cost of this stage.
        key = intent_key(beat)
        record = prior_assets.get(beat.scene_id, {})
        if record.get("intent") == key and record.get("url") not in used_urls:
            reused = _reuse_candidate(record)
            if reused is not None:
                used_urls.add(reused.source_url)
                resolved_paths.setdefault(beat.source_scene_id,
                                          reused.local_cache_path)
                asset_records[beat.scene_id] = record
                reused_count += 1
                provenance.append(AssetResolution(
                    scene_id=beat.scene_id, query=record.get("query", query),
                    status="resolved", selected_source_url=reused.source_url,
                    candidates=[reused],
                    comparison="reused previously selected licensed asset"))
                continue

        for provider in search_providers:
            if settings().production_optimizer_enabled:
                found = discovered[(beat.scene_id, provider)]
            else:
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
        # ONE retry per beat, nouns only. An archive that holds the right
        # photograph still answers "nothing" to a sentence-shaped query; this is
        # the difference between an official asset and falling through the floor.
        retry = subject_query(beat)
        if selected is None and retry and retry != query:
            # The providers are independent HTTP calls, so the retry ran N
            # round-trips back to back for no reason. Still exactly ONE retry
            # per beat — the fan-out is across providers, not extra attempts.
            async def retry_one(provider: str) -> list[AssetCandidate]:
                try:
                    return await fetcher(provider, retry, beat)
                except Exception:  # provider isolation, as above
                    return []
            for found in await asyncio.gather(
                    *(retry_one(provider) for provider in search_providers)):
                for candidate in found:
                    candidate.scene_id = beat.scene_id
                    candidate.retrieval_date = candidate.retrieval_date or today
                all_candidates.extend(found)
            ordered = rank(all_candidates)
            selected = next((c for c in ordered if c.source_url not in used_urls),
                            None)
            if selected is not None:
                query = f"{query} ⟲ {retry}"
        local = await cache(selected, root, downloader) if selected else None
        if selected and local:
            selected.local_cache_path = str(local)
            used_urls.add(selected.source_url)
            resolved_paths.setdefault(beat.source_scene_id, str(local))
            status, selected_url = "resolved", selected.source_url
            asset_records[beat.scene_id] = {
                "intent": key, "query": query, "url": selected.source_url,
                "local_cache_path": str(local),
                "candidate": selected.model_dump(mode="json")}
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
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(
            {"video_id": graph.meta.video_id, "beats": asset_records}, indent=2))
    except OSError as exc:            # a lost manifest only costs a re-search
        print(f"[assets] could not write manifest: {exc}", flush=True)
    print(f"[assets] {reused_count} reused, "
          f"{len(asset_records) - reused_count} newly resolved", flush=True)
    return resolved_paths
