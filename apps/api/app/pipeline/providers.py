"""
External visual provider adapters. ALL behind plain async functions so the pipeline
never imports a vendor SDK directly. v1 ships real pexels/pixabay/manim;
veo3/seedance are stubs that raise unless wired (cost gate).
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from ..config import settings
from ..schemas.scene import AssetCandidate, StoryboardScene

# Wikimedia enforces its robot policy on the anonymous API: a request without a
# descriptive User-Agent is answered 403 (phabricator T400119), which silently
# emptied the official/public-domain tier for every beat. Contact string per
# https://w.wiki/4wJS.
WIKIMEDIA_UA = ("shorts-factory/1.0 (https://github.com/Kadir70-dev/shorts-factory; "
                "kadirab1999@gmail.com) httpx")

# --- download admission control (see `_download`) --------------------------- #
# Wikimedia's robot policy is about CONCURRENCY, not volume: a burst is throttled
# where the same requests spread over time are served. Two in flight keeps the
# official/public-domain tier reachable without slowing a render measurably.
_WIKIMEDIA_HOSTS = frozenset({"upload.wikimedia.org", "commons.wikimedia.org"})
_WIKIMEDIA_TRANSFERS = asyncio.Semaphore(2)
# Only these statuses are worth a second attempt; 403/404 are settled answers.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_DOWNLOAD_ATTEMPTS = 2                  # one try, one retry
_DOWNLOAD_BACKOFF_S = 2.0               # doubled per attempt; `Retry-After` wins
# Whole-fetch deadline, independent of httpx's per-read timeout. Generous enough
# for a 1080p stock clip on a slow line, hard enough that one bad CDN connection
# cannot hold a 156-beat render open indefinitely.
_DOWNLOAD_DEADLINE_S = 90.0
_MEDIA_TYPES = ("image/", "video/", "application/octet-stream")
# A 1.6 KB "image" decodes cleanly and still cannot fill a 1080x1920 frame. The
# floor rejects thumbnails and throttling notices before either reaches cache.
_MIN_ASSET_BYTES = 8_192


def _retry_delay(response: "httpx.Response", attempt: int) -> float:
    """Honour `Retry-After` when the server sends one, else exponential."""
    header = response.headers.get("retry-after", "").strip()
    if header.isdigit():
        return min(30.0, float(header))
    return _DOWNLOAD_BACKOFF_S * (2 ** attempt)


# --------------------------------------------------------------------------- #
# PROVIDER AVAILABILITY — decided ONCE per run, not re-discovered per scene.
#
# A long-form episode asks the resolver for assets 150+ times. Without this, a
# provider that is unconfigured or has gone down is re-attempted on every single
# beat, and each attempt pays the full connect/read timeout before falling
# through. On a 156-beat graph that is the difference between seconds and an
# hour of waiting for answers already known.
#
# Two separate ideas, deliberately:
#   configured() — static: is there a key / is the provider switched on. Free of
#                  charge to check, so it is checked before any network call.
#   is_down()    — dynamic: this provider has failed repeatedly DURING THIS RUN.
#                  Cleared on process exit; nothing is persisted, because a
#                  provider being down for one render says nothing about the next.
# --------------------------------------------------------------------------- #
_FAILURE_LIMIT = 2            # consecutive failures before a provider is parked
_run_failures: dict[str, int] = {}
_run_reasons: dict[str, str] = {}


def configured(provider: str) -> bool:
    """Is this provider usable at all on this machine? No network involved."""
    s = settings()
    if provider in ("wikimedia_commons", "pollinations"):
        return bool(s.pollinations_enabled) if provider == "pollinations" else True
    if provider == "pexels":
        return bool(s.pexels_api_key)
    if provider == "pixabay":
        return bool(s.pixabay_api_key)
    if provider == "google_ai":
        return bool(s.google_api_key)
    if provider == "huggingface":
        return bool(s.hf_api_token)
    if provider == "comfyui":
        return bool(s.comfyui_enabled and s.comfyui_base_url)
    return True               # unknown providers are not pre-judged


def is_down(provider: str) -> bool:
    """Has this provider failed enough times this run to stop asking?"""
    return _run_failures.get(provider, 0) >= _FAILURE_LIMIT


def available(provider: str) -> bool:
    return configured(provider) and not is_down(provider)


def note_failure(provider: str, error: BaseException | str) -> None:
    """Record a failed attempt. The provider is parked after `_FAILURE_LIMIT`."""
    reason = (f"{type(error).__name__}: {error}" if isinstance(error, BaseException)
              else str(error))
    _run_failures[provider] = _run_failures.get(provider, 0) + 1
    _run_reasons[provider] = reason[:160]
    if is_down(provider):
        print(f"[providers] {provider} parked for this run after "
              f"{_FAILURE_LIMIT} failures — {reason[:120]}", flush=True)


def note_success(provider: str) -> None:
    """A success clears the strike count: a blip must not park a live provider."""
    _run_failures.pop(provider, None)
    _run_reasons.pop(provider, None)


def availability_report() -> str:
    """One line per provider, for the run log."""
    names = ("wikimedia_commons", "pexels", "pixabay", "pollinations",
             "google_ai", "huggingface", "comfyui")
    rows = []
    for name in names:
        if not configured(name):
            state = "unconfigured — skipped without a network call"
        elif is_down(name):
            state = f"DOWN this run — {_run_reasons.get(name, '')}"
        else:
            state = "available"
        rows.append(f"  {name:20} {state}")
    return "provider availability\n" + "\n".join(rows)


async def multi_source_candidates(provider: str, query: str,
                                  beat: StoryboardScene) -> list[AssetCandidate]:
    """Discover typed candidates for the provenance-aware b-roll extension.

    Official/government, SEC and company-IR collections do not expose one safe
    universal media API, so those adapters intentionally return no result until
    an institution-specific connector can supply explicit licence metadata.
    They remain ahead of library sources in the resolver priority.
    """
    today = date.today().isoformat()

    def narration_match(metadata: str) -> float:
        stop = {"the", "a", "an", "and", "or", "at", "in", "of", "to",
                "for", "from", "since", "its", "it", "was"}
        wanted = {word for word in re.findall(r"[a-z0-9]+", query.lower())
                  if len(word) > 2 and word not in stop}
        offered = set(re.findall(r"[a-z0-9]+", metadata.lower()))
        coverage = len(wanted & offered) / max(1, len(wanted))
        return round(min(.96, .30 + .70 * coverage), 3)

    def candidate(url: str, institution: str, license_name: str,
                  relevance: float, quality: float = .75) -> AssetCandidate:
        return AssetCandidate(
            source_url=url, provider_institution=institution, asset_type="image",
            license=license_name, commercial_use_status="allowed",
            retrieval_date=today, scene_id=beat.scene_id,
            relevance_score=relevance, confidence=.8,
            subject_specificity=relevance, visual_quality=quality,
            originality=.65, mobile_readability=.8)

    # Answer from what this run already knows before opening a socket.
    if not available(provider):
        return []

    if provider == "wikimedia_commons":
        try:
            async with httpx.AsyncClient(
                    timeout=30, headers={"User-Agent": WIKIMEDIA_UA}) as client:
                response = await client.get("https://commons.wikimedia.org/w/api.php",
                    params={"action": "query", "generator": "search", "gsrsearch": query,
                            "gsrnamespace": 6, "gsrlimit": 10, "prop": "imageinfo",
                            "iiprop": "url|extmetadata", "format": "json"})
        except (httpx.HTTPError, OSError) as e:
            note_failure(provider, e)
            return []
        if response.status_code != 200:
            note_failure(provider, f"HTTP {response.status_code}")
            return []
        note_success(provider)
        out = []
        for page in response.json().get("query", {}).get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            license_name = (meta.get("LicenseShortName") or {}).get("value", "")
            url = info.get("thumburl") or info.get("url")
            if url:
                description = " ".join((page.get("title", ""),
                    (meta.get("ImageDescription") or {}).get("value", "")))
                item = candidate(url, provider, license_name,
                                 narration_match(description))
                item.attribution_requirement = (meta.get("Artist") or {}).get("value", "")
                out.append(item)
        return out
    if provider == "pexels":
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get("https://api.pexels.com/v1/search",
                    headers={"Authorization": settings().pexels_api_key},
                    params={"query": query, "orientation": "portrait", "per_page": 10})
        except (httpx.HTTPError, OSError) as e:
            note_failure(provider, e)
            return []
        if response.status_code != 200:
            note_failure(provider, f"HTTP {response.status_code}")
            return []
        note_success(provider)
        return [candidate((p.get("src") or {}).get("portrait", ""), provider,
                          "Pexels License", narration_match(p.get("alt", "")), .82)
                for p in response.json().get("photos", [])
                if (p.get("src") or {}).get("portrait")]
    if provider == "pixabay":
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get("https://pixabay.com/api/",
                    params={"key": settings().pixabay_api_key, "q": query,
                            "image_type": "photo", "orientation": "vertical",
                            "safesearch": "true", "per_page": 10})
        except (httpx.HTTPError, OSError) as e:
            note_failure(provider, e)
            return []
        if response.status_code != 200:
            note_failure(provider, f"HTTP {response.status_code}")
            return []
        note_success(provider)
        return [candidate(h.get("largeImageURL") or h.get("webformatURL"), provider,
                          "Pixabay Content License",
                          narration_match(h.get("tags", "")), .78)
                for h in response.json().get("hits", [])
                if h.get("largeImageURL") or h.get("webformatURL")]
    return []


async def download_asset_candidate(candidate: AssetCandidate, target: Path
                                   ) -> Path | None:
    """Download through the existing content-addressed provider cache."""
    ext = target.suffix.lstrip(".") or "bin"
    cached = Path(await _download(candidate.source_url, ext))
    return cached if cached.is_file() else None


# ----------------------------- B-roll -------------------------------------- #
# Real-footage engine. Four search adapters (Pexels/Pixabay × video/image) feed
# the asset resolver's priority chain. Each returns a LOCAL file path or None.
#
#   pick: candidate index — lets the resolver hand adjacent scenes *different*
#         clips for the same query so the video doesn't repeat itself, while
#         staying deterministic (same pick -> same clip).
#
# Per-process caches keep it fast & cheap: search results are memoised by query
# (one API call per unique query per run) and downloads are content-addressed
# (one file per unique URL, ever — see _download).

_SEARCH_CACHE: dict[str, list[str]] = {}
_SEARCH_LOCKS: dict[str, asyncio.Lock] = {}
_DL_LOCKS: dict[str, asyncio.Lock] = {}


# Stock-library results churn slowly — a query answered today answers the same
# tomorrow. The in-process memo only ever survived one render, so every re-run
# paid the same API round-trips again. A day on disk is long enough to make
# re-renders free and short enough that new uploads still surface.
_SEARCH_TTL_SECONDS = 86_400


def _search_cache_file(key: str) -> Path:
    path = settings().data_dir / "cache" / "provider_search"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{hashlib.sha1(key.encode()).hexdigest()}.json"


def _search_from_disk(key: str) -> list[str] | None:
    entry = _search_cache_file(key)
    try:
        payload = json.loads(entry.read_text())
    except (OSError, ValueError):
        return None
    if time.time() - float(payload.get("fetched_at", 0)) > _SEARCH_TTL_SECONDS:
        return None
    urls = payload.get("urls")
    return urls if isinstance(urls, list) else None


def _search_to_disk(key: str, urls: list[str]) -> None:
    entry = _search_cache_file(key)
    tmp = entry.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps({"key": key, "fetched_at": time.time(),
                                   "urls": urls}))
        tmp.replace(entry)                  # atomic: no torn read
    except OSError as exc:                  # a cache miss is always survivable
        tmp.unlink(missing_ok=True)
        _log(f"search cache store failed ({type(exc).__name__}): {exc}")


async def _cached_search(key: str, fetch) -> list[str]:
    """Memoise a candidate-URL list per query, in process and on disk.

    A per-key lock collapses concurrent identical searches into one API call.
    An empty result is NOT persisted: a provider outage would otherwise be
    cached as "this query has no assets" for a full day.
    """
    if key in _SEARCH_CACHE:
        return _SEARCH_CACHE[key]
    lock = _SEARCH_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        if key in _SEARCH_CACHE:
            return _SEARCH_CACHE[key]
        stored = _search_from_disk(key)
        if stored is not None:
            _SEARCH_CACHE[key] = stored
            return stored
        try:
            urls = await fetch()
        except Exception:
            urls = []
        _SEARCH_CACHE[key] = urls
        if urls:
            _search_to_disk(key, urls)
        return urls


async def _pick_download(urls: list[str], pick: int, ext: str) -> str | None:
    if not urls:
        return None
    return await _download(urls[pick % len(urls)], ext)


async def pexels_video(query: str, min_dur: float, pick: int = 0) -> str | None:
    key = settings().pexels_api_key
    if not available("pexels"):       # unkeyed, or already parked this run
        return None

    async def fetch() -> list[str]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": key},
                params={"query": query, "orientation": "portrait",
                        "size": "medium", "per_page": 15},
            )
        if r.status_code != 200:
            return []
        vids = r.json().get("videos", [])
        long_enough = [v for v in vids if v.get("duration", 0) >= min_dur] or vids
        urls: list[str] = []
        for v in long_enough:
            files = sorted(v.get("video_files", []),
                           key=lambda f: f.get("height", 0), reverse=True)
            # tallest file that isn't oversized (<=1920h) keeps download light
            pref = [f for f in files if f.get("height", 0) <= 1920] or files
            if pref:
                urls.append(pref[0]["link"])
        return urls

    urls = await _cached_search(f"pexvid:{min_dur:.0f}:{query}", fetch)
    return await _pick_download(urls, pick, "mp4")


async def pixabay_video(query: str, min_dur: float, pick: int = 0) -> str | None:
    key = settings().pixabay_api_key
    if not available("pixabay"):      # unkeyed, or already parked this run
        return None

    async def fetch() -> list[str]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get("https://pixabay.com/api/videos/",
                            params={"key": key, "q": query, "per_page": 15,
                                    "safesearch": "true"})
        if r.status_code != 200:
            return []
        hits = r.json().get("hits", [])
        long_enough = [h for h in hits if h.get("duration", 0) >= min_dur] or hits
        urls: list[str] = []
        for h in long_enough:
            files = h.get("videos", {})
            f = files.get("large") or files.get("medium") or files.get("small")
            if f and f.get("url"):
                urls.append(f["url"])
        return urls

    urls = await _cached_search(f"pixvid:{min_dur:.0f}:{query}", fetch)
    return await _pick_download(urls, pick, "mp4")


async def pexels_image(query: str, pick: int = 0) -> str | None:
    key = settings().pexels_api_key
    if not available("pexels"):       # unkeyed, or already parked this run
        return None

    async def fetch() -> list[str]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": key},
                params={"query": query, "orientation": "portrait", "per_page": 15},
            )
        if r.status_code != 200:
            return []
        out: list[str] = []
        for p in r.json().get("photos", []):
            src = p.get("src") or {}
            u = src.get("portrait") or src.get("large2x") or src.get("large")
            if u:
                out.append(u)
        return out

    urls = await _cached_search(f"peximg:{query}", fetch)
    return await _pick_download(urls, pick, "jpg")


async def pixabay_image(query: str, pick: int = 0) -> str | None:
    key = settings().pixabay_api_key
    if not available("pixabay"):      # unkeyed, or already parked this run
        return None

    async def fetch() -> list[str]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get("https://pixabay.com/api/",
                            params={"key": key, "q": query, "image_type": "photo",
                                    "orientation": "vertical", "per_page": 15,
                                    "safesearch": "true"})
        if r.status_code != 200:
            return []
        out: list[str] = []
        for h in r.json().get("hits", []):
            u = h.get("largeImageURL") or h.get("webformatURL")
            if u:
                out.append(u)
        return out

    urls = await _cached_search(f"piximg:{query}", fetch)
    return await _pick_download(urls, pick, "jpg")


# ------------------------- Ranked candidate pools --------------------------- #
# Separate from the four plain search functions above ON PURPOSE: they keep
# their own `_SEARCH_CACHE`/on-disk cache (list[str] payload) completely
# unchanged, so the keyword-first-hit fallback path is byte-for-byte identical
# to before this was added. These functions hit the same APIs independently,
# with their own richer cache (list[dict] payload, separate cache file), and
# exist only to feed `pipeline/clip_rank.py`'s semantic ranking. If that
# ranking is unavailable, nothing here is ever called.
from dataclasses import dataclass, asdict as _asdict


@dataclass(frozen=True)
class RankCandidate:
    """One stock-search hit, with enough metadata to rank AND download it.

    `thumb_url` is a small/cheap image to embed for ranking — a video poster
    frame (Pexels) or a preview-size image (Pixabay images). When a provider
    exposes no cheap thumbnail (Pixabay video has none in its API response),
    `thumb_url` is "" and the ranker scores that candidate as unranked rather
    than guessing — it stays eligible, just not re-ordered by visual content.
    """
    download_url: str
    thumb_url: str
    source: str                 # "pexels" | "pixabay"
    kind: str                   # "video" | "image"
    tags: str = ""              # provider title/tag text, for a text-only prior
    source_page_url: str = ""
    creator: str = ""
    license: str = ""
    license_url: str = ""
    attribution: str = ""
    width: int = 0
    height: int = 0


def _rank_cache_file(key: str) -> Path:
    path = settings().data_dir / "cache" / "provider_search_rank"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{hashlib.sha1(key.encode()).hexdigest()}.json"


async def _cached_rank_search(key: str, fetch) -> list[RankCandidate]:
    """Same memoise-per-key-per-day shape as `_cached_search`, for the richer
    RankCandidate payload. A separate cache namespace, see module note above."""
    entry = _rank_cache_file(key)
    try:
        payload = json.loads(entry.read_text())
        if time.time() - float(payload.get("fetched_at", 0)) <= _SEARCH_TTL_SECONDS:
            return [RankCandidate(**row) for row in payload.get("rows", [])]
    except (OSError, ValueError, TypeError):
        pass
    try:
        rows = await fetch()
    except Exception:
        rows = []
    if rows:
        tmp = entry.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps({"fetched_at": time.time(),
                                       "rows": [_asdict(r) for r in rows]}))
            tmp.replace(entry)
        except OSError:
            tmp.unlink(missing_ok=True)
    return rows


async def pexels_video_candidates(query: str, min_dur: float) -> list[RankCandidate]:
    if not available("pexels"):
        return []

    async def fetch() -> list[RankCandidate]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": settings().pexels_api_key},
                params={"query": query, "orientation": "portrait",
                        "size": "medium", "per_page": 15},
            )
        if r.status_code != 200:
            return []
        vids = r.json().get("videos", [])
        long_enough = [v for v in vids if v.get("duration", 0) >= min_dur] or vids
        out: list[RankCandidate] = []
        for v in long_enough:
            files = sorted(v.get("video_files", []),
                           key=lambda f: f.get("height", 0), reverse=True)
            pref = [f for f in files if f.get("height", 0) <= 1920] or files
            if pref:
                out.append(RankCandidate(
                    download_url=pref[0]["link"], thumb_url=v.get("image", ""),
                    source="pexels", kind="video",
                    tags=v.get("url", "").rsplit("/", 1)[-1].replace("-", " ")))
        return out

    return await _cached_rank_search(f"pexvidrank:{min_dur:.0f}:{query}", fetch)


async def pixabay_video_candidates(query: str, min_dur: float) -> list[RankCandidate]:
    if not available("pixabay"):
        return []

    async def fetch() -> list[RankCandidate]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get("https://pixabay.com/api/videos/",
                            params={"key": settings().pixabay_api_key, "q": query,
                                    "per_page": 15, "safesearch": "true"})
        if r.status_code != 200:
            return []
        hits = r.json().get("hits", [])
        long_enough = [h for h in hits if h.get("duration", 0) >= min_dur] or hits
        out: list[RankCandidate] = []
        for h in long_enough:
            files = h.get("videos", {})
            f = files.get("large") or files.get("medium") or files.get("small")
            if f and f.get("url"):
                # Pixabay's video API exposes no poster/thumbnail field — the
                # ranker will score this candidate on tags only (see RankCandidate
                # docstring), not a guessed-at frame.
                out.append(RankCandidate(
                    download_url=f["url"], thumb_url="", source="pixabay",
                    kind="video", tags=h.get("tags", "")))
        return out

    return await _cached_rank_search(f"pixvidrank:{min_dur:.0f}:{query}", fetch)


async def pexels_image_candidates(query: str, orientation: str = "portrait") -> list[RankCandidate]:
    if not available("pexels"):
        return []

    async def fetch() -> list[RankCandidate]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": settings().pexels_api_key},
                params={"query": query, "orientation": orientation, "per_page": 15},
            )
        if r.status_code != 200:
            return []
        out: list[RankCandidate] = []
        for p in r.json().get("photos", []):
            src = p.get("src") or {}
            u = src.get("portrait") or src.get("large2x") or src.get("large")
            thumb = src.get("small") or src.get("tiny") or u
            if u:
                out.append(RankCandidate(
                    download_url=u, thumb_url=thumb or "", source="pexels",
                    kind="image", tags=p.get("alt", ""),
                    source_page_url=p.get("url", ""), creator=p.get("photographer", ""),
                    license="Pexels License", license_url="https://www.pexels.com/license/",
                    attribution=f"Photo by {p.get('photographer', 'UNKNOWN')} on Pexels",
                    width=int(p.get("width") or 0), height=int(p.get("height") or 0)))
        return out

    return await _cached_rank_search(f"peximgrank:{orientation}:{query}", fetch)


async def pixabay_image_candidates(query: str, orientation: str = "vertical") -> list[RankCandidate]:
    if not available("pixabay"):
        return []

    async def fetch() -> list[RankCandidate]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get("https://pixabay.com/api/",
                            params={"key": settings().pixabay_api_key, "q": query,
                                    "image_type": "all", "orientation": orientation,
                                    "per_page": 15, "safesearch": "true"})
        if r.status_code != 200:
            return []
        out: list[RankCandidate] = []
        for h in r.json().get("hits", []):
            u = h.get("largeImageURL") or h.get("webformatURL")
            thumb = h.get("previewURL") or u
            if u:
                out.append(RankCandidate(
                    download_url=u, thumb_url=thumb or "", source="pixabay",
                    kind="image", tags=h.get("tags", ""),
                    source_page_url=h.get("pageURL", ""), creator=h.get("user", ""),
                    license="Pixabay Content License",
                    license_url="https://pixabay.com/service/license-summary/",
                    attribution=f"Image by {h.get('user', 'UNKNOWN')} on Pixabay",
                    width=int(h.get("imageWidth") or 0), height=int(h.get("imageHeight") or 0)))
        return out

    return await _cached_rank_search(f"piximgrank:{orientation}:{query}", fetch)


async def download_rank_candidate(cand: RankCandidate) -> str:
    """Download a ranked candidate's full-resolution file through the same
    content-addressed cache every other asset in this pipeline uses."""
    ext = "mp4" if cand.kind == "video" else "jpg"
    return await _download(cand.download_url, ext)


# ----------------------------- Manim --------------------------------------- #
async def manim_render(spec: str, video_id: str, scene_id: str) -> str:
    """Render a chart via a vetted parametric template (no LLM codegen)."""
    from . import manim_templates as mt
    out = settings().data_dir / "jobs" / video_id / f"{scene_id}_chart.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = mt.payload_from_query(spec, title=spec)
    return await mt.render_chart(payload, out)   # raises if manim absent -> solid


# --------------------------- Premium AI video ------------------------------ #
# Hybrid-engine slot #3 (Phase 5.7 — Pika Labs): a SHORT (1–3s) cinematic AI
# insert for PREMIUM documentary beats real footage can't truthfully serve —
# history recreations, political symbolism, election atmosphere, impossible camera
# shots, dark history, abstract economy metaphors. It NEVER replaces real footage:
# the decision engine caps it at ~15–20% of the timeline and the resolver always
# keeps real footage as the safety net, so a missing PIKA_API_KEY or a generation
# failure degrades to footage — the pipeline never breaks.
#
# PROVIDER CHAIN (first configured key wins): Pika (via fal.ai) → Veo3 → Seedance.
# Pika is the real, wired provider; Veo3/Seedance stay stubbed (cost gate). Every
# clip is HARD-CLAMPED + locally trimmed to 1–3s and content-addressed (generated
# once, reused free) so render speed stays reasonable.
AI_INSERT_MIN_S = 1.0
AI_INSERT_MAX_S = 3.0

# Picsart image-to-video inserts are slightly longer (3–5s) — a still gets a real
# cinematic move, so it needs room to breathe vs the 1–3s Pika text→video inserts.
I2V_MIN_S = 3.0
I2V_MAX_S = 5.0


def clamp_i2v_seconds(dur: float) -> float:
    """Picsart image-to-video clips are 3–5s ONLY — clamp any requested duration."""
    return round(max(I2V_MIN_S, min(I2V_MAX_S, dur)), 2)

# Cinematic style baked into every AI-video prompt (matches the AI-image doctrine:
# Netflix/Vox/Bloomberg documentary look, photoreal, vertical 9:16, no text).
AI_VIDEO_STYLE = (
    "cinematic documentary footage, photorealistic, slow deliberate camera move, "
    "dramatic directional lighting, shallow depth of field, 35mm film grain, "
    "muted graded color, American setting, premium Netflix Vox Bloomberg "
    "documentary look, vertical 9:16, highly detailed, no text, no captions, "
    "no watermark, natural undistorted faces"
)
AI_VIDEO_NEGATIVE = (
    "cartoon, illustration, anime, cgi, 3d render, video game, plastic skin, "
    "uncanny faces, deformed face, extra fingers, text, caption, watermark, "
    "logo, lowres, blurry, oversaturated, fast cuts, jittery motion"
)


def clamp_insert_seconds(dur: float) -> float:
    """Premium AI inserts are 1–3s ONLY — clamp any requested duration."""
    return round(max(AI_INSERT_MIN_S, min(AI_INSERT_MAX_S, dur)), 2)


def build_video_prompt(subject: str) -> str:
    """The cinematic prompt sent to Pika for a beat (also used by verification to
    show exactly what was generated)."""
    return (f"{subject.strip()}. {AI_VIDEO_STYLE}. "
            f"Avoid: {AI_VIDEO_NEGATIVE}.").strip(". ")


def _log_video(msg: str) -> None:
    print(f"[ai-video] {msg}", flush=True)


async def ai_video_generate(prompt: str, dur: float, video_id: str,
                            scene_id: str, *, seed: int = 0) -> str:
    """Generate a short (1–3s) cinematic insert. Prefers Pika (fal.ai), then the
    gated Veo3/Seedance stubs; raises if none is configured (cost gate) so the
    resolver falls through to real footage."""
    dur = clamp_insert_seconds(dur)                 # inserts only — never longer
    s = settings()
    if not s.ai_video_enabled:                      # master switch (default OFF)
        raise RuntimeError("AI video disabled (AI_VIDEO_ENABLED=0) → use footage")
    if s.pika_api_key:
        return await pika_generate(prompt, dur, video_id, scene_id, seed=seed)
    if s.veo3_api_key:
        return await veo3_generate(prompt, dur, video_id, scene_id)
    if s.seedance_api_key:
        return await seedance_generate(prompt, dur, video_id, scene_id)
    raise RuntimeError("no AI-video provider key configured (PIKA_API_KEY unset)")


# fal.ai async-queue states that mean "still working" (anything else → check done)
_FAL_PENDING = {"IN_QUEUE", "IN_PROGRESS"}


async def pika_generate(prompt: str, dur: float, video_id: str, scene_id: str,
                        *, seed: int = 0) -> str:
    """Pika Labs cinematic clip via fal.ai's async queue. Submits the job, polls
    until the video is ready, downloads it, then TRIMS to 1–3s locally so the
    insert constraint holds regardless of the provider's native clip length.
    Content-addressed by (model, resolution, prompt, dur) → generated once, reused
    free. Raises on any failure → resolver falls back to real footage."""
    s = settings()
    dur = clamp_insert_seconds(dur)
    cache = _img_cache(
        f"pika:{s.pika_model}:{s.pika_resolution}:{dur}:{seed}:{prompt}", "mp4")
    if cache.exists():
        _log_video(f"{scene_id}: ✓ PIKA clip (cached) → {cache.name}")
        return str(cache)

    _log_video(f"{scene_id}: generating via Pika ({s.pika_model}, {dur:.0f}s, "
               f"{s.pika_resolution})… prompt={prompt[:90]!r}")
    src_url = await _fal_submit_and_wait(prompt, seed)
    raw = await _download(src_url, "mp4")           # provider's native clip
    await _trim_clip(Path(raw), cache, dur)         # enforce 1–3s
    _log_video(f"{scene_id}: ✓ PIKA AI VIDEO inserted ({dur:.0f}s) → {cache.name}")
    return str(cache)


async def _fal_submit_and_wait(prompt: str, seed: int) -> str:
    """Run one fal.ai queued generation and return the resulting video URL.
    Works against any Pika-compatible fal endpoint (PIKA_API_BASE/PIKA_MODEL)."""
    s = settings()
    headers = {"Authorization": f"Key {s.pika_api_key}"}
    body = {
        "prompt": prompt,
        "negative_prompt": AI_VIDEO_NEGATIVE,
        "aspect_ratio": s.pika_aspect_ratio,
        "resolution": s.pika_resolution,
        "seed": seed,
    }
    submit_url = f"{s.pika_api_base.rstrip('/')}/{s.pika_model.lstrip('/')}"
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
        r = await c.post(submit_url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        # Sync endpoints return the result directly; queue endpoints hand back
        # status_url / response_url to poll.
        url = _extract_video_url(data)
        if url:
            return url
        status_url = data.get("status_url")
        response_url = data.get("response_url")
        if not response_url:
            raise RuntimeError(f"pika: unexpected submit response {str(data)[:160]}")

        waited = 0.0
        while waited < s.pika_max_wait_seconds:
            await asyncio.sleep(s.pika_poll_seconds)
            waited += s.pika_poll_seconds
            if status_url:
                sr = await c.get(status_url, headers=headers)
                if sr.status_code == 200:
                    st = sr.json().get("status", "")
                    if st in _FAL_PENDING:
                        continue
            fr = await c.get(response_url, headers=headers)
            if fr.status_code == 200:
                url = _extract_video_url(fr.json())
                if url:
                    return url
        raise RuntimeError(f"pika: timed out after {s.pika_max_wait_seconds:.0f}s")


def _extract_video_url(data: dict) -> str | None:
    """Pull the clip URL out of a fal/Pika response (a few known shapes)."""
    if not isinstance(data, dict):
        return None
    v = data.get("video")
    if isinstance(v, dict) and v.get("url"):
        return v["url"]
    if isinstance(v, str):
        return v
    vids = data.get("videos")
    if isinstance(vids, list) and vids:
        first = vids[0]
        if isinstance(first, dict) and first.get("url"):
            return first["url"]
        if isinstance(first, str):
            return first
    if data.get("url"):
        return data["url"]
    return None


async def _trim_clip(src: Path, out: Path, dur: float) -> None:
    """Trim a clip to the first `dur` seconds (1–3s insert). Re-encodes — clips
    are tiny so it's fast, and it guarantees a clean, keyframe-accurate cut."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part.mp4")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src), "-t", f"{dur:.2f}",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(tmp),
        stderr=asyncio.subprocess.DEVNULL,
    )
    rc = await proc.wait()
    if rc != 0 or not tmp.exists():
        raise RuntimeError("pika clip trim failed")
    tmp.replace(out)                                 # atomic publish


