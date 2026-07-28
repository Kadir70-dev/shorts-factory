"""Shared stubs for the topic-intelligence tests. No network, no API keys."""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from app.topic_intelligence.gemini_client import GeminiClient, GeminiResponse
from app.topic_intelligence.models import ProviderStatus, RawTrendSignal
from app.topic_intelligence.providers.base import BaseProvider


class StubProvider(BaseProvider):
    """A provider whose behaviour is fully scripted."""

    def __init__(self, name: str, signals=None, *, enabled=True, configured=True,
                 exc: Exception | None = None, delay: float = 0.0, settings=None):
        super().__init__(settings)
        self.name = name
        self._signals = list(signals or [])
        self._enabled = enabled
        self._configured = configured
        self._exc = exc
        self._delay = delay
        self.calls = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def configured(self) -> bool:
        return self._configured

    async def collect(self, *, niche: str, region: str, since: datetime,
                      limit: int) -> list[RawTrendSignal]:
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc:
            raise self._exc
        return list(self._signals)


class StubGeminiClient(GeminiClient):
    """A GeminiClient that returns canned text (or raises) without any SDK."""

    def __init__(self, *, responses=None, exc: Exception | None = None,
                 settings=None, spend_today: float = 0.0,
                 input_tokens: int = 1200, output_tokens: int = 400):
        super().__init__(settings, sdk_factory=lambda: (None, None),
                         spend_today=spend_today)
        self._responses = list(responses or [])
        self._exc = exc
        self._in = input_tokens
        self._out = output_tokens
        self.calls = 0
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **kwargs) -> GeminiResponse:
        self.calls += 1
        self.prompts.append(prompt)
        # Budget is enforced identically to the real client.
        self._check_budget()
        if self._exc:
            raise self._exc
        text = self._responses.pop(0) if self._responses else "{}"
        cost = self._estimate_cost(self._in, self._out)
        self.cost.gemini_calls += 1
        self.cost.input_tokens += self._in
        self.cost.output_tokens += self._out
        self.cost.estimated_usd = round(self.cost.estimated_usd + cost, 6)
        return GeminiResponse(
            text=text, input_tokens=self._in, output_tokens=self._out,
            estimated_usd=cost, model=self.settings.gemini_model,
        )


@pytest.fixture
def settings():
    from app.topic_intelligence.settings import TopicIntelligenceSettings

    return TopicIntelligenceSettings(
        gemini_api_key="", gemini_ranker_enabled=True,
        gemini_grounding_enabled=False, ti_auto_enqueue=False,
        youtube_data_api_key="", reddit_enabled=False, x_trends_enabled=False,
    )


@pytest.fixture
def brief():
    from app.topic_intelligence.config_types import ChannelBrief

    return ChannelBrief(channel_id="usa_trading", name="USA Trading & Markets",
                        niche="usa_finance")


def status_by_name(statuses: list[ProviderStatus]) -> dict[str, ProviderStatus]:
    return {s.name: s for s in statuses}
