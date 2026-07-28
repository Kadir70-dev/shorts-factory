"""
X / Twitter connector — OFFICIAL API ONLY (recent search, v2).

There is NO scraping here and there never should be. Recent search requires a paid
tier on current X plans, so this provider:

  * is OFF by default (`X_TRENDS_ENABLED=false`),
  * auto-disables itself when `X_BEARER_TOKEN` is absent,
  * treats a 403 (plan lacks access) as a clean, non-fatal skip.

X is a velocity/attention signal only. Bot risk and author concentration are
computed so that amplification is not mistaken for interest.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from ..http import ProviderError, request_json
from ..models import RawTrendSignal
from .base import BaseProvider

API = "https://api.x.com/2/tweets/search/recent"

# Deliberately narrow: recent-search quota is small and expensive.
X_QUERIES: tuple[str, ...] = (
    "(fed OR fomc OR powell) (rates OR inflation) -is:retweet lang:en",
    "(cpi OR inflation OR pce) -is:retweet lang:en",
    "(bitcoin OR btc) (price OR etf) -is:retweet lang:en",
    "(nvda OR nvidia) (earnings OR ai) -is:retweet lang:en",
    "(gold OR oil OR wti) price -is:retweet lang:en",
)


def _parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


class XProvider(BaseProvider):
    name = "x"

    @property
    def enabled(self) -> bool:
        return self.settings.x_trends_enabled

    @property
    def configured(self) -> bool:
        # Missing credentials == not configured == silently skipped. X is never
        # allowed to be a hard dependency.
        return bool(self.settings.x_bearer_token.strip())

    async def collect(
        self, *, niche: str, region: str, since: datetime, limit: int
    ) -> list[RawTrendSignal]:
        s = self.settings
        headers = {"Authorization": f"Bearer {s.x_bearer_token.strip()}"}
        start = (since if since.tzinfo else since.replace(tzinfo=timezone.utc))
        now = datetime.now(timezone.utc)
        out: list[RawTrendSignal] = []

        for query in X_QUERIES:
            try:
                data = await request_json(
                    "GET", API, breaker_key=self.name, headers=headers,
                    params={
                        "query": query,
                        "max_results": max(10, min(100, s.x_max_results)),
                        "start_time": start.astimezone(timezone.utc)
                                           .strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "tweet.fields": "created_at,public_metrics,author_id,lang,entities",
                        "expansions": "author_id",
                        "user.fields": "public_metrics,verified,description",
                    },
                )
            except ProviderError as e:
                if "HTTP 403" in str(e) or "HTTP 401" in str(e):
                    # Plan does not include recent search, or the token is invalid.
                    raise ProviderError(
                        "x: API access denied (403/401) — recent search requires a "
                        "paid X plan; provider skipped"
                    ) from e
                print(f"[ti.x] query failed: {e}", flush=True)
                continue

            tweets = data.get("data", []) or []
            if not tweets:
                continue
            users = {
                u["id"]: u
                for u in ((data.get("includes") or {}).get("users") or [])
            }
            authors = Counter(t.get("author_id") for t in tweets if t.get("author_id"))
            unique_authors = len(authors)
            hashtags = Counter(
                tag.get("tag", "").lower()
                for t in tweets
                for tag in ((t.get("entities") or {}).get("hashtags") or [])
            )
            top_hashtag_share = (
                hashtags.most_common(1)[0][1] / max(1, sum(hashtags.values()))
                if hashtags else 0.0
            )
            # A "finance account" heuristic: verified, or a finance-ish bio.
            finance_accounts = sum(
                1 for u in users.values()
                if u.get("verified")
                or any(k in (u.get("description") or "").lower()
                       for k in ("market", "trading", "invest", "finance", "macro",
                                 "econom", "crypto"))
            )
            finance_concentration = finance_accounts / max(1, len(users))

            agg_likes = sum(
                float((t.get("public_metrics") or {}).get("like_count", 0)) for t in tweets)
            agg_rts = sum(
                float((t.get("public_metrics") or {}).get("retweet_count", 0)) for t in tweets)
            agg_replies = sum(
                float((t.get("public_metrics") or {}).get("reply_count", 0)) for t in tweets)

            # One aggregated signal per query — individual tweets are noise, the
            # conversation volume is the signal.
            newest = max(
                (_parse_dt(t.get("created_at")) for t in tweets if t.get("created_at")),
                default=None,
            )
            sample = max(
                tweets,
                key=lambda t: float((t.get("public_metrics") or {}).get("like_count", 0)),
            )
            out.append(RawTrendSignal(
                provider=self.name,
                external_id=sample.get("id"),
                title=(sample.get("text") or "")[:280],
                summary=f"X conversation volume for query: {query}",
                url=f"https://x.com/i/status/{sample.get('id')}" if sample.get("id") else None,
                published_at=newest,
                collected_at=now,
                region=None,
                engagement={
                    "mentions": float(len(tweets)),
                    "likes": agg_likes,
                    "retweets": agg_rts,
                    "replies": agg_replies,
                },
                raw_metrics={
                    "query": query,
                    "unique_authors": unique_authors,
                    "top_author_share": (
                        authors.most_common(1)[0][1] / max(1, len(tweets))
                        if authors else 0.0
                    ),
                    "hashtag_concentration": round(top_hashtag_share, 4),
                    "finance_account_concentration": round(finance_concentration, 4),
                    "sampled_tweets": len(tweets),
                },
                author_or_channel="x_aggregate",
                source_credibility=None,
            ))
            if len(out) >= limit:
                break
        return out
