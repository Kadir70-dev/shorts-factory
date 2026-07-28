"""
Finance news connector — configurable RSS feeds and/or NewsAPI.

RSS is parsed with the stdlib (`xml.etree`), so no extra dependency and no key is
required for the default feed set. NewsAPI is used additionally when NEWS_API_KEY
is set.

Syndication handling: the same wire story is published by dozens of outlets. This
provider tags each item with a `syndication_group` (a normalized-title hash) and a
`syndication_count`, so downstream clustering can collapse 20 copies of a press
release into ONE independent confirmation. Counting copies as corroboration is the
single easiest way to convince yourself a rumour is true.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from ..entities import classify_source, host_of
from ..http import request_json
from ..models import RawTrendSignal, SourceTier
from .base import BaseProvider

NEWSAPI_URL = "https://newsapi.org/v2/everything"
NEWSAPI_QUERY = (
    "(federal reserve OR inflation OR CPI OR stock market OR bitcoin OR gold OR "
    "oil prices OR treasury yields OR earnings OR forex)"
)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_ATOM = "{http://www.w3.org/2005/Atom}"


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return _WS.sub(" ", _TAG.sub(" ", text)).strip()[:600] or None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)          # RFC-822 (RSS)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))   # ISO (Atom)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def syndication_group(title: str) -> str:
    """Normalized-title hash. Identical wire copy across outlets -> same group."""
    norm = re.sub(r"[^a-z0-9 ]", " ", (title or "").lower())
    tokens = sorted(set(t for t in norm.split() if len(t) > 2))
    return hashlib.sha1(" ".join(tokens).encode()).hexdigest()[:12]


class FinanceNewsProvider(BaseProvider):
    name = "finance_news"

    @property
    def enabled(self) -> bool:
        return self.settings.finance_news_enabled

    @property
    def configured(self) -> bool:
        return bool(self.settings.news_feeds or self.settings.news_api_key.strip())

    # -------------------------------------------------------------------- RSS
    async def _fetch_rss(self, url: str, limit: int) -> list[dict]:
        text = await request_json(
            "GET", url, breaker_key=self.name, expect_json=False,
            headers={"User-Agent": "shorts-factory-topic-intelligence/2a"},
        )
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError as e:
            print(f"[ti.news] unparseable feed {url}: {e}", flush=True)
            return []

        items: list[dict] = []
        # RSS 2.0
        for item in root.iter("item"):
            items.append({
                "title": (item.findtext("title") or "").strip(),
                "summary": _strip_html(item.findtext("description")),
                "url": (item.findtext("link") or "").strip() or None,
                "published": _parse_date(item.findtext("pubDate")),
                "id": item.findtext("guid"),
                "feed": url,
            })
        # Atom
        for entry in root.iter(f"{_ATOM}entry"):
            link_el = entry.find(f"{_ATOM}link")
            items.append({
                "title": (entry.findtext(f"{_ATOM}title") or "").strip(),
                "summary": _strip_html(
                    entry.findtext(f"{_ATOM}summary")
                    or entry.findtext(f"{_ATOM}content")
                ),
                "url": (link_el.get("href") if link_el is not None else None),
                "published": _parse_date(
                    entry.findtext(f"{_ATOM}updated")
                    or entry.findtext(f"{_ATOM}published")
                ),
                "id": entry.findtext(f"{_ATOM}id"),
                "feed": url,
            })
        return [i for i in items if i["title"]][:limit]

    # ---------------------------------------------------------------- NewsAPI
    async def _fetch_newsapi(self, since: datetime, limit: int) -> list[dict]:
        data = await request_json(
            "GET", NEWSAPI_URL, breaker_key=self.name,
            params={
                "q": NEWSAPI_QUERY, "language": "en", "sortBy": "publishedAt",
                "pageSize": min(100, limit),
                "from": since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            },
            headers={"X-Api-Key": self.settings.news_api_key.strip()},
        )
        out = []
        for a in (data or {}).get("articles", []):
            out.append({
                "title": (a.get("title") or "").strip(),
                "summary": _strip_html(a.get("description") or a.get("content")),
                "url": a.get("url"),
                "published": _parse_date(a.get("publishedAt")),
                "id": a.get("url"),
                "feed": "newsapi",
                "publisher": (a.get("source") or {}).get("name"),
            })
        return [o for o in out if o["title"]]

    # ---------------------------------------------------------------- collect
    async def collect(
        self, *, niche: str, region: str, since: datetime, limit: int
    ) -> list[RawTrendSignal]:
        s = self.settings
        since = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        per_feed = max(1, s.news_articles_per_feed)
        rows: list[dict] = []

        for feed in s.news_feeds:
            try:
                rows.extend(await self._fetch_rss(feed, per_feed))
            except Exception as e:  # noqa: BLE001 — one dead feed is not a failure
                print(f"[ti.news] feed failed {feed}: {type(e).__name__}: {e}",
                      flush=True)

        if s.news_api_key.strip():
            try:
                rows.extend(await self._fetch_newsapi(since, limit))
            except Exception as e:  # noqa: BLE001
                print(f"[ti.news] newsapi failed: {type(e).__name__}: {e}", flush=True)

        # Drop anything older than the window, then measure syndication.
        rows = [
            r for r in rows
            if r.get("published") is None or r["published"] >= since
        ]
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            groups[syndication_group(r["title"])].append(r)

        now = datetime.now(timezone.utc)
        out: list[RawTrendSignal] = []
        for gid, members in groups.items():
            # Keep the MOST CREDIBLE copy as the representative; the rest only
            # contribute to syndication_count.
            def cred(row: dict) -> float:
                tier = classify_source(row.get("url"), self.name)
                return {
                    SourceTier.primary: 1.0, SourceTier.wire: 0.85,
                    SourceTier.reputable: 0.7, SourceTier.aggregator: 0.45,
                    SourceTier.social: 0.25, SourceTier.unknown: 0.35,
                }[tier]

            rep = max(members, key=cred)
            publishers = sorted({
                (m.get("publisher") or host_of(m.get("url")) or m.get("feed") or "")
                for m in members
            } - {""})

            out.append(RawTrendSignal(
                provider=self.name,
                external_id=rep.get("id") or rep.get("url"),
                title=rep["title"],
                summary=rep.get("summary"),
                url=rep.get("url"),
                published_at=rep.get("published"),
                collected_at=now,
                region=region or "US",
                engagement={},
                raw_metrics={
                    "syndication_group": gid,
                    "syndication_count": len(members),
                    "publishers": publishers[:15],
                    "publisher_count": len(publishers),
                    "feed": rep.get("feed"),
                },
                author_or_channel=rep.get("publisher") or host_of(rep.get("url")),
                # Tiering is host-based in the normalizer; nothing asserted here.
                source_credibility=None,
            ))
            if len(out) >= limit:
                break
        return out