# --------- Picsart IMAGE-TO-VIDEO — cinematic motion on a generated still ------- #
# Slot for the desired "IMAGE → VIDEO" branch: take the still LOCAL ComfyUI already
# produced for a cinematic beat and animate it into a SHORT (3–5s) clip via
# Picsart's GenAI API. HERO / high-emotion / anime / dramatic beats only — the
# scene director caps it (MAX_AI_VIDEO_SCENES) and the resolver keeps the still +
# real footage as the safety net, so a missing PICSART_API_KEY or ANY failure
# degrades to the still (Ken Burns) then real footage — the pipeline never breaks.
#
# API (docs.picsart.io): POST {base}{path} multipart with the image file + prompt;
# auth header X-Picsart-API-Key. Returns 202 + an inference id; we poll
# {base}{path}/inferences/{id} until a video URL is ready, download + trim to 3–5s.
# Content-addressed by (model, quality, dur, image-bytes, prompt) → generated once,
# reused free. Optimised for a weak laptop: 480p + wan-2.7 default, server-side gen
# (no local GPU), only a cheap local trim.
# Friendly model name → the value Picsart expects. `wan-2.7` is a plain short
# name (the API default); the Google Veo image-to-video models are addressed by
# URN. Unknown values (already a URN, or a future short name) pass through
# unchanged, so you can always set a raw model string in the env and it just works.
_PICSART_MODEL_ALIASES: dict[str, str] = {
    "wan-2.7": "wan-2.7",
    "veo-2.0": "urn:air:google:model:google:veo-2.0-image-to-video@1",
    "veo-3.1": "urn:air:google:model:google:veo-3.1-image-to-video@1",
    "veo-3.1-fast": "urn:air:google:model:google:veo-3.1-fast-image-to-video@1",
}


