"""
Shared Gemini client: SDK loading, retries, budget enforcement, cost accounting.

Uses the current official Google Gen AI SDK (`google-genai`, `from google import
genai`). The import is LAZY and guarded so the whole package — and the entire test
suite — works with the SDK absent and no API key present.

Guarantees:
  * The model name always comes from configuration (GEMINI_MODEL). No preview
    model is ever hardcoded.
  * A daily USD budget is enforced BEFORE the call is made.
  * 429 RESOURCE_EXHAUSTED is retried with exponential backoff + jitter, then
    surfaces as a clean failure so the deterministic fallback takes over.
  * API keys are never logged.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import CostReport
from .settings import TopicIntelligenceSettings, ti_settings


class GeminiUnavailable(RuntimeError):
    """Gemini cannot be used right now (no SDK, no key, budget spent, API down).

    Always non-fatal: every caller falls back to the deterministic path.
    """


class GeminiBudgetExceeded(GeminiUnavailable):
    pass


@dataclass
class GeminiResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_usd: float = 0.0
    grounding_chunks: list[dict] = field(default_factory=list)
    model: str = ""


def _load_sdk():
    """Import google-genai lazily. Absence is a normal, handled condition."""
    try:
        from google import genai                      # type: ignore
        from google.genai import types                # type: ignore
    except ImportError as e:  # pragma: no cover - exercised via monkeypatch
        raise GeminiUnavailable(
            "google-genai SDK is not installed (pip install google-genai) — "
            "falling back to the deterministic ranker"
        ) from e
    return genai, types


class GeminiClient:
    """Thin, testable wrapper. Inject `sdk_factory` in tests to avoid the network."""

    def __init__(
        self,
        settings: TopicIntelligenceSettings | None = None,
        *,
        sdk_factory=_load_sdk,
        spend_today: float = 0.0,
    ) -> None:
        self.settings = settings or ti_settings()
        self._sdk_factory = sdk_factory
        self.cost = CostReport(budget_usd=self.settings.gemini_daily_budget_usd)
        self._prior_spend = spend_today
        self._client = None

    # ------------------------------------------------------------------ budget
    @property
    def spent_usd(self) -> float:
        return round(self._prior_spend + self.cost.estimated_usd, 6)

    def _check_budget(self) -> None:
        budget = self.settings.gemini_daily_budget_usd
        if budget > 0 and self.spent_usd >= budget:
            self.cost.budget_exhausted = True
            raise GeminiBudgetExceeded(
                f"daily Gemini budget exhausted: ${self.spent_usd:.4f} >= "
                f"${budget:.4f} — using the deterministic ranker"
            )

    def _estimate_cost(self, in_tok: int, out_tok: int) -> float:
        s = self.settings
        return round(
            in_tok / 1_000_000 * s.gemini_input_cost_per_mtok
            + out_tok / 1_000_000 * s.gemini_output_cost_per_mtok,
            6,
        )

    # ------------------------------------------------------------------ client
    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self.settings.gemini_api_key.strip():
            raise GeminiUnavailable("GEMINI_API_KEY is not set")
        genai, _types = self._sdk_factory()
        self._client = genai.Client(api_key=self.settings.gemini_api_key.strip())
        return self._client

    # ------------------------------------------------------------------- call
    async def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        response_schema: Any | None = None,
        use_grounding: bool = False,
        temperature: float = 0.2,
    ) -> GeminiResponse:
        """One generation call with retries. Raises GeminiUnavailable on failure."""
        s = self.settings
        self._check_budget()
        client = self._ensure_client()
        _genai, types = self._sdk_factory()

        cfg_kwargs: dict[str, Any] = {"temperature": temperature}
        if system_instruction:
            cfg_kwargs["system_instruction"] = system_instruction
        if use_grounding:
            # Google Search grounding — discovery/verification only.
            cfg_kwargs["tools"] = [
                types.Tool(google_search=types.GoogleSearch())
            ]
        elif response_schema is not None:
            # Structured JSON output. Cannot be combined with tools.
            cfg_kwargs["response_mime_type"] = "application/json"
            cfg_kwargs["response_schema"] = response_schema

        config = types.GenerateContentConfig(**cfg_kwargs)
        last_err: Exception | None = None

        for attempt in range(max(1, s.gemini_max_retries)):
            try:
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=s.gemini_model,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=s.gemini_timeout_s,
                )
                return self._wrap(resp)
            except asyncio.TimeoutError as e:
                last_err = e
            except Exception as e:  # noqa: BLE001 — SDK raises many shapes
                last_err = e
                msg = str(e)
                if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                    # Honour a server-provided retryDelay when present.
                    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+)", msg)
                    delay = float(m.group(1)) if m else None
                    await self._backoff(attempt, delay)
                    continue
                if any(k in msg for k in ("PERMISSION_DENIED", "API_KEY_INVALID",
                                          "INVALID_ARGUMENT", "NOT_FOUND")):
                    raise GeminiUnavailable(f"gemini: non-retryable error: {msg[:300]}") from e
            await self._backoff(attempt, None)

        raise GeminiUnavailable(
            f"gemini: exhausted {s.gemini_max_retries} attempts: "
            f"{type(last_err).__name__}: {str(last_err)[:300]}"
        )

    async def _backoff(self, attempt: int, server_delay: float | None) -> None:
        s = self.settings
        if server_delay is not None:
            await asyncio.sleep(min(server_delay, s.ti_http_backoff_max_s))
            return
        ceiling = min(s.ti_http_backoff_max_s, s.ti_http_backoff_base_s * (2 ** attempt))
        await asyncio.sleep(random.uniform(0.0, ceiling))

    # ------------------------------------------------------------------- wrap
    def _wrap(self, resp: Any) -> GeminiResponse:
        text = getattr(resp, "text", None) or ""
        usage = getattr(resp, "usage_metadata", None)
        in_tok = int(getattr(usage, "prompt_token_count", 0) or 0)
        out_tok = int(getattr(usage, "candidates_token_count", 0) or 0)
        cost = self._estimate_cost(in_tok, out_tok)

        self.cost.gemini_calls += 1
        self.cost.input_tokens += in_tok
        self.cost.output_tokens += out_tok
        self.cost.estimated_usd = round(self.cost.estimated_usd + cost, 6)

        print(
            f"[ti.gemini] model={self.settings.gemini_model} in={in_tok} out={out_tok} "
            f"cost=${cost:.6f} run_total=${self.cost.estimated_usd:.6f}",
            flush=True,
        )
        return GeminiResponse(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            estimated_usd=cost, grounding_chunks=extract_grounding_chunks(resp),
            model=self.settings.gemini_model,
        )


def extract_grounding_chunks(resp: Any) -> list[dict]:
    """Pull citation metadata out of a grounded response.

    Returns one dict per chunk with `uri`, `title`, and `complete` — where
    `complete=False` marks a chunk whose source metadata Gemini did not supply.
    Incomplete chunks are kept and FLAGGED, never silently dropped or invented.
    """
    out: list[dict] = []
    for cand in getattr(resp, "candidates", None) or []:
        meta = getattr(cand, "grounding_metadata", None)
        if meta is None:
            continue
        for chunk in getattr(meta, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None) if web else None
            title = getattr(web, "title", None) if web else None
            out.append({
                "uri": uri, "title": title or "",
                "complete": bool(uri and title),
            })
        for q in getattr(meta, "web_search_queries", None) or []:
            out.append({"uri": None, "title": f"search_query: {q}", "complete": False})
    return out


def parse_json_response(text: str) -> Any:
    """Parse model output that *should* be JSON but may be fenced or prefixed."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty Gemini response")
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = min(
            (i for i in (raw.find("{"), raw.find("[")) if i >= 0), default=-1
        )
        end = max(raw.rfind("}"), raw.rfind("]"))
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
        raise


def utc_day_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def next_day_start() -> datetime:
    return utc_day_start() + timedelta(days=1)
