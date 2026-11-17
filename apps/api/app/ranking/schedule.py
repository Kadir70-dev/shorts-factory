"""
DST-aware publishing slots. Slots are US-Eastern WALL-CLOCK times, resolved
through zoneinfo so 4:00 PM stays 4:00 PM across the March/November switches,
then expressed in UTC (RFC 3339) for the YouTube `publishAt` field.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def _slot_times(slots: list[str]) -> list[time]:
    out = []
    for s in slots:
        hh, mm = s.split(":")
        out.append(time(int(hh), int(mm)))
    return sorted(out)


def slots_for_day(day: date, cfg: dict) -> list[datetime]:
    tz = ZoneInfo(cfg["schedule"].get("timezone", "America/New_York"))
    return [datetime.combine(day, t, tzinfo=tz) for t in _slot_times(cfg["schedule"]["slots"])]


def next_slots(cfg: dict, taken: set[str], count: int = 1,
               now: datetime | None = None, lead_minutes: int = 30) -> list[datetime]:
    """Next `count` free slots at least `lead_minutes` ahead. `taken` holds UTC
    ISO strings already booked in this channel's upload history."""
    tz = ZoneInfo(cfg["schedule"].get("timezone", "America/New_York"))
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    earliest = now + timedelta(minutes=lead_minutes)
    found: list[datetime] = []
    day = earliest.date()
    while len(found) < count and day <= earliest.date() + timedelta(days=60):
        for slot in slots_for_day(day, cfg):
            if slot >= earliest and to_rfc3339(slot) not in taken:
                found.append(slot)
                if len(found) == count:
                    break
        day += timedelta(days=1)
    return found


def to_rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def quota_day(now: datetime | None = None) -> str:
    """YouTube Data API quota resets at midnight Pacific."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
