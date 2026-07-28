"""
GeminiClient + Google Search grounding.

The SDK is stubbed, so these run with no key and no network while still
exercising the real client code path (config building, retry, cost accounting,
grounding-metadata extraction, citation discipline).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.topic_intelligence.gemini_client import (
    GeminiClient,
    GeminiUnavailable,
    extract_grounding_chunks,
)
from app.topic_intelligence.http import ProviderError
from app.topic_intelligence.providers.gemini_grounding import GeminiGroundingProvider
from app.topic_intelligence.settings import TopicIntelligenceSettings

SINCE = datetime.now(timezone.utc) - timedelta(hours=24)


# --------------------------------------------------------------------------- #
# A minimal stand-in for the google-genai SDK.
# --------------------------------------------------------------------------- #
class _FakeTypes:
    class Tool:
        def __init__(self, **kw):
            self.kw = kw

    class GoogleSearch:
        pass

    class GenerateContentConfig:
        def __init__(self, **kw):
            self.kw = kw


class _FakeModels:
    def __init__(self, response, *, errors=None):
        self._response = response
        self._errors = list(errors or [])
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self._errors:
            raise self._errors.pop(0)
        return self._response


class _FakeClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.models = None


def _sdk(response, *, errors=None):
    models = _FakeModels(response, errors=errors)

    class _Genai:
        @staticmethod
        def Client(api_key):
            c = _FakeClient(api_key)
            c.models = models
            return c

    return (lambda: (_Genai, _FakeTypes)), models


def _response(text, *, in_tok=100, out_tok=50, chunks=None):
    meta = None
    if chunks is not None:
        meta = SimpleNamespace(
            grounding_chunks=[
                SimpleNamespace(web=SimpleNamespace(uri=u, title=t))
                for u, t in chunks
            ],
            web_search_queries=[],
        )
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=in_tok, candidates_token_count=out_tok
        ),
        candidates=[SimpleNamespace(grounding_metadata=meta)],
    )


def _settings(**over):
    base = dict(gemini_api_key="test-key", gemini_model="gemini-2.5-flash",
                gemini_grounding_enabled=True, gemini_max_retries=3,
                ti_http_backoff_base_s=0.001, ti_http_backoff_max_s=0.002)
    base.update(over)
    return TopicIntelligenceSettings(**base)


# --------------------------------------------------------------------------- #
# client behaviour
# --------------------------------------------------------------------------- #
async def test_model_comes_from_configuration_not_a_hardcoded_preview():
    s = _settings(gemini_model="gemini-2.0-flash")
    factory, models = _sdk(_response('{"ok":1}'))
    out = await GeminiClient(s, sdk_factory=factory).generate("hi")
    assert models.calls[0]["model"] == "gemini-2.0-flash"
    assert out.model == "gemini-2.0-flash"


async def test_cost_and_tokens_are_accounted():
    s = _settings(gemini_input_cost_per_mtok=1.0, gemini_output_cost_per_mtok=2.0)
    factory, _m = _sdk(_response("{}", in_tok=1_000_000, out_tok=500_000))
    client = GeminiClient(s, sdk_factory=factory)
    out = await client.generate("hi")
    assert out.estimated_usd == pytest.approx(2.0)
    assert client.cost.gemini_calls == 1
    assert client.cost.input_tokens == 1_000_000
    assert client.spent_usd == pytest.approx(2.0)


async def test_missing_api_key_is_a_clean_unavailable():
    s = _settings(gemini_api_key="")
    factory, _m = _sdk(_response("{}"))
    with pytest.raises(GeminiUnavailable, match="GEMINI_API_KEY"):
        await GeminiClient(s, sdk_factory=factory).generate("hi")


async def test_missing_sdk_is_a_clean_unavailable():
    def _no_sdk():
        raise GeminiUnavailable("google-genai SDK is not installed")

    with pytest.raises(GeminiUnavailable, match="not installed"):
        await GeminiClient(_settings(), sdk_factory=_no_sdk).generate("hi")


async def test_rate_limit_is_retried_then_succeeds():
    s = _settings()
    factory, models = _sdk(
        _response('{"ok":1}'),
        errors=[Exception("429 RESOURCE_EXHAUSTED retryDelay: 0")],
    )
    out = await GeminiClient(s, sdk_factory=factory).generate("hi")
    assert out.text == '{"ok":1}'
    assert len(models.calls) == 2


async def test_rate_limit_exhausts_retries_and_falls_back():
    s = _settings(gemini_max_retries=2)
    factory, models = _sdk(
        _response("{}"),
        errors=[Exception("429 RESOURCE_EXHAUSTED")] * 2,
    )
    with pytest.raises(GeminiUnavailable, match="exhausted"):
        await GeminiClient(s, sdk_factory=factory).generate("hi")
    assert len(models.calls) == 2


async def test_invalid_key_is_not_retried():
    s = _settings()
    factory, models = _sdk(_response("{}"), errors=[Exception("API_KEY_INVALID")])
    with pytest.raises(GeminiUnavailable, match="non-retryable"):
        await GeminiClient(s, sdk_factory=factory).generate("hi")
    assert len(models.calls) == 1


async def test_api_key_is_never_logged(capsys):
    s = _settings(gemini_api_key="super-secret-key-abc123")
    factory, _m = _sdk(_response("{}"))
    await GeminiClient(s, sdk_factory=factory).generate("hi")
    captured = capsys.readouterr()
    assert "super-secret-key-abc123" not in captured.out
    assert "super-secret-key-abc123" not in captured.err
    assert "[ti.gemini]" in captured.out          # it did log the cost line


async def test_grounding_tool_is_only_attached_when_requested():
    s = _settings()
    factory, models = _sdk(_response("{}"))
    client = GeminiClient(s, sdk_factory=factory)

    await client.generate("a", use_grounding=True)
    assert "tools" in models.calls[0]["config"].kw

    await client.generate("b", use_grounding=False, response_schema=dict)
    cfg = models.calls[1]["config"].kw
    assert "tools" not in cfg
    assert cfg["response_mime_type"] == "application/json"


def test_grounding_chunk_extraction_flags_incomplete_metadata():
    resp = _response("x", chunks=[
        ("https://www.reuters.com/a", "Reuters story"),
        (None, None),
    ])
    chunks = extract_grounding_chunks(resp)
    assert chunks[0]["complete"] is True
    assert chunks[1]["complete"] is False


# --------------------------------------------------------------------------- #
# grounding provider: citation discipline
# --------------------------------------------------------------------------- #
async def test_grounding_drops_items_without_a_url():
    s = _settings()
    payload = (
        '[{"headline":"Fed cuts rates","summary":"s","url":'
        '"https://www.reuters.com/a","publisher":"Reuters"},'
        '{"headline":"Uncited claim","summary":"s","url":null,"publisher":"?"}]'
    )
    factory, _m = _sdk(_response(payload, chunks=[
        ("https://www.reuters.com/a", "Reuters"),
    ]))
    provider = GeminiGroundingProvider(s, client=GeminiClient(s, sdk_factory=factory))
    signals = await provider.collect(
        niche="usa_finance", region="US", since=SINCE, limit=10
    )
    assert len(signals) == 1
    assert signals[0].title == "Fed cuts rates"


async def test_grounding_marks_unverified_urls_and_carries_no_metrics():
    """A URL the model asserted but never actually grounded on is demoted."""
    s = _settings()
    payload = (
        '[{"headline":"Verified story","url":"https://www.reuters.com/a"},'
        '{"headline":"Model-asserted story","url":"https://example.invalid/b"}]'
    )
    factory, _m = _sdk(_response(payload, chunks=[
        ("https://www.reuters.com/a", "Reuters"),
    ]))
    provider = GeminiGroundingProvider(s, client=GeminiClient(s, sdk_factory=factory))
    signals = await provider.collect(
        niche="usa_finance", region="US", since=SINCE, limit=10
    )
    by_title = {x.title: x for x in signals}

    assert by_title["Verified story"].raw_metrics["grounding_verified"] is True
    assert by_title["Model-asserted story"].raw_metrics["grounding_verified"] is False
    assert by_title["Model-asserted story"].source_credibility == 0.2
    # Grounding must never contribute engagement/trend metrics.
    assert all(x.engagement == {} for x in signals)


async def test_grounding_provider_failure_is_non_fatal():
    s = _settings()
    factory, _m = _sdk(_response("{}"), errors=[Exception("API_KEY_INVALID")])
    provider = GeminiGroundingProvider(s, client=GeminiClient(s, sdk_factory=factory))
    signals, status = await provider.run(
        niche="usa_finance", region="US", since=SINCE, limit=5
    )
    assert signals == []
    assert status.ok is False
    assert "gemini_grounding" in (status.error or "")


async def test_grounding_unparseable_response_is_non_fatal():
    s = _settings()
    factory, _m = _sdk(_response("I could not find anything useful."))
    provider = GeminiGroundingProvider(s, client=GeminiClient(s, sdk_factory=factory))
    with pytest.raises(ProviderError, match="unparseable"):
        await provider.collect(niche="usa_finance", region="US", since=SINCE, limit=5)


def test_grounding_is_disabled_without_a_key():
    s = TopicIntelligenceSettings(gemini_grounding_enabled=True, gemini_api_key="")
    p = GeminiGroundingProvider(s)
    assert p.enabled is True
    assert p.configured is False
    assert p.usable is False
