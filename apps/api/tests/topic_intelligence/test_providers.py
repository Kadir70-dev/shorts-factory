"""
Provider-layer tests (requirements 1, 2, 14).

  1. A provider timeout does not kill the entire run.
  2. YouTube signals are normalized correctly.
 14. The X provider stays disabled without credentials.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.topic_intelligence.http import ProviderError
from app.topic_intelligence.models import SourceTier
from app.topic_intelligence.normalizer import normalize_signal
from app.topic_intelligence.providers import build_providers
from app.topic_intelligence.providers.x_api import XProvider
from app.topic_intelligence.settings import TopicIntelligenceSettings

from .conftest import StubProvider
from .fixtures import FOMC_SIGNALS, NOW, NVDA_SIGNALS

SINCE = NOW - timedelta(hours=48)


# --------------------------------------------------------------------------- #
# 1. provider timeout / failure isolation
# --------------------------------------------------------------------------- #
async def test_provider_timeout_does_not_kill_the_run(settings):
    """A hanging provider is abandoned; healthy providers still deliver."""
    settings.ti_provider_timeout_s = 0.05     # run() allows 2x this
    slow = StubProvider("slow_one", FOMC_SIGNALS, delay=5.0, settings=settings)
    healthy = StubProvider("healthy_one", NVDA_SIGNALS, settings=settings)

    results = await asyncio.gather(*[
        p.run(niche="usa_finance", region="US", since=SINCE, limit=50)
        for p in (slow, healthy)
    ])
    (slow_signals, slow_status), (ok_signals, ok_status) = results

    assert slow_signals == []
    assert slow_status.ok is False
    assert "timeout" in (slow_status.error or "")
    # The healthy provider is entirely unaffected.
    assert ok_status.ok is True
    assert len(ok_signals) == len(NVDA_SIGNALS)


async def test_provider_exception_is_contained(settings):
    boom = StubProvider("boom", exc=ProviderError("upstream 500"), settings=settings)
    signals, status = await boom.run(
        niche="usa_finance", region="US", since=SINCE, limit=10
    )
    assert signals == []
    assert status.ok is False
    assert "upstream 500" in status.error


async def test_unexpected_exception_is_contained(settings):
    """Even a plain bug in a connector must not propagate."""
    broken = StubProvider("broken", exc=ValueError("bad parse"), settings=settings)
    signals, status = await broken.run(
        niche="usa_finance", region="US", since=SINCE, limit=10
    )
    assert signals == []
    assert "ValueError: bad parse" in status.error


async def test_disabled_and_unconfigured_providers_report_reasons(settings):
    disabled = StubProvider("d", enabled=False, settings=settings)
    unconfigured = StubProvider("u", configured=False, settings=settings)

    _, s1 = await disabled.run(niche="n", region="US", since=SINCE, limit=1)
    _, s2 = await unconfigured.run(niche="n", region="US", since=SINCE, limit=1)

    assert s1.skipped_reason == "disabled by feature flag"
    assert "missing credentials" in s2.skipped_reason


async def test_stale_provider_is_flagged(settings):
    settings.ti_stale_after_hours = 1.0
    old = FOMC_SIGNALS[0].model_copy(update={
        "published_at": datetime.now(timezone.utc) - timedelta(days=5)
    })
    p = StubProvider("stale_one", [old], settings=settings)
    signals, status = await p.run(niche="n", region="US", since=SINCE, limit=5)
    assert status.ok is True and len(signals) == 1
    assert status.stale is True


# --------------------------------------------------------------------------- #
# 2. YouTube normalization
# --------------------------------------------------------------------------- #
def test_youtube_signal_is_normalized_correctly():
    sig = FOMC_SIGNALS[2]      # 48,000 views, 1h old, 120k-sub channel
    n = normalize_signal(sig, now=NOW)

    m = n.normalized_metrics
    # 48000 views over a 1h-floored age.
    assert m["views_per_hour"] == pytest.approx(48000.0, rel=0.01)
    assert m["like_velocity"] == pytest.approx(2100.0, rel=0.01)
    assert m["comment_velocity"] == pytest.approx(310.0, rel=0.01)
    assert m["channel_subscribers"] == 120000.0
    # Breakout ratio: views relative to the channel's own size.
    assert m["views_per_subscriber"] == pytest.approx(0.4, rel=0.01)

    # Meaning extraction.
    assert n.event_type.value == "fed_decision"
    assert "federal reserve" in n.entities or "fomc" in n.entities
    # A YouTube video is an interest signal, never a credible source.
    assert n.source_tier is SourceTier.social
    assert n.credibility <= 0.3
    # Raw metrics survive untouched.
    assert n.raw.raw_metrics["video_id"] == "yt_fomc_1"


def test_youtube_age_floor_prevents_absurd_velocity():
    """A 5-minute-old video with 100 views must not report 1200 views/hour."""
    sig = FOMC_SIGNALS[2].model_copy(update={
        "published_at": NOW - timedelta(minutes=5),
        "engagement": {"views": 100.0},
    })
    n = normalize_signal(sig, now=NOW)
    assert n.normalized_metrics["views_per_hour"] == 100.0


def test_absent_metrics_are_never_defaulted_to_zero():
    """A provider that reports no likes must not produce like_velocity=0."""
    sig = FOMC_SIGNALS[2].model_copy(update={"engagement": {"views": 1000.0}})
    n = normalize_signal(sig, now=NOW)
    assert "views_per_hour" in n.normalized_metrics
    assert "like_velocity" not in n.normalized_metrics
    assert "comment_velocity" not in n.normalized_metrics


# --------------------------------------------------------------------------- #
# 14. X stays disabled without credentials
# --------------------------------------------------------------------------- #
def test_x_provider_disabled_without_credentials():
    s = TopicIntelligenceSettings(x_trends_enabled=True, x_bearer_token="")
    p = XProvider(s)
    assert p.enabled is True          # the flag is on...
    assert p.configured is False      # ...but there is no token
    assert p.usable is False
    assert s.x_usable is False


async def test_x_provider_never_calls_the_api_without_a_token():
    s = TopicIntelligenceSettings(x_trends_enabled=True, x_bearer_token="")
    p = XProvider(s)
    called = False

    async def _fail(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("collect() must not run without credentials")

    p.collect = _fail  # type: ignore[method-assign]
    signals, status = await p.run(
        niche="usa_finance", region="US", since=SINCE, limit=10
    )
    assert called is False
    assert signals == []
    assert status.ok is False
    assert "missing credentials" in status.skipped_reason


def test_x_provider_usable_only_with_flag_and_token():
    on = TopicIntelligenceSettings(x_trends_enabled=True, x_bearer_token="tok")
    off = TopicIntelligenceSettings(x_trends_enabled=False, x_bearer_token="tok")
    assert XProvider(on).usable is True
    assert XProvider(off).usable is False


def test_default_provider_set_is_optional_and_mostly_off():
    """Nothing in the default configuration requires a paid provider."""
    s = TopicIntelligenceSettings(
        google_trends_enabled=False, reddit_enabled=False, x_trends_enabled=False,
        economic_calendar_enabled=False, youtube_data_api_key="", gemini_api_key="",
    )
    providers = build_providers(s)
    assert {p.name for p in providers} == {
        "google_trends", "youtube", "reddit", "x", "economic_calendar",
        "finance_news", "gemini_grounding",
    }
    # Only the free, keyless RSS news provider is usable out of the box.
    assert [p.name for p in providers if p.usable] == ["finance_news"]
