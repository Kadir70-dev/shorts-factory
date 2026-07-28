"""
Resilience primitives shared by every provider: timeouts, retry with exponential
backoff + full jitter, rate-limit awareness, a TTL response cache, and a per-host
circuit breaker.

No provider is allowed to call httpx directly — that would bypass the breaker and
the quota guards. All of this is dependency-free apart from httpx and is fully
exercisable in tests via a transport stub.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from .settings import ti_settings


class ProviderError(RuntimeError):
    """Any provider-level failure. Always caught by the service; never fatal."""


class CircuitOpen(ProviderError):
    pass


class RateLimited(ProviderError):
    def __init__(self, msg: str, retry_after: float | None = None) -> None:
        super().__init__(msg)
        self.retry_after = retry_after


# --------------------------------------------------------------------------- #
# Circuit breaker
# --------------------------------------------------------------------------- #
@dataclass
class _Breaker:
    failures: int = 0
    opened_at: float = 0.0

    def is_open(self, reset_s: float) -> bool:
        if self.opened_at == 0.0:
            return False
        if time.monotonic() - self.opened_at >= reset_s:
            # half-open: allow one probe through and reset the counter
            self.opened_at = 0.0
            self.failures = 0
            return False
        return True


_BREAKERS: dict[str, _Breaker] = {}


def circuit_state(key: str) -> bool:
    s = ti_settings()
    b = _BREAKERS.get(key)
    return bool(b and b.is_open(s.ti_circuit_reset_s))


def record_failure(key: str) -> None:
    s = ti_settings()
    b = _BREAKERS.setdefault(key, _Breaker())
    b.failures += 1
    if b.failures >= s.ti_circuit_failure_threshold and b.opened_at == 0.0:
        b.opened_at = time.monotonic()


def record_success(key: str) -> None:
    _BREAKERS.pop(key, None)


def reset_circuits() -> None:
    """Test hook — the breaker is process-global by design."""
    _BREAKERS.clear()


# --------------------------------------------------------------------------- #
# TTL cache
# --------------------------------------------------------------------------- #
@dataclass
class _CacheEntry:
    value: Any
    expires_at: float
    stored_at: float = field(default_factory=time.time)


_CACHE: dict[str, _CacheEntry] = {}


def _cache_key(method: str, url: str, params: Any, body: Any) -> str:
    blob = json.dumps(
        {"m": method, "u": url, "p": params, "b": body},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def cache_get(key: str) -> Optional[Any]:
    e = _CACHE.get(key)
    if e is None:
        return None
    if e.expires_at < time.time():
        _CACHE.pop(key, None)
        return None
    return e.value


def cache_put(key: str, value: Any, ttl: float) -> None:
    _CACHE[key] = _CacheEntry(value=value, expires_at=time.time() + ttl)


def reset_cache() -> None:
    _CACHE.clear()


# --------------------------------------------------------------------------- #
# The one HTTP entrypoint
# --------------------------------------------------------------------------- #
async def request_json(
    method: str,
    url: str,
    *,
    breaker_key: str,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    auth: tuple[str, str] | None = None,
    timeout: float | None = None,
    retries: int | None = None,
    cache_ttl: float | None = None,
    client: httpx.AsyncClient | None = None,
    expect_json: bool = True,
) -> Any:
    """GET/POST returning parsed JSON (or raw text when expect_json=False).

    Raises ProviderError on definitive failure. Never raises anything else.
    """
    s = ti_settings()
    timeout = s.ti_provider_timeout_s if timeout is None else timeout
    retries = s.ti_http_retries if retries is None else retries
    ttl = s.ti_cache_ttl_s if cache_ttl is None else cache_ttl

    if circuit_state(breaker_key):
        raise CircuitOpen(f"circuit open for {breaker_key}")

    ck = _cache_key(method, url, params, json_body or data)
    if ttl > 0:
        hit = cache_get(ck)
        if hit is not None:
            return hit

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    last_err: Exception | None = None
    try:
        for attempt in range(max(1, retries)):
            try:
                resp = await client.request(
                    method, url, params=params, json=json_body, data=data,
                    headers=headers, auth=auth, timeout=timeout,
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    ra = resp.headers.get("retry-after")
                    retry_after = float(ra) if (ra or "").replace(".", "", 1).isdigit() else None
                    last_err = RateLimited(
                        f"{breaker_key}: HTTP {resp.status_code}", retry_after
                    )
                    await _sleep_backoff(attempt, s, retry_after)
                    continue
                if resp.status_code >= 400:
                    # 4xx (bad key, forbidden, quota) — retrying will not help.
                    record_failure(breaker_key)
                    raise ProviderError(
                        f"{breaker_key}: HTTP {resp.status_code} {resp.text[:200]}"
                    )
                out = resp.json() if expect_json else resp.text
                record_success(breaker_key)
                if ttl > 0:
                    cache_put(ck, out, ttl)
                return out
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = e
                await _sleep_backoff(attempt, s, None)
            except ProviderError:
                raise
            except json.JSONDecodeError as e:
                last_err = e
                break
        record_failure(breaker_key)
        raise ProviderError(f"{breaker_key}: {type(last_err).__name__}: {last_err}")
    finally:
        if owns_client:
            await client.aclose()


async def _sleep_backoff(attempt: int, s, retry_after: float | None) -> None:
    """Exponential backoff with FULL jitter (AWS-style) — avoids retry storms when
    several providers hit the same rate limit simultaneously."""
    if retry_after is not None:
        await asyncio.sleep(min(retry_after, s.ti_http_backoff_max_s))
        return
    ceiling = min(s.ti_http_backoff_max_s, s.ti_http_backoff_base_s * (2 ** attempt))
    await asyncio.sleep(random.uniform(0.0, ceiling))
