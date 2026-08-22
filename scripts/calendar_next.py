#!/usr/bin/env python3
"""
CALENDAR -> PRODUCTION QUEUE (orchestration-only glue, sits on top of the
frozen v1-production pipeline per PRODUCTION.md — no pipeline/schema code
touched).

Resolves "today's 3 jobs" from the 30-day finance-Shorts backlog
(`data/calendar/master_plan.json` + `data/calendar/jobs/*.meta.json`) and
prints the exact `scripts/produce.py` command for each slot. Evergreen slots
point straight at a pre-authored SceneGraph (--from-json, deterministic,
no live Director call needed). Trend slots are flagged for a research pass
first — this script deliberately does NOT fabricate or auto-render a trend
story; that is a separate, explicit step (see docs note below).

Usage:
    python scripts/calendar_next.py                  # today = day 1 of the cycle
    python scripts/calendar_next.py --day 7           # a specific day
    python scripts/calendar_next.py --start 2026-08-17 --day-for 2026-08-23
    python scripts/calendar_next.py --json             # machine-readable

The cycle's start date is stored in `data/calendar/cycle_start.json` the
first time this is run (or pass --start once to set it explicitly).
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "data" / "calendar"
JOBS = CAL / "jobs"
START_FILE = CAL / "cycle_start.json"


def _load_plan() -> list[dict]:
    return json.loads((CAL / "master_plan.json").read_text(encoding="utf-8"))


def _get_or_set_start(explicit: str | None) -> date:
    if explicit:
        d = datetime.strptime(explicit, "%Y-%m-%d").date()
        START_FILE.write_text(json.dumps({"start": d.isoformat()}), encoding="utf-8")
        return d
    if START_FILE.exists():
        return datetime.strptime(
            json.loads(START_FILE.read_text())["start"], "%Y-%m-%d"
        ).date()
    d = date.today()
    START_FILE.write_text(json.dumps({"start": d.isoformat()}), encoding="utf-8")
    return d


def resolve_day(day: int) -> list[dict]:
    plan = _load_plan()
    todays = [s for s in plan if s["day"] == day]
    if len(todays) != 3:
        raise SystemExit(f"expected 3 slots for day {day}, found {len(todays)}")
    out = []
    for slot in sorted(todays, key=lambda s: s["slot"]):
        job_id = slot["job_id"]
        meta_path = JOBS / f"{job_id}.meta.json"
        scene_path = JOBS / f"{job_id}.scene.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        entry = {
            "job_id": job_id,
            "day": day,
            "slot": slot["slot"],
            "category": slot["category"],
            "content_type": slot["content_type"],
            "topic": slot["topic"],
            "status": meta.get("status", "MISSING"),
            "scene_graph_path": str(scene_path) if scene_path.exists() else None,
            "meta_path": str(meta_path) if meta_path.exists() else None,
        }
        if slot["content_type"] == "evergreen":
            entry["produce_cmd"] = (
                f'python scripts/produce.py --preset finance_shorts '
                f'--from-json "{scene_path}" --keep'
                if scene_path.exists() else None
            )
            entry["action"] = "RENDER" if scene_path.exists() else "BLOCKED — scene.json missing"
        else:
            entry["produce_cmd"] = None
            entry["action"] = (
                "RESEARCH FIRST — run the topic-intelligence / research pass "
                "using this slot's research_query + source_requirements in "
                f"{meta_path.name}, write a real scene.json once a fresh, "
                "sourced story clears the freshness/source bar, THEN render. "
                "If nothing clears the bar, fall back to an unused evergreen "
                "topic in the same category — never force a weak story."
            )
        out.append(entry)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", type=int, help="explicit day-of-cycle (1-30)")
    ap.add_argument("--start", help="set/reset the cycle start date, YYYY-MM-DD")
    ap.add_argument("--day-for", help="resolve the day-of-cycle for this calendar date, YYYY-MM-DD")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    start = _get_or_set_start(args.start)
    if args.day:
        day = args.day
    else:
        ref = datetime.strptime(args.day_for, "%Y-%m-%d").date() if args.day_for else date.today()
        day = ((ref - start).days % 30) + 1

    jobs = resolve_day(day)

    if args.json:
        print(json.dumps({"day": day, "cycle_start": start.isoformat(), "jobs": jobs}, indent=2))
        return 0

    print(f"=== Day {day} of 30 — cycle start {start.isoformat()} ===")
    for j in jobs:
        print(f"\nSlot {j['slot']} [{j['content_type'].upper()}] — {j['topic']}")
        print(f"  status: {j['status']}")
        print(f"  action: {j['action']}")
        if j["produce_cmd"]:
            print(f"  cmd   : {j['produce_cmd']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
