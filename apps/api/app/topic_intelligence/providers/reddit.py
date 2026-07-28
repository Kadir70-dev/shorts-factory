"""
Reddit connector via the OFFICIAL API (OAuth2 client-credentials).

Reddit is a PUBLIC-INTEREST signal only. Upvotes are never treated as evidence
that a claim is true — `entities.classify_source` pins every Reddit item to the
`social` tier, and `safety.py` blocks any social-only factual claim. This module
just measures how much people are talking, and how unusually.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from ..http import ProviderError, request_json
from ..models import RawTrendSignal
from .base import BaseProvider

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"


class RedditProvider(BaseProvider):
    name = "reddit"

    def __init__(self, settings=None) -> None:
        super().__init__(settings)
        self._token: str | None = None
        self._token_expires: float = 0.0

    @property
    def enabled(self) -> bool:
        return self.settings.reddit_enabled

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.reddit_client_id.strip()
            and self.settings.reddit_client_secret.strip()
        )

    @property
    def _user_agent(self) -> str:
        return (
            self.settings.reddit_user_agent.strip()
            or "python:shorts-factory.topic-intelligence:2a (by /u/unknown)"
        )

    async def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        data = await request_json(
            "POST", TOKEN_URL, breaker_key=self.name,
            data={"grant_type": "client_credentials"},
            auth=(self.settings.reddit_client_id.strip(),
                  self.settings.reddit_client_secret.strip()),
            headers={"User-Agent": self._user_agent},
            cache_ttl=0,     # never cache credentials
        )
        token = data.get("access_token")
        if not token:
            raise ProviderError("reddit: no access_token in response")
        self._token = token
        self._token_expires = time.time() + float(data.get("expires_in", 3600))
        return token

    async def collect(
        self, *, niche: str, region: str, since: datetime, limit: int
    ) -> list[RawTrendSignal]:
        s = self.settings
        token = await self._access_token()
        headers = {"Authorization": f"Bearer {token}", "User-Agent": self._user_agent}
        since_ts = (since if since.tzinfo else since.replace(tzinfo=timezone.utc)).timestamp()
        now = datetime.now(timezone.utc)

        # Title -> the subs it appeared in, for cross-subreddit spread.
        seen_titles: dict[str, set[str]] = {}
        collected: list[tuple[dict, str]] = []

        for sub in s.subreddits:
            try:
                data = await request_json(
                    "GET", f"{API}/r/{sub}/hot", breaker_key=self.name,
                    params={"limit": min(100, s.reddit_posts_per_sub)},
                    headers=headers,
                )
            except Exception as e:  # noqa: BLE001 — a private/banned sub is not fatal
                print(f"[ti.reddit] r/{sub} failed: {type(e).__name__}: {e}", flush=True)
                continue
            for child in (data.get("data", {}) or {}).get("children", []):
                post = child.get("data") or {}
                created = float(post.get("created_utc") or 0)
                if created < since_ts:
                    continue
                if post.get("stickied") or post.get("over_18"):
                    continue
                title = (post.get("title") or "").strip()
                if not title:
                    continue
                seen_titles.setdefault(title.lower()[:120], set()).add(sub)
                collected.append((post, sub))
            if len(collected) >= limit:
                break

        out: list[RawTrendSignal] = []
        for post, sub in collected[:limit]:
            title = (post.get("title") or "").strip()
            created = float(post.get("created_utc") or 0)
            published = datetime.fromtimestamp(created, tz=timezone.utc) if created else None
            spread = len(seen_titles.get(title.lower()[:120], {sub}))
            permalink = post.get("permalink") or ""

            out.append(RawTrendSignal(
                provider=self.name,
                external_id=post.get("id"),
                title=title,
                summary=(post.get("selftext") or "")[:600] or None,
                url=f"https://www.reddit.com{permalink}" if permalink else post.get("url"),
                published_at=published,
                collected_at=now,
                region=None,        # Reddit does not expose reliable geo per post
                engagement={
                    "score": float(post.get("score") or 0),
                    "comments": float(post.get("num_comments") or 0),
                    "awards": float(post.get("total_awards_received") or 0),
                },
                raw_metrics={
                    "subreddit": sub,
                    "upvote_ratio": post.get("upvote_ratio"),
                    "cross_subreddit_spread": spread,
                    "link_flair": post.get("link_flair_text"),
                    "is_self": post.get("is_self"),
                    "domain": post.get("domain"),
                    "num_crossposts": post.get("num_crossposts"),
                },
                author_or_channel=f"r/{sub}",
                # Deliberately None: credibility comes from the social tier cap,
                # never from engagement.
                source_credibility=None,
            ))
        return out
