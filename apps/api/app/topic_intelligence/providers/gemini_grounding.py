"""
Gemini Google Search grounding — a DISCOVERY and VERIFICATION source only.

What it is for:
  * finding US-finance stories the deterministic providers missed,
  * diversifying sources,
  * retrieving missing context.

What it is NOT for:
  * producing trend metrics, search volumes, engagement figures or competitor
    statistics. Grounded signals carry NO engagement data at all — by construction
    they cannot pollute the momentum blend.

Citation discipline: only items that arrive with real grounding metadata (a URI)
are emitted as evidence. Items whose metadata is missing or incomplete are still
emitted but explicitly flagged `grounding_complete=False`, which `safety.py`
penalizes. Nothing is ever fabricated to fill a gap.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..gemini_client import GeminiClient, GeminiUnavailable, parse_json_response
from ..http import ProviderError
from ..models import RawTrendSignal
from .base import BaseProvider

DISCOVERY_PROMPT = """\
You are a research assistant for a US-focused finance YouTube Shorts channel.

Use Google Search to find NOTABLE, VERIFIABLE United States finance stories from
the last {hours} hours across: markets, trading, investing, high-frequency and
quant trading, market microstructure, AI in finance, US economic events, stocks,
bitcoin and digital assets, gold, oil, forex, and Federal Reserve policy.

Return ONLY a JSON array (no prose, no markdown fence) of at most {limit} objects:

[
  {{
    "headline": "<factual headline, no hype>",
    "summary": "<2 sentences of what is actually known>",
    "url": "<the source URL you actually found>",
    "published_at": "<ISO-8601 timestamp if the source states one, else null>",
    "publisher": "<publisher name>",
    "factual_state": "confirmed|forecast|expectation|opinion|rumour|historical"
  }}
]

Hard rules:
- Report ONLY what the search results actually say.
- NEVER invent a URL, a publisher, a timestamp, or a number.
- If you cannot find a real source for an item, omit that item entirely.
- Do NOT estimate search volumes, view counts, engagement or audience size.
- Do NOT give financial advice or predict prices.
"""


class GeminiGroundingProvider(BaseProvider):
    name = "gemini_grounding"

    def __init__(self, settings=None, *, client: GeminiClient | None = None) -> None:
        super().__init__(settings)
        self._client = client

    @property
    def enabled(self) -> bool:
        return self.settings.gemini_grounding_enabled

    @property
    def configured(self) -> bool:
        return bool(self.settings.gemini_api_key.strip())

    async def collect(
        self, *, niche: str, region: str, since: datetime, limit: int
    ) -> list[RawTrendSignal]:
        client = self._client or GeminiClient(self.settings)
        now = datetime.now(timezone.utc)
        hours = max(1, int((now - (since if since.tzinfo else
                                   since.replace(tzinfo=timezone.utc))).total_seconds() // 3600))
        prompt = DISCOVERY_PROMPT.format(hours=hours, limit=min(limit, 20))

        try:
            resp = await client.generate(prompt, use_grounding=True, temperature=0.1)
        except GeminiUnavailable as e:
            raise ProviderError(f"gemini_grounding: {e}") from e

        try:
            items = parse_json_response(resp.text)
        except (ValueError, TypeError) as e:
            raise ProviderError(
                f"gemini_grounding: unparseable response ({type(e).__name__})"
            ) from e
        if isinstance(items, dict):
            items = items.get("items") or items.get("results") or []
        if not isinstance(items, list):
            return []

        # URIs Gemini actually grounded on. A model-asserted URL that appears in no
        # grounding chunk is treated as UNVERIFIED, not as a citation.
        grounded_uris = {
            c["uri"] for c in resp.grounding_chunks if c.get("uri")
        }
        any_metadata = bool(resp.grounding_chunks)

        out: list[RawTrendSignal] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            headline = str(item.get("headline") or "").strip()
            url = item.get("url")
            if not headline:
                continue
            # No URL at all => no citation => we do not accept it as a signal.
            if not url or not isinstance(url, str) or not url.startswith("http"):
                print(f"[ti.grounding] dropped uncited item: {headline[:80]!r}",
                      flush=True)
                continue

            verified = any(
                url.rstrip("/") == g.rstrip("/") or url in g or g in url
                for g in grounded_uris
            )
            published = _parse_dt(item.get("published_at"))

            out.append(RawTrendSignal(
                provider=self.name,
                external_id=url,
                title=headline,
                summary=str(item.get("summary") or "")[:600] or None,
                url=url,
                published_at=published,
                collected_at=now,
                region=region or "US",
                # Intentionally EMPTY: grounding never supplies metrics.
                engagement={},
                raw_metrics={
                    "publisher": item.get("publisher"),
                    "model_reported_state": item.get("factual_state"),
                    "grounding_verified": verified,
                    "grounding_metadata_present": any_metadata,
                    "grounding_chunk_count": len(resp.grounding_chunks),
                    "gemini_model": resp.model,
                },
                author_or_channel=item.get("publisher"),
                # Credibility is decided by host tier in the normalizer. An
                # unverified grounding claim is explicitly demoted.
                source_credibility=None if verified else 0.2,
            ))
        return out


def _parse_dt(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
