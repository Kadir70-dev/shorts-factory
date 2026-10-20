"""Optional pre-render adapter. Frozen K70 architecture and production unchanged.

Call after TTS + visual asset selection and before existing render_ffmpeg.render.
Only manually selected illustrative slots change, no financial evidence replaced.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .engine import EngineError, FinanceShot, render_clip

_ELIGIBLE_TYPES = {"broll", "ai_image", "image", "solid", "branded"}
_PROTECTED_CHANNELS = {"charts", "official", "motion_gfx", "threejs"}


def attach_finance_clips(graph, scene_specs: dict[str, Path], target_dir: Path,
                         *, cache_dir: Path | None = None):
    """Return deep-copied SceneGraph with chosen illustrated clips, preserving original."""
    if not scene_specs:
        return graph
    by_id = {scene.id: scene for scene in graph.scenes}
    missing = set(scene_specs) - set(by_id)
    if missing:
        raise EngineError(f"Unknown SceneGraph scene IDs: {sorted(missing)}")
    for sid, spec in scene_specs.items():
        scene = by_id[sid]
        visual = scene.visual
        if (visual.type not in _ELIGIBLE_TYPES or
            getattr(visual, "budget_channel", None) in _PROTECTED_CHANNELS or
            getattr(visual, "evidence_card_path", None)):
            raise EngineError(f"Scene {sid} has protected visual; refusing cinematic replacement")
        data = getattr(scene, "data", None)
        if data is not None and callable(getattr(data, "valid", None)) and data.valid():
            raise EngineError(f"Scene {sid} has verified data chart; refusing replacement")
        shot = FinanceShot(json.loads(Path(spec).read_text()),
                           Path(spec).resolve().parent)
        # Render_ffmpeg fits clips to final delivery dimensions; 640x360 CPU
        # source is valid for a 1920x1080 documentary (same 16:9 aspect).
        if abs(shot.w / shot.h - graph.width / graph.height) > 0.005:
            raise EngineError(f"Scene {sid} aspect mismatch: shot {shot.w}x{shot.h}, video {graph.width}x{graph.height}")
    directory = Path(target_dir)
    rendered = {}
    # Complete clip generation before mutating/copying caller's graph.
    for sid, spec in scene_specs.items():
        duration = float(by_id[sid].duration_sec)
        shot = FinanceShot(json.loads(Path(spec).read_text()),
                           Path(spec).resolve().parent)
        if abs(shot.duration - duration) > max(0.05, 1 / shot.fps):
            raise EngineError(f"Scene {sid} duration mismatch: clip {shot.duration}s, scene {duration}s")
        name = hashlib.sha256(sid.encode()).hexdigest()[:12]
        target = directory / f"finance_cinematic_{name}.mp4"
        render_clip(spec, target, cache_dir=cache_dir)
        rendered[sid] = target.resolve()
    result = graph.model_copy(deep=True)
    for scene in result.scenes:
        if scene.id in rendered:
            scene.visual.asset_path = str(rendered[scene.id])
            scene.visual.type = "ai_video"
            scene.visual.motion = "none"
            scene.visual.layers = []
    return result
