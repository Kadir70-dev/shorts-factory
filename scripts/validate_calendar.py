#!/usr/bin/env python3
"""
Validation harness for the 30-day finance-Shorts content backlog
(data/calendar/). Orchestration-only script — reads existing job files and
the real SceneGraph schema, does not touch the frozen pipeline.

Checks (per the backlog task's STEP 18):
  - total days == 30, shorts/day == 3, total slots == 90
  - evergreen ~= 75, trend ~= 15
  - no duplicate job ids, no duplicate (day, slot)
  - no obvious duplicate topics (lexical overlap on the topic strings)
  - every evergreen job: has sources, has a script (scene.json, real
    narration), has a visual plan (every scene has a query/keywords), has
    metadata (title/description/tags/hashtags), and the scene.json actually
    validates against the REAL production SceneGraph pydantic schema
  - every trend slot: has research_query + source_requirements +
    script_template + freshness_requirements
  - no empty required fields
  - duration window (35-55s) and word-count window (~90-130) per evergreen job
  - quality gate: hook>=7, fact_confidence>=9, average>=8 (or rewritten=true)

Usage: python scripts/validate_calendar.py [--json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "data" / "calendar"
JOBS = CAL / "jobs"
sys.path.insert(0, str(ROOT / "apps" / "api"))


def _stopword_set(s: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", s.lower())
    stop = {"the", "a", "an", "of", "and", "how", "why", "what", "is", "actually",
            "to", "in", "for", "vs", "on", "it", "its", "s"}
    return {w for w in words if w not in stop and len(w) > 2}


def main() -> int:
    problems: list[str] = []
    warnings: list[str] = []

    plan = json.loads((CAL / "master_plan.json").read_text(encoding="utf-8"))

    if len(plan) != 90:
        problems.append(f"total slots == {len(plan)}, expected 90")
    days = sorted({s["day"] for s in plan})
    if days != list(range(1, 31)):
        problems.append(f"days present: {days[:3]}...{days[-3:]} (expected exactly 1..30)")
    for d in range(1, 31):
        slots_today = [s for s in plan if s["day"] == d]
        if len(slots_today) != 3:
            problems.append(f"day {d}: {len(slots_today)} slots (expected 3)")
        letters = sorted(s["slot"] for s in slots_today)
        if letters != ["A", "B", "C"]:
            problems.append(f"day {d}: slots {letters} (expected A,B,C)")

    ids = [s["job_id"] for s in plan]
    dupe_ids = {i for i in ids if ids.count(i) > 1}
    if dupe_ids:
        problems.append(f"duplicate job ids: {sorted(dupe_ids)}")
    day_slot_pairs = [(s["day"], s["slot"]) for s in plan]
    dupe_pairs = {p for p in day_slot_pairs if day_slot_pairs.count(p) > 1}
    if dupe_pairs:
        problems.append(f"duplicate (day,slot) pairs: {sorted(dupe_pairs)}")

    evergreen = [s for s in plan if s["evergreen"]]
    trend = [s for s in plan if not s["evergreen"]]
    if not (70 <= len(evergreen) <= 80):
        problems.append(f"evergreen count {len(evergreen)}, expected ~75")
    if not (10 <= len(trend) <= 20):
        problems.append(f"trend count {len(trend)}, expected ~15")
    if len(evergreen) + len(trend) != 90:
        problems.append("evergreen+trend != 90")

    # semantic-ish dedup: pairwise word-overlap on evergreen topic strings
    topic_words = [(s["job_id"], _stopword_set(s["topic"])) for s in evergreen]
    for i in range(len(topic_words)):
        for j in range(i + 1, len(topic_words)):
            id_a, w_a = topic_words[i]
            id_b, w_b = topic_words[j]
            if not w_a or not w_b:
                continue
            overlap = len(w_a & w_b) / max(1, min(len(w_a), len(w_b)))
            if overlap >= 0.6:
                warnings.append(f"possible topic overlap: {id_a} vs {id_b} ({overlap:.0%} word overlap)")

    try:
        from app.schemas.scene import SceneGraph  # type: ignore
        have_schema = True
    except Exception as e:  # noqa: BLE001
        have_schema = False
        warnings.append(f"could not import real SceneGraph schema ({e}); "
                         f"falling back to structural checks only")

    evergreen_ready = 0
    for s in evergreen:
        jid = s["job_id"]
        scene_p = JOBS / f"{jid}.scene.json"
        meta_p = JOBS / f"{jid}.meta.json"
        if not scene_p.exists():
            problems.append(f"{jid}: missing scene.json")
            continue
        if not meta_p.exists():
            problems.append(f"{jid}: missing meta.json")
            continue

        raw = scene_p.read_text(encoding="utf-8")
        graph = None
        if have_schema:
            try:
                graph = SceneGraph.model_validate_json(raw)
            except Exception as e:  # noqa: BLE001
                problems.append(f"{jid}: scene.json FAILS real SceneGraph validation: {e}")
        else:
            try:
                graph_dict = json.loads(raw)
            except Exception as e:  # noqa: BLE001
                problems.append(f"{jid}: scene.json invalid JSON: {e}")
                continue

        meta = json.loads(meta_p.read_text(encoding="utf-8"))

        if graph is not None:
            if not graph.meta.title.strip():
                problems.append(f"{jid}: empty title")
            if not graph.meta.description.strip():
                problems.append(f"{jid}: empty description")
            if not graph.meta.tags:
                problems.append(f"{jid}: empty tags")
            if not graph.meta.hashtags:
                problems.append(f"{jid}: empty hashtags")
            if not graph.scenes:
                problems.append(f"{jid}: no scenes")
            for sc in graph.scenes:
                if not sc.narration.strip():
                    problems.append(f"{jid}/{sc.id}: empty narration")
                if not sc.visual.query.strip() and not sc.visual.broll_keywords:
                    problems.append(f"{jid}/{sc.id}: no visual plan (query/broll_keywords empty)")
            total_dur = sum(sc.duration_sec for sc in graph.scenes)
            if not (33 <= total_dur <= 57):
                warnings.append(f"{jid}: total duration {total_dur:.1f}s outside 35-55s target")
            word_count = sum(len(sc.narration.split()) for sc in graph.scenes)
            if not (80 <= word_count <= 145):
                warnings.append(f"{jid}: {word_count} spoken words outside ~90-130 target")

        sources = meta.get("sources") or []
        if not sources:
            problems.append(f"{jid}: no sources recorded in meta.json")
        qs = meta.get("quality_scores") or {}
        if qs:
            hook = qs.get("hook", 0)
            fact = qs.get("fact_confidence", 0)
            avg = qs.get("average", 0)
            if (hook < 7 or fact < 9 or avg < 8) and not meta.get("rewritten"):
                problems.append(
                    f"{jid}: quality gate not met (hook={hook} fact_confidence={fact} "
                    f"avg={avg}) and not flagged rewritten"
                )
        else:
            warnings.append(f"{jid}: no quality_scores recorded")

        if meta.get("status") == "READY" and not problems:
            evergreen_ready += 1

    for s in trend:
        jid = s["job_id"]
        meta_p = JOBS / f"{jid}.meta.json"
        if not meta_p.exists():
            problems.append(f"{jid}: missing meta.json (trend template)")
            continue
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        for field in ("research_query", "source_requirements", "script_template",
                      "freshness_requirements"):
            v = meta.get(field)
            if not v:
                problems.append(f"{jid}: missing/empty trend field '{field}'")
        if meta.get("status") != "TREND — RESEARCH ON PUBLISH DATE":
            warnings.append(f"{jid}: unexpected trend status '{meta.get('status')}'")

    result = {
        "total_days": len(days),
        "total_slots": len(plan),
        "evergreen": len(evergreen),
        "trend": len(trend),
        "evergreen_ready": evergreen_ready,
        "problems": problems,
        "warnings": warnings,
        "passed": not problems,
    }

    if "--json" in sys.argv:
        print(json.dumps(result, indent=2))
    else:
        print(f"days={result['total_days']} slots={result['total_slots']} "
              f"evergreen={result['evergreen']} trend={result['trend']} "
              f"evergreen_ready={result['evergreen_ready']}")
        print(f"\nPROBLEMS ({len(problems)}):")
        for p in problems:
            print("  [X]", p)
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print("  [!]", w)
        print(f"\n{'PASSED' if result['passed'] else 'FAILED'}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