def resolve_picsart_model(name: str) -> str:
    """Map a friendly Picsart model name to its API value; pass unknowns through."""
    n = (name or "").strip()
    return _PICSART_MODEL_ALIASES.get(n, n)


def _picsart_poll_url(inference_id: str) -> str:
    s = settings()
    base = s.picsart_api_base.rstrip("/")
    path = s.picsart_i2v_path.strip("/")
    return f"{base}/{path}/inferences/{inference_id}"


def _extract_inference_id(data: dict) -> str | None:
    """Pull the async job id out of a Picsart 202 response (a few known shapes)."""
    if not isinstance(data, dict):
        return None
    for k in ("inference_id", "transaction_id", "id"):
        v = data.get(k)
        if isinstance(v, str) and v:
            return v
    inner = data.get("data")
    if isinstance(inner, dict):
        for k in ("inference_id", "transaction_id", "id"):
            v = inner.get(k)
            if isinstance(v, str) and v:
                return v
    return None


def _picsart_status(data: dict) -> str:
    """Normalised lowercase status from a Picsart poll response."""
    st = data.get("status") if isinstance(data, dict) else ""
    if not st and isinstance(data.get("data"), dict):
        st = data["data"].get("status", "")
    return str(st or "").lower()


# Picsart async states that mean "still working" (anything else → check for a URL).
_PICSART_PENDING = {"queued", "in_progress", "in-progress", "processing", "pending",
                    "accepted", "running"}


