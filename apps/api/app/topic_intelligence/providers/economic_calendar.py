"""
Economic-calendar connector — a vendor ABSTRACTION, not a hardcoded provider.

Three adapters ship: `tradingeconomics`, `finnhub`, and `generic_json` (any
endpoint returning a list of events in the documented shape). Pick one with
ECONOMIC_CALENDAR_PROVIDER; add another by writing a ~20-line `_parse_*`.

Critical rule: previous / forecast / actual values are passed through EXACTLY as
the vendor published them and stay `None` when absent. Gemini is never asked to
fill in a missing macro number — a fabricated CPI print is a catastrophic error,
not a rounding issue.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..http import ProviderError, request_json
from ..models import AssetClass, EconomicEvent, EventStatus, RawTrendSignal
from .base import BaseProvider

# The US events this channel cares about, and what they move.
US_EVENT_ASSETS: dict[str, list[AssetClass]] = {
    "fomc": [AssetClass.rates, AssetClass.equities, AssetClass.macro],
    "fed interest rate": [AssetClass.rates, AssetClass.equities, AssetClass.macro],
    "interest rate decision": [AssetClass.rates, AssetClass.equities],
    "cpi": [AssetClass.macro, AssetClass.rates, AssetClass.equities],
    "inflation rate": [AssetClass.macro, AssetClass.rates],
    "pce": [AssetClass.macro, AssetClass.rates],
    "non farm payrolls": [AssetClass.macro, AssetClass.equities],
    "nonfarm payrolls": [AssetClass.macro, AssetClass.equities],
    "unemployment rate": [AssetClass.macro],
    "gdp": [AssetClass.macro, AssetClass.equities],
    "retail sales": [AssetClass.macro, AssetClass.equities],
    "ism": [AssetClass.macro],
    "initial jobless claims": [AssetClass.macro],
    "treasury": [AssetClass.rates],
    "crude oil inventories": [AssetClass.oil],
}
US_KEYWORDS = tuple(US_EVENT_ASSETS)


def _parse_dt(v) -> datetime | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(float(v), tz=timezone.utc)
    txt = str(v).strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.fromisoformat(txt) if fmt is None else datetime.strptime(txt, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _str_or_none(v) -> str | None:
    """Empty string, None, and '-' all mean NOT PUBLISHED. Never coerce to 0."""
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s not in {"-", "--", "n/a", "N/A"} else None


def _affected(name: str) -> list[AssetClass]:
    low = name.lower()
    for key, assets in US_EVENT_ASSETS.items():
        if key in low:
            return list(assets)
    return [AssetClass.macro]


def _importance(raw) -> str:
    if isinstance(raw, (int, float)):
        return {3: "high", 2: "medium", 1: "low"}.get(int(raw), "medium")
    s = str(raw or "").strip().lower()
    if s in {"high", "3"}:
        return "high"
    if s in {"low", "1"}:
        return "low"
    return "medium"


class EconomicCalendarProvider(BaseProvider):
    name = "economic_calendar"

    @property
    def enabled(self) -> bool:
        return self.settings.economic_calendar_enabled

    @property
    def configured(self) -> bool:
        return bool(self.settings.economic_calendar_provider.strip())

    # ------------------------------------------------------------------ fetch
    async def _fetch(self, since: datetime) -> list[dict]:
        s = self.settings
        vendor = s.economic_calendar_provider.strip().lower()
        key = s.economic_calendar_api_key.strip()
        base = s.economic_calendar_base_url.strip()
        start = since.date().isoformat()
        end = (since + timedelta(days=10)).date().isoformat()

        if vendor == "tradingeconomics":
            url = base or "https://api.tradingeconomics.com/calendar/country/united states"
            data = await request_json(
                "GET", url, breaker_key=self.name,
                params={"c": key or "guest:guest", "d1": start, "d2": end, "f": "json"},
            )
            return data if isinstance(data, list) else []

        if vendor == "finnhub":
            url = base or "https://finnhub.io/api/v1/calendar/economic"
            data = await request_json(
                "GET", url, breaker_key=self.name,
                params={"token": key, "from": start, "to": end},
            )
            return (data or {}).get("economicCalendar", []) if isinstance(data, dict) else []

        if vendor == "generic_json":
            if not base:
                raise ProviderError(
                    "economic_calendar: ECONOMIC_CALENDAR_PROVIDER=generic_json "
                    "requires ECONOMIC_CALENDAR_BASE_URL"
                )
            data = await request_json(
                "GET", base, breaker_key=self.name,
                headers={"Authorization": f"Bearer {key}"} if key else None,
                params={"country": "US", "from": start, "to": end},
            )
            if isinstance(data, dict):
                data = data.get("events") or data.get("items") or []
            return data if isinstance(data, list) else []

        raise ProviderError(
            f"economic_calendar: unknown provider {vendor!r} "
            "(expected tradingeconomics | finnhub | generic_json)"
        )

    # ------------------------------------------------------------------ parse
    def _to_event(self, row: dict) -> EconomicEvent | None:
        vendor = self.settings.economic_calendar_provider.strip().lower()
        country = str(
            row.get("Country") or row.get("country") or row.get("region") or ""
        ).lower()
        if country and country not in {"united states", "us", "usa"}:
            return None

        name = str(
            row.get("Event") or row.get("event") or row.get("name") or ""
        ).strip()
        if not name or not any(k in name.lower() for k in US_KEYWORDS):
            return None

        scheduled = _parse_dt(
            row.get("Date") or row.get("date") or row.get("time")
            or row.get("scheduled_at")
        )
        if scheduled is None:
            return None

        actual = _str_or_none(row.get("Actual", row.get("actual")))
        revised = _str_or_none(row.get("Revised", row.get("revised")))
        status = EventStatus.scheduled
        if revised:
            status = EventStatus.revised
        elif actual:
            status = EventStatus.released
        if str(row.get("status", "")).lower() == "cancelled":
            status = EventStatus.cancelled

        return EconomicEvent(
            name=name,
            scheduled_at=scheduled,
            importance=_importance(row.get("Importance", row.get("impact"))),
            affected_assets=_affected(name),
            previous_value=_str_or_none(row.get("Previous", row.get("prev"))),
            forecast_value=_str_or_none(
                row.get("Forecast", row.get("estimate", row.get("TEForecast")))
            ),
            actual_value=actual,
            source=vendor,
            source_url=row.get("SourceURL") or row.get("source_url") or row.get("url"),
            status=status,
        )

    # ---------------------------------------------------------------- collect
    async def collect(
        self, *, niche: str, region: str, since: datetime, limit: int
    ) -> list[RawTrendSignal]:
        rows = await self._fetch(since)
        now = datetime.now(timezone.utc)
        out: list[RawTrendSignal] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            ev = self._to_event(row)
            if ev is None:
                continue

            # Title carries the factual state explicitly so the normalizer classifies
            # a released print as CONFIRMED and an upcoming one as FORECAST.
            if ev.status is EventStatus.released and ev.actual_value:
                title = f"{ev.name} released: actual {ev.actual_value}"
                if ev.forecast_value:
                    title += f" vs forecast {ev.forecast_value}"
            elif ev.status is EventStatus.revised:
                title = f"{ev.name} revised"
            elif ev.status is EventStatus.cancelled:
                title = f"{ev.name} cancelled"
            else:
                title = f"{ev.name} scheduled — forecast {ev.forecast_value or 'not published'}"

            out.append(RawTrendSignal(
                provider=self.name,
                external_id=f"{ev.source}:{ev.name}:{ev.scheduled_at.isoformat()}",
                title=title,
                summary=(
                    f"US economic event. Importance: {ev.importance}. "
                    f"Previous: {ev.previous_value or 'not published'}. "
                    f"Forecast: {ev.forecast_value or 'not published'}. "
                    f"Actual: {ev.actual_value or 'not released'}."
                ),
                url=ev.source_url,
                published_at=ev.scheduled_at,
                collected_at=now,
                region="US",
                engagement={},
                raw_metrics={
                    "event_name": ev.name,
                    "importance": ev.importance,
                    "status": ev.status.value,
                    "previous_value": ev.previous_value,
                    "forecast_value": ev.forecast_value,
                    "actual_value": ev.actual_value,
                    "affected_assets": [a.value for a in ev.affected_assets],
                    "scheduled_at": ev.scheduled_at.isoformat(),
                    "source": ev.source,
                },
                author_or_channel=ev.source,
                # Official calendars are primary-grade schedules.
                source_credibility=0.95,
            ))
            if len(out) >= limit:
                break
        return out
