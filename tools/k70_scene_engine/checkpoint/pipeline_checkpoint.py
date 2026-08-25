"""Stage checkpointing for long-form productions (brief section 16).

Mirrors the existing pipeline's own checkpoint convention
(`data/jobs/<video_id>/*.checkpoint`, as used by `scripts/produce.py`) so a
K70-scene-engine-augmented job resumes the same way an ordinary job
already does -- one checkpoint file per stage, written only on success,
read back before re-running a stage.

    ckpt = PipelineCheckpoint(job_dir)
    if not ckpt.done("3d_scenes"):
        result = build_3d_scenes(...)
        ckpt.mark_done("3d_scenes", {"scene_count": len(result)})
    # on a re-run after a crash, ckpt.done("3d_scenes") is now True and
    # build_3d_scenes(...) is skipped entirely.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STAGES = [
    "research", "script", "voice", "storyboard", "asset_resolution",
    "3d_scenes", "stock_assets", "motion_graphics", "timeline", "render", "qa",
]


class PipelineCheckpoint:
    def __init__(self, job_dir: Path):
        self.job_dir = Path(job_dir)
        self.job_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, stage: str) -> Path:
        if stage not in STAGES:
            raise ValueError(f"unknown stage '{stage}'; known: {STAGES}")
        return self.job_dir / f"{stage}.checkpoint"

    def done(self, stage: str) -> bool:
        return self._path(stage).exists()

    def mark_done(self, stage: str, payload: dict | None = None) -> None:
        data = {"stage": stage, "completed_at": datetime.now(timezone.utc).isoformat(),
                **(payload or {})}
        self._path(stage).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def read(self, stage: str) -> dict | None:
        p = self._path(stage)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def reset(self, stage: str) -> None:
        """Force one stage (and only that stage) to re-run on next resume."""
        self._path(stage).unlink(missing_ok=True)

    def status(self) -> dict[str, bool]:
        return {s: self.done(s) for s in STAGES}

    def next_stage(self) -> str | None:
        for s in STAGES:
            if not self.done(s):
                return s
        return None