async def picsart_image_to_video(image_path: str, prompt: str, dur: float,
                                 video_id: str, scene_id: str, *,
                                 seed: int = 0, model: str | None = None) -> str:
    """Animate a local still into a 3–5s cinematic clip via Picsart. Submits the
    image + prompt, polls until ready, downloads + trims to 3–5s. Content-addressed
    → generated once, reused free. `model` overrides settings().picsart_model (used
    for the hero beat). Raises on any failure → resolver falls back to the still
    (Ken Burns) then real footage."""
    s = settings()
    if not s.enable_image_to_video:
        raise RuntimeError("image-to-video disabled (ENABLE_IMAGE_TO_VIDEO=0)")
    if not s.picsart_api_key:
        raise RuntimeError("no PICSART_API_KEY configured")
    img = Path(image_path)
    if not img.exists():
        raise RuntimeError(f"picsart: source still missing ({image_path})")

    dur = clamp_i2v_seconds(dur)
    eff_model = resolve_picsart_model(model or s.picsart_model)
    img_sig = hashlib.sha1(img.read_bytes()).hexdigest()[:16]
    cache = _img_cache(
        f"picsart:{eff_model}:{s.picsart_quality}:{dur}:{img_sig}:{prompt}",
        "mp4")
    if cache.exists():
        _log_video(f"{scene_id}: ✓ PICSART clip (cached) → {cache.name}")
        return str(cache)

    _log_video(f"{scene_id}: image→video via Picsart ({eff_model}, "
               f"{dur:.0f}s, {s.picsart_quality})… still={img.name}")
    src_url = await _picsart_submit_and_wait(img, prompt, dur, eff_model)
    raw = await _download(src_url, "mp4")
    await _trim_clip(Path(raw), cache, dur)          # enforce 3–5s
    _log_video(f"{scene_id}: ✓ PICSART AI VIDEO inserted ({dur:.0f}s) → {cache.name}")
    return str(cache)


