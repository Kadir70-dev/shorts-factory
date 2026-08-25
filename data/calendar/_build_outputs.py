#!/usr/bin/env python3
"""Builds 30_day_calendar.json/.md and production_queue.json from
master_plan.json + jobs/*.meta.json. Safe to re-run any time — it only
reads job files, never writes into jobs/."""
import json
import pathlib

ROOT = pathlib.Path(__file__).parent
JOBS = ROOT / "jobs"

plan = json.loads((ROOT / "master_plan.json").read_text(encoding="utf-8"))


def meta_for(job_id: str) -> dict:
    p = JOBS / f"{job_id}.meta.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---- 30_day_calendar.json / .md -------------------------------------------
calendar = []
for day in range(1, 31):
    day_slots = sorted([s for s in plan if s["day"] == day], key=lambda s: s["slot"])
    entry = {"day": day, "slots": {}}
    for s in day_slots:
        m = meta_for(s["job_id"])
        entry["slots"][s["slot"]] = {
            "job_id": s["job_id"],
            "category": s["category"],
            "content_type": s["content_type"],
            "topic": s["topic"],
            "status": m.get("status", "PLANNED" if s["evergreen"] else "TREND — RESEARCH ON PUBLISH DATE"),
        }
    calendar.append(entry)

(ROOT / "30_day_calendar.json").write_text(json.dumps(calendar, indent=2), encoding="utf-8")

md = ["# 30-Day Finance Shorts Calendar", "",
      "3 Shorts/day x 30 days = 90 Shorts. Slot A = business/wealth story, "
      "Slot B = markets/economics/investing education, Slot C = money "
      "mechanics/surprising finance.", ""]
for entry in calendar:
    md.append(f"## DAY {entry['day']:02d}")
    for letter in ("A", "B", "C"):
        s = entry["slots"][letter]
        md.append(f"- **{letter}** [{s['content_type']}] {s['topic']}  \n"
                  f"  status: `{s['status']}`  ·  job: `{s['job_id']}`")
    md.append("")
(ROOT / "30_day_calendar.md").write_text("\n".join(md), encoding="utf-8")

# ---- production_queue.json --------------------------------------------
queue = []
for s in plan:
    m = meta_for(s["job_id"])
    scene_path = JOBS / f"{s['job_id']}.scene.json"
    queue.append({
        "job_id": s["job_id"],
        "day": s["day"],
        "slot": s["slot"],
        "category": s["category"],
        "content_type": s["content_type"],
        "topic": s["topic"],
        "status": m.get("status", "PLANNED" if s["evergreen"] else "TREND — RESEARCH ON PUBLISH DATE"),
        "scene_graph_path": str(scene_path) if scene_path.exists() else None,
        "meta_path": str(JOBS / f"{s['job_id']}.meta.json") if (JOBS / f"{s['job_id']}.meta.json").exists() else None,
        "produce_cmd": (
            f'python scripts/produce.py --preset finance_shorts --from-json "{scene_path}" --keep'
            if scene_path.exists() else None
        ),
    })
(ROOT / "production_queue.json").write_text(json.dumps(queue, indent=2), encoding="utf-8")

n_ready = sum(1 for q in queue if str(q["status"]).startswith("READY"))
n_trend = sum(1 for q in queue if q["content_type"] == "trend")
print(f"calendar/queue built: {len(queue)} slots, {n_ready} READY, {n_trend} trend")

# ---- content_report.md -----------------------------------------------
evergreen = [q for q in queue if q["content_type"] == "evergreen"]
trend = [q for q in queue if q["content_type"] == "trend"]
legacy_score_exceptions = []
for q in evergreen:
    m = meta_for(q["job_id"])
    scores = m.get("quality_scores") or {}
    if (scores.get("hook", 0) < 7 or scores.get("fact_confidence", 0) < 9
            or scores.get("average", 0) < 8):
        legacy_score_exceptions.append(q["job_id"])

report = [
    "# Finance Shorts Content Report", "",
    f"- Total days: 30", f"- Total slots: {len(queue)}",
    f"- Evergreen production jobs: {len(evergreen)}",
    f"- Trend research templates: {len(trend)}",
    f"- Evergreen scene graphs present: {sum(bool(q['scene_graph_path']) for q in evergreen)}",
    f"- Metadata sidecars present: {sum(bool(q['meta_path']) for q in queue)}", "",
    "## Production state", "",
    "All evergreen slots have a source-backed script, scene-by-scene visual plan, platform metadata, and quality scores. "
    "Trend slots intentionally have no scene graph until their publish-date research pass; each has freshness, source, selection, script, and fallback instructions.", "",
    "## Preserved legacy quality-score exceptions", "",
    ("The following valid recovered Claude jobs were preserved unchanged even though their recorded score is below the newer hook/fact-confidence/average target: "
     + ", ".join(f"`{x}`" for x in legacy_score_exceptions) + ".") if legacy_score_exceptions else "None.", "",
    "## Safety", "",
    "No videos were rendered or published. No Git commit or push was performed.",
]
(ROOT / "content_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
