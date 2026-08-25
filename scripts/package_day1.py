"""Assemble the reviewed Day 1 Shorts into upload-ready delivery folders."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "outputs" / "day_01"


for job_id in ("d01_a", "d01_b", "d01_c"):
    source = ROOT / "data" / "jobs" / f"vid_fin_{job_id}"
    target = OUTPUT / job_id
    target.mkdir(parents=True, exist_ok=True)

    for name in (
        "final.mp4",
        "thumbnail.jpg",
        "metadata.json",
        "captions.srt",
        "qa_report.json",
        "qa_report.txt",
        "provenance.json",
        "visual_breakdown.json",
    ):
        shutil.copy2(source / name, target / name)

    meta_path = ROOT / "data" / "calendar" / "jobs" / f"{job_id}.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    sources_package = {
        "id": job_id,
        "topic": meta.get("topic"),
        "content_type": meta.get("content_type"),
        "sources": meta.get("sources", []),
        "pronunciation_notes": meta.get("pronunciation_notes", []),
        "disclaimer": meta.get("disclaimer", ""),
    }
    (target / "sources.json").write_text(
        json.dumps(sources_package, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

print(OUTPUT)