async def _picsart_submit_and_wait(img: Path, prompt: str, dur: float,
                                   model: str) -> str:
    """Run one Picsart image-to-video job and return the result video URL."""
    s = settings()
    headers = {"X-Picsart-API-Key": s.picsart_api_key, "accept": "application/json"}
    submit_url = f"{s.picsart_api_base.rstrip('/')}/{s.picsart_i2v_path.strip('/')}"
    data = {
        "prompt": prompt,
        "model": model,
        "quality": s.picsart_quality,
        "length": str(int(round(dur))),
        "audio": "true" if s.picsart_audio else "false",
    }
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as c:
        with img.open("rb") as fh:
            files = {"image": (img.name, fh, "application/octet-stream")}
            r = await c.post(submit_url, headers=headers, data=data, files=files)
        r.raise_for_status()
        payload = r.json()
        # A sync-style response may hand back the URL directly.
        url = _extract_video_url(payload)
        if url:
            return url
        inference_id = _extract_inference_id(payload)
        if not inference_id:
            raise RuntimeError(f"picsart: no inference id {str(payload)[:160]}")

        poll_url = _picsart_poll_url(inference_id)
        waited = 0.0
        while waited < s.picsart_max_wait_seconds:
            await asyncio.sleep(s.picsart_poll_seconds)
            waited += s.picsart_poll_seconds
            pr = await c.get(poll_url, headers=headers)
            if pr.status_code in (200, 201):
                body = pr.json()
                url = _extract_video_url(body)
                if url:
                    return url
                if _picsart_status(body) not in _PICSART_PENDING:
                    # terminal non-pending state with no URL → treat as failure
                    if _picsart_status(body) in ("failed", "error", "cancelled"):
                        raise RuntimeError(
                            f"picsart: job {_picsart_status(body)} {str(body)[:120]}")
            elif pr.status_code == 202:
                continue                              # still queued
        raise RuntimeError(
            f"picsart: timed out after {s.picsart_max_wait_seconds:.0f}s")


async def veo3_generate(prompt: str, dur: float, video_id: str, scene_id: str) -> str:
    raise NotImplementedError("Veo3 gated — wire the API call when budget approved")


async def seedance_generate(prompt: str, dur: float, video_id: str, scene_id: str) -> str:
    raise NotImplementedError("Seedance gated — wire the API call when budget approved")


# ----------------------- Premium AI documentary IMAGES --------------------- #
# Phase-5.6 slot: a cinematic AI still (gets Ken Burns motion downstream) for
# beats real footage can't truthfully serve — history recreations, symbolic
# politics, scandals/elections, dark history, impossible-to-film moments. The
# decision engine (`scene_director.py`) picks WHICH beats; this just GENERATES.
#
# IMAGE BACKEND chain (OpenAI is intentionally NOT used — OPENAI_API_KEY ignored):
#   1. PRIMARY — Google AI Studio (GOOGLE_API_KEY): gemini-2.5-flash-image
#      (:generateContent) → imagen-*:predict. Needs BILLING on the key.
#   2. FREE FALLBACK #1 — Hugging Face Inference Providers (HF_TOKEN): cinematic
#      FLUX (FLUX.1-dev → FLUX.1-schnell). Free with a HF token; no Google/OpenAI
#      billing. Returns raw image bytes from the router.
#   3. FREE FALLBACK #2 — Pollinations (no key): photoreal `flux` model. Keeps real
#      AI images flowing for free when Google + HF are unavailable / fail.
#   4. else → raise, and the resolver falls back to real footage (Pexels/Pixabay).
# `ai_image_demo` (default OFF) enables a local ffmpeg plate for fully-offline
# testing. The pipeline never breaks. Results are content-addressed by prompt hash
# → generated once, reused free.

# Style suffix that bakes in the IMAGE QUALITY RULES (Netflix/Vox/Bloomberg doc).
AI_IMAGE_STYLE = (
    "cinematic documentary still, photorealistic, dramatic directional lighting, "
    "shallow depth of field, 35mm film grain, muted graded color, American "
    "setting, premium Netflix Vox Bloomberg documentary look, vertical 9:16 "
    "portrait framing, highly detailed, no text, no captions, no watermark, "
    "natural undistorted faces"
)
AI_IMAGE_NEGATIVE = (
    "cartoon, illustration, anime, cgi, 3d render, video game, plastic skin, "
    "uncanny faces, deformed face, extra fingers, distorted hands, text, "
    "caption, watermark, logo, signature, lowres, blurry, oversaturated"
)
# Cinematic palettes per subject bucket. A BRIGHT key-light colour (c0) falls off
# to a dark base (c1) so the off-centre gradient reads as dramatic directional
# lighting, not a flat near-black card.
_PLATE_PALETTE: dict[str, tuple[str, str, str]] = {
    "history":  ("0xb8842f", "0x140d05", "0x161009"),   # warm amber key on sepia
    "politics": ("0x3f6fb0", "0x4a0f1c", "0x05070d"),   # blue key ↔ deep red
    "business": ("0x4a7fb8", "0xb89a4a", "0x06121f"),   # steel blue + gold key
    "abstract": ("0x2f7a5c", "0x0a1a14", "0x0a0f14"),   # teal key / charcoal
    "default":  ("0x5a5a7a", "0x121218", "0x07070a"),   # neutral cinematic
}


def _img_cache(key: str, ext: str) -> Path:
    cache = settings().data_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache / f"ai_img_{hashlib.sha1(key.encode()).hexdigest()}.{ext}"


def _log(msg: str) -> None:
    print(f"[ai-image] {msg}", flush=True)


