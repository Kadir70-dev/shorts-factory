"""
YouTube Data API v3 connector — the primary competition + demand signal.

Discovery does NOT use videos.list(chart="mostPopular"): that returns whatever is
trending nationally (music, sports, entertainment) and is nearly useless for a
finance niche. Instead:

    search.list(q=<finance query>, type=video, order=viewCount,
                publishedAfter=<since>, regionCode=US, relevanceLanguage=en)
        -> videos.list(id=..., part=statistics,snippet,contentDetails)
        -> channels.list(id=..., part=statistics)   [subscriber counts]

Quota notes (default 10,000 units/day):
    search.list   = 100 units per call   <-- the expensive one
    videos.list   =   1 unit per call (batched 50 ids)
    channels.list =   1 unit per call (batched 50 ids)
A default run of 8 queries costs ~800 + ~4 = ~804 units. Responses are cached for
TI_CACHE_TTL_S so repeated runs within the window are free.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..http import request_json
from ..models import RawTrendSignal
from .base import FINANCE_QUERIES, BaseProvider

API = "https://www.googleapis.com/youtube/v3"


def _iso(dt: datetime) -> str:
    dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _num(d: dict, key: str) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class YouTubeProvider(BaseProvider):
    name = "youtube"

    @property
    def enabled(self) -> bool:
        return self.settings.youtube_trends_enabled

    @property
    def configured(self) -> bool:
        return bool(self.settings.youtube_data_api_key.strip())

    async def collect(
        self, *, niche: str, region: str, since: datetime, limit: int
    ) -> list[RawTrendSignal]:
        s = self.settings
        key = s.youtube_data_api_key.strip()
        region = region or s.youtube_region
        queries = list(FINANCE_QUERIES)[: max(1, s.youtube_max_queries)]
        per_query = max(1, min(50, s.youtube_results_per_query))

        # --- 1. discovery ---
        video_ids: list[str] = []
        snippets: dict[str, dict] = {}
        for q in queries:
            try:
                data = await request_json(
                    "GET", f"{API}/search", breaker_key=self.name,
                    params={
                        "key": key, "part": "snippet", "q": q, "type": "video",
                        "order": "viewCount", "maxResults": per_query,
                        "publishedAfter": _iso(since), "regionCode": region,
                        "relevanceLanguage": s.youtube_relevance_language,
                        "videoEmbeddable": "true", "safeSearch": "moderate",
                    },
                )
            except Exception as e:  # noqa: BLE001 — one bad query, not the whole run
                print(f"[ti.youtube] query {q!r} failed: {type(e).__name__}: {e}",
                      flush=True)
                continue
            for item in data.get("items", []):
                vid = (item.get("id") or {}).get("videoId")
                if vid and vid not in snippets:
                    video_ids.append(vid)
                    snippets[vid] = dict(item.get("snippet") or {}, _query=q)
            if len(video_ids) >= limit:
                break

        if not video_ids:
            return []
        video_ids = video_ids[:limit]

        # --- 2. statistics (batched, 1 unit per 50) ---
        stats: dict[str, dict] = {}
        details: dict[str, dict] = {}
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i + 50]
            data = await request_json(
                "GET", f"{API}/videos", breaker_key=self.name,
                params={"key": key, "part": "statistics,snippet,contentDetails",
                        "id": ",".join(chunk)},
            )
            for item in data.get("items", []):
                stats[item["id"]] = item.get("statistics", {}) or {}
                details[item["id"]] = item

        # --- 3. channel statistics (batched) ---
        channel_ids = sorted({
            (details.get(v, {}).get("snippet", {}) or {}).get("channelId")
            or (snippets.get(v, {}) or {}).get("channelId")
            for v in video_ids
        } - {None})
        channel_stats: dict[str, dict] = {}
        for i in range(0, len(channel_ids), 50):
            chunk = channel_ids[i:i + 50]
            try:
                data = await request_json(
                    "GET", f"{API}/channels", breaker_key=self.name,
                    params={"key": key, "part": "statistics,snippet",
                            "id": ",".join(chunk)},
                )
            except Exception as e:  # noqa: BLE001 — subscriber data is a bonus
                print(f"[ti.youtube] channels.list failed: {type(e).__name__}: {e}",
                      flush=True)
                break
            for item in data.get("items", []):
                channel_stats[item["id"]] = item

        # --- 4. assemble ---
        out: list[RawTrendSignal] = []
        now = datetime.now(timezone.utc)
        for vid in video_ids:
            snip = (details.get(vid, {}).get("snippet")
                    or snippets.get(vid) or {})
            st = stats.get(vid, {})
            published = _parse_dt(snip.get("publishedAt"))
            ch_id = snip.get("channelId")
            ch = channel_stats.get(ch_id or "", {})
            ch_stats = ch.get("statistics", {}) or {}

            engagement = {}
            for src_key, dst in (("viewCount", "views"), ("likeCount", "likes"),
                                 ("commentCount", "comments")):
                v = _num(st, src_key)
                if v is not None:
                    engagement[dst] = v

            raw_metrics: dict = {
                "video_id": vid,
                "channel_id": ch_id,
                "query": snip.get("_query"),
                "duration": (details.get(vid, {}).get("contentDetails") or {}).get("duration"),
                "tags": (details.get(vid, {}).get("snippet") or {}).get("tags", [])[:10],
            }
            subs = _num(ch_stats, "subscriberCount")
            if subs is not None:
                raw_metrics["channel_subscribers"] = subs
            ch_videos = _num(ch_stats, "videoCount")
            if ch_videos is not None:
                raw_metrics["channel_video_count"] = ch_videos

            out.append(RawTrendSignal(
                provider=self.name,
                external_id=vid,
                title=snip.get("title", "") or "",
                summary=(snip.get("description") or "")[:600] or None,
                url=f"https://www.youtube.com/watch?v={vid}",
                published_at=published,
                collected_at=now,
                region=region,
                engagement=engagement,
                raw_metrics=raw_metrics,
                author_or_channel=snip.get("channelTitle"),
                # A YouTube video is an interest signal, not a credible source.
                source_credibility=None,
            ))
        return out
