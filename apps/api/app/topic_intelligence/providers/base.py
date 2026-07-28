"""
The unified provider contract.

Every connector is OPTIONAL and independently configurable. `BaseProvider.run()`
is the only entrypoint the service uses; it wraps `collect()` in a timeout, catches
every exception, and always returns a (signals, status) pair — so one dead provider
can never take down a run.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from ..http import ProviderError, circuit_state
from ..models import ProviderStatus, RawTrendSignal
from ..settings import TopicIntelligenceSettings, ti_settings

# The finance/trading beat this channel covers. Providers turn these into their own
# native query shapes; they are deliberately US-centric and event-oriented.
FINANCE_QUERIES: tuple[str, ...] = (
    "stock market today",
    "federal reserve interest rates",
    "CPI inflation report",
    "bitcoin price",
    "nvidia earnings AI",
    "gold price forecast",
    "oil prices WTI",
    "dollar forex markets",
    "high frequency trading explained",
    "quant trading strategies",
    "market microstructure order flow",
    "AI in finance trading",
    "nonfarm payrolls jobs report",
    "treasury yields bonds",
)


@runtime_checkable
class TrendProvider(Protocol):
    """Structural contract — anything with this shape is a provider."""

    name: str

    async def collect(
        self,
        *,
        niche: str,
        region: str,
        since: datetime,
        limit: int,
    ) -> list[RawTrendSignal]:
        ...


class BaseProvider:
    """Shared plumbing: enablement, timeout, circuit state, status reporting."""

    name: str = "base"

    def __init__(self, settings: TopicIntelligenceSettings | None = None) -> None:
        self.settings = settings or ti_settings()

    # --- subclasses override these two ---
    @property
    def enabled(self) -> bool:
        """Feature flag only (ignores credentials)."""
        return False

    @property
    def configured(self) -> bool:
        """Credentials/endpoints present."""
        return False

    async def collect(
        self, *, niche: str, region: str, since: datetime, limit: int
    ) -> list[RawTrendSignal]:
        raise NotImplementedError

    # --- shared ---
    @property
    def usable(self) -> bool:
        return self.enabled and self.configured

    def _status(self, **kw) -> ProviderStatus:
        return ProviderStatus(
            name=self.name, enabled=self.enabled, configured=self.configured, **kw
        )

    async def run(
        self, *, niche: str, region: str, since: datetime, limit: int
    ) -> tuple[list[RawTrendSignal], ProviderStatus]:
        """Never raises. Partial success is success."""
        if not self.enabled:
            return [], self._status(
                ok=False, skipped_reason="disabled by feature flag"
            )
        if not self.configured:
            return [], self._status(
                ok=False,
                skipped_reason="missing credentials or endpoint configuration",
            )
        if circuit_state(self.name):
            return [], self._status(
                ok=False, circuit_open=True,
                skipped_reason="circuit breaker open after repeated failures",
            )

        t0 = time.perf_counter()
        try:
            signals = await asyncio.wait_for(
                self.collect(niche=niche, region=region, since=since, limit=limit),
                timeout=self.settings.ti_provider_timeout_s * 2,
            )
        except asyncio.TimeoutError:
            return [], self._status(
                ok=False, latency_ms=(time.perf_counter() - t0) * 1000,
                error=f"timeout after {self.settings.ti_provider_timeout_s * 2:.0f}s",
            )
        except ProviderError as e:
            return [], self._status(
                ok=False, latency_ms=(time.perf_counter() - t0) * 1000, error=str(e),
                circuit_open=circuit_state(self.name),
            )
        except Exception as e:  # noqa: BLE001 — a provider bug must not kill the run
            return [], self._status(
                ok=False, latency_ms=(time.perf_counter() - t0) * 1000,
                error=f"{type(e).__name__}: {e}",
            )

        latency = (time.perf_counter() - t0) * 1000
        stale = self._is_stale(signals)
        return signals, self._status(
            ok=True, signal_count=len(signals), latency_ms=round(latency, 2),
            stale=stale,
            error="stale data: newest signal older than the staleness window"
            if stale else None,
        )

    def _is_stale(self, signals: list[RawTrendSignal]) -> bool:
        """A provider that only returns old material is degraded, not healthy."""
        dated = [s.published_at for s in signals if s.published_at]
        if not dated:
            return False
        newest = max(d if d.tzinfo else d.replace(tzinfo=timezone.utc) for d in dated)
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=self.settings.ti_stale_after_hours
        )
        return newest < cutoff