async def ai_image_generate(subject: str, video_id: str, scene_id: str,
                            *, category: str = "default", seed: int = 0) -> str:
    """Generate ONE cinematic documentary still via Google AI Studio (free-first).
    Returns a file path, or RAISES so the resolver falls back to real footage.
    Logs exactly where a Google AI image was inserted (or why it fell back)."""
    # OPTIONAL OpenRouter augmentation: sharpen the subject into a richer cinematic
    # prompt. No-op (returns the original subject) when OpenRouter isn't configured,
    # so image generation behaves exactly as before unless OPENROUTER_API_KEY is set.
    from ..openrouter import enhance_image_prompt
    subject = await enhance_image_prompt(subject)
    prompt = (f"{subject.strip()}. {AI_IMAGE_STYLE}. "
              f"Avoid: {AI_IMAGE_NEGATIVE}.").strip(". ")
    s = settings()

    # 0) PRIMARY (when enabled) — remote ComfyUI on a GPU (Colab + Cloudflare
    #    tunnel). Runs a DreamShaper SD1.5 txt2img graph and returns a real still.
    #    ANY failure (tunnel down, timeout, bad graph) logs and falls through to the
    #    existing chain below — the pipeline never breaks.
    if available("comfyui"):
        _log(f"{scene_id}: generating via remote ComfyUI "
             f"({s.comfyui_checkpoint})… subject={subject!r}")
        try:
            path = await _remote_comfyui_image(prompt, seed)
            note_success("comfyui")
            _log(f"{scene_id}: ✓ COMFYUI image inserted → {Path(path).name}")
            return path
        except Exception as e:  # noqa: BLE001
            note_failure("comfyui", e)
            _log(f"{scene_id}: ✗ ComfyUI failed "
                 f"({type(e).__name__}: {str(e)[:120]}) → falling back to chain")

    # 1) PRIMARY — Google AI Studio (needs billing on the key).
    if available("google_ai"):
        _log(f"{scene_id}: generating via Google AI Studio "
             f"({s.google_image_model})… subject={subject!r}")
        try:
            path = await _google_ai_studio_image(prompt)
            note_success("google_ai")
            _log(f"{scene_id}: ✓ GOOGLE AI IMAGE inserted → {Path(path).name}")
            return path
        except Exception as e:  # noqa: BLE001
            note_failure("google_ai", e)
            _log(f"{scene_id}: ✗ Google generation FAILED "
                 f"({type(e).__name__}: {str(e)[:120]}) → trying Pollinations (free)")

    # 2) FREE FALLBACK #1 — Hugging Face Inference Providers (FLUX, free with a HF
    #    token). FLUX.1-dev (preferred) → FLUX.1-schnell (fast free). Any failure or
    #    rate-limit cleanly degrades to Pollinations next — the pipeline never breaks.
    if available("huggingface"):
        _log(f"{scene_id}: generating via HuggingFace FLUX "
             f"({s.huggingface_image_model})… subject={subject!r}")
        try:
            path = await _huggingface_image(prompt, seed)
            note_success("huggingface")
            _log(f"{scene_id}: ✓ HF image inserted → {Path(path).name}")
            return path
        except Exception as e:  # noqa: BLE001
            note_failure("huggingface", e)
            _log(f"{scene_id}: ✗ HF failed "
                 f"({type(e).__name__}: {str(e)[:120]}) → fallback to Pollinations")

    # 3) FREE FALLBACK #2 — Pollinations (no key). Keeps real AI images flowing free.
    if available("pollinations"):
        _log(f"{scene_id}: generating via Pollinations "
             f"({s.pollinations_model}, free)… subject={subject!r}")
        try:
            path = await _pollinations_image(prompt, seed)
            note_success("pollinations")
            _log(f"{scene_id}: ✓ POLLINATIONS (free) AI IMAGE inserted → {Path(path).name}")
            return path
        except Exception as e:  # noqa: BLE001
            note_failure("pollinations", e)
            _log(f"{scene_id}: ✗ Pollinations FAILED "
                 f"({type(e).__name__}: {str(e)[:120]}) → fallback to real footage")

    # 4) optional offline plate, else raise → resolver uses real footage (Pexels)
    if s.ai_image_demo:
        _log(f"{scene_id}: AI_IMAGE_DEMO on → local cinematic plate (offline test)")
        return await _local_cinematic_plate(subject, category, seed)
    raise RuntimeError("no AI image (google + pollinations unavailable); use footage")


# --------- Remote ComfyUI — GPU text→image on the DreamShaper checkpoint -------- #
# Talks to a stock ComfyUI HTTP API (no SDK): POST /prompt to enqueue a graph, poll
# /history/{prompt_id} until the run finishes, then GET /view to download the PNG.
# The graph is a clean, minimal SD1.5 text→image pipeline (CheckpointLoader →
# 2×CLIPTextEncode → EmptyLatentImage → KSampler → VAEDecode → SaveImage). It reuses
# the shared documentary style + negative prompt so output matches the other
# providers. Content-addressed → generated once, reused free. Raises on any failure
# so ai_image_generate() falls through to the existing provider chain.
def _comfy_graph(prompt: str, seed: int) -> dict:
    """Build a ComfyUI prompt graph (node-id → node) for SD1.5 txt2img.

    Default = the stock 25-step graph (UNCHANGED — backward compatible). When
    COMFYUI_LCM=1, a LoraLoaderModelOnly node is inserted and the KSampler is fed
    the LCM model + LCM-tuned steps/cfg/sampler/scheduler, so the same checkpoint
    renders in ~8 steps (the CPU win). COMFYUI_VAE_TILED=1 swaps in a tiled VAE
    decode to cap peak RAM on a 12GB box. Negative prompt is overridable
    (COMFYUI_NEGATIVE) so an anime/cartoon checkpoint isn't fought by the global
    photoreal negative."""
    s = settings()
    negative = s.comfyui_negative.strip() or AI_IMAGE_NEGATIVE

    if s.comfyui_lcm:
        model_ref = ["10", 0]                       # KSampler reads the LCM model
        steps, cfg = s.comfyui_lcm_steps, s.comfyui_lcm_cfg
        sampler, scheduler = s.comfyui_lcm_sampler, s.comfyui_lcm_scheduler
    else:
        model_ref = ["4", 0]                         # checkpoint model (stock path)
        steps, cfg = s.comfyui_steps, s.comfyui_cfg
        sampler, scheduler = s.comfyui_sampler, s.comfyui_scheduler

    if s.comfyui_vae_tiled:
        # Newer ComfyUI VAEDecodeTiled also requires overlap + temporal_* (it's the
        # shared image/video decoder). The temporal params are inert for a single
        # still but must be present or the prompt fails validation.
        decode = {"class_type": "VAEDecodeTiled",
                  "inputs": {"samples": ["3", 0], "vae": ["4", 2],
                             "tile_size": s.comfyui_vae_tile_size,
                             "overlap": 64,
                             "temporal_size": 64, "temporal_overlap": 8}}
    else:
        decode = {"class_type": "VAEDecode",
                  "inputs": {"samples": ["3", 0], "vae": ["4", 2]}}

    graph = {
        "4": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": s.comfyui_checkpoint}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": s.comfyui_width, "height": s.comfyui_height,
                         "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["4", 1]}},
        "3": {"class_type": "KSampler",
              "inputs": {"seed": int(seed), "steps": steps,
                         "cfg": cfg, "sampler_name": sampler,
                         "scheduler": scheduler, "denoise": 1.0,
                         "model": model_ref, "positive": ["6", 0],
                         "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": decode,
        "9": {"class_type": "SaveImage",
              "inputs": {"images": ["8", 0], "filename_prefix": "shortsfactory"}},
    }
    if s.comfyui_lcm:                                # insert the LCM-LoRA on the model
        graph["10"] = {"class_type": "LoraLoaderModelOnly",
                       "inputs": {"lora_name": s.comfyui_lcm_lora,
                                  "strength_model": s.comfyui_lcm_strength,
                                  "model": ["4", 0]}}
    return graph


async def _remote_comfyui_image(prompt: str, seed: int = 0) -> str:
    s = settings()
    base = s.comfyui_base_url.rstrip("/")
    if not base:
        raise RuntimeError("COMFYUI_BASE_URL not set")
    # the render settings live in the key so an LCM still and a stock still (or a
    # changed negative) never collide in the content-addressed cache.
    variant = (f"lcm{s.comfyui_lcm_steps}@{s.comfyui_lcm_cfg}" if s.comfyui_lcm
               else f"std{s.comfyui_steps}@{s.comfyui_cfg}")
    out = _img_cache(f"comfyui:{base}:{s.comfyui_checkpoint}:{variant}:"
                     f"{s.comfyui_width}x{s.comfyui_height}:{seed}:{prompt}", "png")
    if out.exists():
        return str(out)

    graph = _comfy_graph(prompt, seed)
    timeout = float(s.comfyui_timeout)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
        # 1) enqueue the graph
        r = await c.post(f"{base}/prompt", json={"prompt": graph})
        r.raise_for_status()
        prompt_id = r.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI /prompt returned no prompt_id: {r.text[:120]}")

        # 2) poll /history until this prompt_id has outputs (bounded by comfyui_timeout)
        deadline = timeout
        waited = 0.0
        entry: dict = {}
        while waited < deadline:
            h = await c.get(f"{base}/history/{prompt_id}")
            if h.status_code == 200:
                entry = h.json().get(prompt_id) or {}
                if entry.get("outputs"):
                    break
            await asyncio.sleep(s.comfyui_poll_seconds)
            waited += s.comfyui_poll_seconds
        if not entry.get("outputs"):
            raise RuntimeError(f"ComfyUI timed out after {deadline:.0f}s (prompt {prompt_id})")

        # 3) locate the first produced image and download it via /view
        img = None
        for node_out in entry["outputs"].values():
            for i in node_out.get("images", []):
                img = i
                break
            if img:
                break
        if not img:
            raise RuntimeError("ComfyUI run produced no image output")
        v = await c.get(f"{base}/view", params={
            "filename": img["filename"],
            "subfolder": img.get("subfolder", ""),
            "type": img.get("type", "output"),
        })
        v.raise_for_status()
        if len(v.content) < 1024:
            raise RuntimeError(f"ComfyUI /view returned tiny image ({len(v.content)}B)")

    tmp = out.with_name(out.name + ".part")
    tmp.write_bytes(v.content)
    tmp.replace(out)                              # atomic publish
    _log(f"  ComfyUI {s.comfyui_checkpoint.split('.')[0]} "
         f"({s.comfyui_width}x{s.comfyui_height}, {len(v.content)//1024}KB)")
    return str(out)


# Google AI Studio model defaults (overridable via env GOOGLE_IMAGE_MODEL /
# GOOGLE_IMAGEN_MODEL). Gemini flash-image is the free-first path.
async def _google_ai_studio_image(prompt: str) -> str:
    """Google AI Studio image gen: Gemini flash-image first, Imagen as fallback.
    Both use the Generative Language API authed by GOOGLE_API_KEY (AI Studio)."""
    try:
        return await _gemini_image(prompt)
    except Exception:
        return await _imagen_image(prompt)


async def _gemini_image(prompt: str) -> str:
    """Gemini image generation via :generateContent (inline base64 image)."""
    model = settings().google_image_model
    out = _img_cache(f"gemini:{model}:{prompt}", "png")
    if out.exists():
        return str(out)
    key = settings().google_api_key
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        })
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"]["parts"]
        for p in parts:
            inline = p.get("inlineData") or p.get("inline_data")
            if inline and inline.get("data"):
                out.write_bytes(base64.b64decode(inline["data"]))
                return str(out)
    raise RuntimeError("gemini returned no inline image data")


