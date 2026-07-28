"""
Google Trends connector — OFF BY DEFAULT and deliberately vendor-neutral.

There is no free, officially supported public Google Trends API. Unofficial
scrapers (pytrends and friends) break without notice, are rate-limited, and are
not something to hide inside a production dependency chain. So this provider talks
to a connector endpoint YOU supply and approve:

    GOOGLE_TRENDS_ENABLED=true
    GOOGLE_TRENDS_BASE_URL=https://<your-approved-trends-connector>/interest
    GOOGLE_TRENDS_API_KEY=<if your connector needs one>

Expected response (either shape is accepted):

    {"items": [{"query": "cpi report", "interest": 84, "region": "US",
                "breakout_ratio": 3.2, "timestamp": "2026-07-28T12:00:00Z"}, ...]}

If the provider is unavailable the run records a provider failure and continues —
search-interest simply drops out of the momentum blend.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..http import request_json
from ..models import RawTrendSignal
from .base import FINANCE_QUERIES, BaseProvider


def _parse_dt(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(float(v), tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


class GoogleTrendsProvider(BaseProvider):
    name = "google_trends"

    @property
    def enabled(self) -> bool:
        return self.settings.google_trends_enabled

    @property
    def configured(self) -> bool:
        return bool(self.settings.google_trends_base_url.strip())

    async def collect(
        self, *, niche: str, region: str, since: datetime, limit: int
    ) -> list[RawTrendSignal]:
        s = self.settings
        region = s.google_trends_region or region or "US"
        headers = (
            {"Authorization": f"Bearer {s.google_trends_api_key.strip()}"}
            if s.google_trends_api_key.strip() else None
        )
        data = await request_json(
            "GET", s.google_trends_base_url.strip(), breaker_key=self.name,
            headers=headers,
            params={
                "geo": region,
                "category": "finance",
                "terms": ",".join(FINANCE_QUERIES),
                "since": since.isoformat(),
                "limit": limit,
            },
        )

        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []

        now = datetime.now(timezone.utc)
        out: list[RawTrendSignal] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            query = str(item.get("query") or item.get("term") or "").strip()
            if not query:
                continue
            interest = item.get("interest", item.get("value"))
            engagement = {}
            if isinstance(interest, (int, float)):
                engagement["interest"] = float(interest)
            raw: dict = {"query": query, "geo": item.get("region") or region}
            br = item.get("breakout_ratio", item.get("breakout"))
            if isinstance(br, (int, float)):
                raw["breakout_ratio"] = float(br)
            if item.get("rising") is not None:
                raw["rising"] = item["rising"]

            out.append(RawTrendSignal(
                provider=self.name,
                external_id=query,
                title=query,
                summary=f"Google Trends search interest for {query!r} ({region})",
                url=item.get("url"),
                published_at=_parse_dt(item.get("timestamp") or item.get("date")) or now,
                collected_at=now,
                region=item.get("region") or region,
                engagement=engagement,
                raw_metrics=raw,
                author_or_channel="google_trends",
                # Search interest is a demand measurement, not a factual source.
                source_credibility=None,
            ))
        return out