async def _imagen_image(prompt: str) -> str:
    """Google Imagen via the Generative Language predict endpoint (AI Studio)."""
    model = settings().google_imagen_model
    out = _img_cache(f"imagen:{model}:{prompt}", "png")
    if out.exists():
        return str(out)
    key = settings().google_api_key
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:predict?key={key}")
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(url, json={
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": "9:16"},
        })
        r.raise_for_status()
        b64 = r.json()["predictions"][0]["bytesBase64Encoded"]
        out.write_bytes(base64.b64decode(b64))
    return str(out)


# --------- Hugging Face Inference Providers — FREE cinematic FLUX images -------- #
# Text-to-image via the HF router (https://router.huggingface.co). Hits the
# serverless provider endpoint `{router}/{provider}/models/{model}`, which returns
# RAW image bytes. Tries FLUX.1-dev (preferred look) then FLUX.1-schnell (fast free
# fallback served by `hf-inference`). It REUSES the shared documentary style +
# negative prompt, so HF output matches the Google/Pollinations look — photoreal,
# Netflix/Vox/Bloomberg, and NEVER anime/cartoon (cartoon/anime are in the negative).
# Content-addressed → generated once, reused free. Optimised for the AI-eligible
# buckets (history / politics / scandal / elections / dark-history) the decision
# engine routes here. Raises on any failure → caller degrades to Pollinations.
async def _huggingface_image(prompt: str, seed: int = 0) -> str:
    s = settings()
    token = s.hf_api_token
    if not token:
        raise RuntimeError("no HF token (HF_TOKEN / HUGGINGFACE_API_KEY unset)")
    host = s.huggingface_base_url.rstrip("/")
    if host.endswith("/v1"):                  # strip OpenAI-style suffix → router host
        host = host[: -len("/v1")]
    provider = s.huggingface_image_provider.strip("/") or "hf-inference"
    headers = {"Authorization": f"Bearer {token}"}
    models = [m for m in (s.huggingface_image_model,
                          s.huggingface_image_model_fast) if m]

    last = ""
    for model in models:
        out = _img_cache(f"hf:{provider}:{model}:{seed}:{prompt}", "png")
        if out.exists():
            return str(out)
        # schnell is a 4-step distilled model; dev wants more steps for quality.
        steps = 4 if "schnell" in model.lower() else 28
        body = {
            "inputs": prompt,
            "parameters": {
                "negative_prompt": AI_IMAGE_NEGATIVE,     # bars cartoon/anime/3d
                "num_inference_steps": steps,
                "width": 768, "height": 1344,             # 9:16 vertical (renderer crops)
                "seed": seed,
            },
        }
        url = f"{host}/{provider}/models/{model}"
        try:
            async with httpx.AsyncClient(timeout=180, follow_redirects=True) as c:
                r = await c.post(url, headers=headers, json=body)
                if r.status_code == 503:           # model cold-loading → one retry
                    await asyncio.sleep(6)
                    r = await c.post(url, headers=headers, json=body)
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and ct.startswith("image") and len(r.content) >= 1024:
                tmp = out.with_name(out.name + ".part")
                tmp.write_bytes(r.content)
                tmp.replace(out)                   # atomic publish
                _log(f"  HF FLUX via {provider}/{model.split('/')[-1]} "
                     f"({len(r.content)//1024}KB)")
                return str(out)
            # 429 rate-limit / 404 not-served-here / JSON error → record and try next.
            detail = r.text[:100].replace("\n", " ") if not ct.startswith("image") else ""
            last = f"{model.split('/')[-1]}: {r.status_code} {detail}"
        except Exception as e:  # noqa: BLE001
            last = f"{model.split('/')[-1]}: {type(e).__name__}"
    raise RuntimeError(f"huggingface unavailable ({last})")


# Pollinations' free/anonymous tier allows only ONE in-flight request per IP
# (extra concurrent calls get 402 "queue full max:1") and occasionally returns an
# empty body. The pipeline resolves scenes CONCURRENTLY, so we serialize all
# Pollinations calls through this lock and retry-with-backoff on 402/429/empty.
_POLLI_LOCK = asyncio.Lock()
# A FREE service must never be able to block a render. Pollinations serialises
# every call behind `_POLLI_LOCK` (its free tier allows one at a time), so any
# per-image cost is multiplied by the number of AI beats. At the previous
# settings — 180s per request x 5 attempts + 48s of backoff — a single image
# could hold the pipeline for ~16 minutes, and a 28-beat episode for over seven
# hours. Measured on this box: 57 minutes of waiting produced ZERO images.
#
# These three constants are the whole budget. When it is spent the caller
# degrades to `_local_cinematic_plate`, which is free, local and instant, and
# `note_failure` parks the provider so the remaining beats skip it outright.
# Measured: a healthy free generation lands in 2-45s (three cold prompts came
# back at 2.4s, 45.2s and 44.7s). The request window has to clear that, or half
# the LEGITIMATE images get cut off; the total budget is what stops a throttled
# queue from turning into an unbounded wait.
_POLLI_REQUEST_TIMEOUT_S = 70.0   # one attempt; comfortably over the 45s norm
_POLLI_TOTAL_BUDGET_S = 110.0     # wall clock for ALL attempts at one image
_POLLI_BACKOFF = (4, 8)           # seconds between attempts (queue drains)


async def _pollinations_image(prompt: str, seed: int = 0) -> str:
    """Pollinations — FREE image generation (no key needed; a free POLLINATIONS_
    TOKEN lifts the rate limit). Forces photoreal documentary style (NOT cartoon/
    anime) via the prompt. Serialized + retried to respect the 1-concurrent free
    tier. Content-addressed → generated once, reused free."""
    s = settings()
    model = s.pollinations_model
    out = _img_cache(f"pollinations:{model}:{seed}:{prompt}", "jpg")
    if out.exists():
        return str(out)
    # Refuse at the GENERATOR, not only at the orchestrator. `ai_image_generate`
    # checks `available()` first, but the AI-b-roll engine's FluxAdapter calls
    # this function directly — so switching Pollinations off did nothing and the
    # render still hung on it. A disabled or parked provider must be unreachable
    # by every caller, cached results excepted (already returned above).
    if not available("pollinations"):
        raise RuntimeError("pollinations disabled or parked for this run")
    url = f"https://image.pollinations.ai/prompt/{quote(prompt, safe='')}"
    params = {"width": 768, "height": 1344,    # 9:16; renderer crops to fill
              "model": model, "seed": seed, "nologo": "true",
              "enhance": "false", "private": "true"}
    if s.pollinations_token:                    # registered free token (optional)
        params["token"] = s.pollinations_token
    headers = ({"Authorization": f"Bearer {s.pollinations_token}"}
               if s.pollinations_token else {})

    last = ""
    started = time.monotonic()

    def _spent() -> float:
        return time.monotonic() - started

    async with _POLLI_LOCK:                      # one Pollinations call at a time
        async with httpx.AsyncClient(timeout=_POLLI_REQUEST_TIMEOUT_S,
                                     follow_redirects=True) as c:
            for i in range(len(_POLLI_BACKOFF) + 1):
                remaining = _POLLI_TOTAL_BUDGET_S - _spent()
                if remaining <= 0:
                    last = last or "budget spent before first reply"
                    break
                try:
                    # HARD wall-clock cap. httpx's `timeout` is per-READ, so a
                    # server that trickles bytes while it queues never trips it
                    # and the transfer hangs forever — measured here as a single
                    # socket held open for 21 minutes against a 70s timeout.
                    # asyncio.wait_for bounds the whole request, not each read.
                    r = await asyncio.wait_for(
                        c.get(url, params=params, headers=headers),
                        timeout=min(_POLLI_REQUEST_TIMEOUT_S, remaining))
                except (asyncio.TimeoutError, TimeoutError):
                    last = f"timed out after {_spent():.0f}s"
                except Exception as e:          # noqa: BLE001
                    last = f"{type(e).__name__}"
                else:
                    ct = r.headers.get("content-type", "")
                    if r.status_code == 200 and ct.startswith("image") \
                            and len(r.content) >= 1024:
                        tmp = out.with_name(out.name + ".part")
                        tmp.write_bytes(r.content)
                        tmp.replace(out)         # atomic publish
                        return str(out)
                    last = (f"{r.status_code} {ct} {len(r.content)}B"
                            if r.status_code != 200 else "empty image")
                # Only sleep if there is budget left to use the next attempt.
                if i < len(_POLLI_BACKOFF) and \
                        _spent() + _POLLI_BACKOFF[i] < _POLLI_TOTAL_BUDGET_S:
                    await asyncio.sleep(_POLLI_BACKOFF[i])
    raise RuntimeError(f"pollinations unavailable after {_spent():.0f}s ({last})")


async def _local_cinematic_plate(subject: str, category: str, seed: int) -> str:
    """Zero-key fallback: synthesize a 1080x1920 cinematic PLATE with ffmpeg
    (graded gradient + grain + vignette). This is NOT a photoreal neural image —
    it is an atmospheric backdrop so the AI-image SLOT (and its Ken Burns motion)
    is exercised end-to-end without a paid key. Content-addressed → made once."""
    c0, c1, base = _PLATE_PALETTE.get(category, _PLATE_PALETTE["default"])
    sd = (abs(hash(subject)) + seed) % 100000
    # recipe version in the key → tweaking the palette/grade busts stale plates.
    out = _img_cache(f"plate:v2:{category}:{subject}:{seed}", "jpg")
    if out.exists():
        return str(out)
    # off-centre gradient (cinematic key-light feel) → grain → vignette → grade.
    src = (f"gradients=s=1080x1920:c0={c0}:c1={c1}:x0=360:y0=620:"
           f"x1=1020:y1=1820:nb_colors=2:seed={sd}")
    vf = ("noise=alls=11:allf=t,vignette=PI/4.6,"
          "eq=contrast=1.08:saturation=1.02:brightness=0.02,format=yuv420p")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", src, "-frames:v", "1", "-vf", vf, "-y", str(out),
        stderr=asyncio.subprocess.DEVNULL,
    )
    rc = await proc.wait()
    if rc != 0 or not out.exists():
        raise RuntimeError("local cinematic plate generation failed")
    return str(out)


async def _decodes(path: Path) -> bool:
    """Does ffmpeg actually see a frame in this file? The repo already probes
    media with ffprobe everywhere else, so this needs no new dependency.

    Byte count alone cannot tell a photograph from a throttling notice that
    happened to arrive with a 200 — decoding can.
    """
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        return False
    dims = out.decode().strip().strip(",").split(",")
    return len(dims) >= 2 and all(d.isdigit() and int(d) > 0 for d in dims[:2])


async def _download(url: str, ext: str) -> str:
    """Content-addressed cache. The filename is sha1(url) so the SAME asset is
    only ever fetched once across runs (deterministic, no duplicate downloads).
    A per-file lock collapses concurrent requests for the same URL, and the
    bytes are published atomically via rename so a crash can't leave a truncated
    file masquerading as a cache hit.

    Nothing is published until the response proves it is renderable media:
    status, Content-Type, byte count and a real decode. A body that fails any of
    those is discarded rather than cached, because a cached dud is permanent —
    the sha1 name makes every later run a "hit" on the same broken bytes.
    """
    cache = settings().data_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    name = cache / f"{hashlib.sha1(url.encode()).hexdigest()}.{ext}"
    if name.exists():
        return str(name)
    lock = _DL_LOCKS.setdefault(str(name), asyncio.Lock())
    async with lock:
        if name.exists():                       # won the race while waiting
            return str(name)
        # upload.wikimedia.org enforces the same robot policy as the API, so a
        # candidate could rank 0.96 and still never reach disk: the search
        # succeeded, the fetch 403'd, and the beat silently fell back.
        #
        # It also answers a BURST of parallel fetches with 429. The asset engine
        # discovers every beat concurrently, so a 7-scene video opened ~28
        # requests at once and the throttled ones raised — which is how a
        # 0.91-scoring public-domain image was reported as "no licensed asset
        # exists". Wikimedia transfers are serialised to two at a time; every
        # other host keeps the previous unbounded behaviour.
        gate = (_WIKIMEDIA_TRANSFERS
                if urlparse(url).hostname in _WIKIMEDIA_HOSTS
                else contextlib.nullcontext())
        async with httpx.AsyncClient(timeout=180, follow_redirects=True,
                                     headers={"User-Agent": WIKIMEDIA_UA}) as c:
            # ONE retry, backed off. A 429/5xx means "come back later", so an
            # immediate repeat just spends the same rejection twice; anything
            # else is a permanent answer and retrying it is pure latency.
            for attempt in range(_DOWNLOAD_ATTEMPTS):
                async with gate:
                    # HARD wall-clock cap. `timeout=180` above is httpx's
                    # per-READ budget, so a host that trickles a large video —
                    # a few bytes inside every window — never trips it and the
                    # transfer hangs indefinitely. A 156-beat render sat silent
                    # for 27 minutes on exactly one such socket. asyncio.wait_for
                    # bounds the whole fetch, so a slow CDN costs one asset, not
                    # the episode.
                    try:
                        r = await asyncio.wait_for(c.get(url),
                                                   timeout=_DOWNLOAD_DEADLINE_S)
                    except (asyncio.TimeoutError, TimeoutError):
                        if attempt < _DOWNLOAD_ATTEMPTS - 1:
                            continue
                        raise RuntimeError(
                            f"{url[:80]} → stalled past {_DOWNLOAD_DEADLINE_S:.0f}s")
                if r.status_code != 200:
                    if (r.status_code in _RETRY_STATUS
                            and attempt < _DOWNLOAD_ATTEMPTS - 1):
                        await asyncio.sleep(_retry_delay(r, attempt))
                        continue
                    raise RuntimeError(f"{url[:80]} → HTTP {r.status_code}")
                kind = r.headers.get("content-type", "").split(";")[0].strip()
                if kind and not kind.startswith(_MEDIA_TYPES):
                    raise RuntimeError(f"{url[:80]} → not media ({kind})")
                if len(r.content) < _MIN_ASSET_BYTES:
                    raise RuntimeError(f"{url[:80]} → {len(r.content)}B under the "
                                       f"{_MIN_ASSET_BYTES}B floor")
                tmp = name.with_name(name.name + ".part")
                tmp.write_bytes(r.content)
                if not await _decodes(tmp):
                    tmp.unlink(missing_ok=True)
                    raise RuntimeError(f"{url[:80]} → body does not decode")
                tmp.replace(name)               # atomic publish
                break
    return str(name)
