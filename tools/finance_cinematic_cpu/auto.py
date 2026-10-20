"""F2: conservative automatic selection of *existing* AI-generated stills.

Does not call a generative model, edit the K70 pipeline, or fabricate evidence.
Never changes a graph without explicitly calling auto_apply().
"""
from __future__ import annotations
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from PIL import Image
from .engine import EngineError, MAX_SOURCE_PIXELS
from .bridge import attach_finance_clips

SAFE_CHANNELS = {'', 'ai_broll'}
STILL_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
UNSAFE_TERMS = ('archival footage', 'leaked video', 'actual footage', 'security camera',
                'official document', 'sec filing', 'historical photograph')


@dataclass(frozen=True)
class Pick:
    scene_id: str
    index: int
    start_sec: float
    duration_sec: float
    source: str
    score: int
    reason: str


def select_scenes(graph: Any, *, max_clips: int = 8, spacing_sec: float = 25.0,
                  min_dur: float = 2.0, max_dur: float = 12.0) -> dict:
    """Return audit report with accepted/rejected scenes; no filesystem mutations."""
    if not 1 <= max_clips <= 20 or not 0 <= spacing_sec <= 600:
        raise EngineError('Invalid max_clips or spacing_sec')
    if not (0.2 <= min_dur <= max_dur <= 20):
        raise EngineError('Invalid clip duration window')
    if getattr(graph, 'width', 0) <= 0 or getattr(graph, 'height', 0) <= 0:
        raise EngineError('Graph has invalid canvas')
    choices, rejected, t = [], [], 0.0
    for index, scene in enumerate(graph.scenes):
        duration = float(scene.duration_sec)
        start = t
        t += duration
        v = scene.visual
        reason = None
        if v.type != 'ai_image':
            reason = 'not_an_AI_still'
        elif getattr(v, 'budget_channel', '') not in SAFE_CHANNELS:
            reason = 'not_an_AI_broll_channel'
        elif getattr(v, 'evidence_card_path', None) or getattr(v, 'layers', []):
            reason = 'protected_evidence_or_layered_scene'
        elif scene.data is not None and scene.data.valid():
            reason = 'protected_financial_data'
        elif any(getattr(o, 'type', None) in ('stat', 'source') for o in scene.overlays):
            reason = 'number_or_evidence_overlay'
        elif any(term in (scene.narration + ' ' + (getattr(v, 'visual_intent', '') or '')).lower()
                 for term in UNSAFE_TERMS):
            reason = 'requires_authentic_footage'
        elif not min_dur <= duration <= max_dur:
            reason = 'duration_outside_window'
        else:
            src = Path(v.asset_path) if v.asset_path else None
            if src is None or src.suffix.lower() not in STILL_EXTS or not src.is_file():
                reason = 'missing_or_unsupported_source_still'
            elif not src.stat().st_size:
                reason = 'empty_still'
        if reason:
            rejected.append({'scene_id': scene.id, 'reason': reason})
            continue
        score = 10
        if getattr(v, 'scene_visual_type', '') == 'dramatic':
            score += 5
        if getattr(scene, 'beat_role', '') in ('hook', 'tension', 'reveal', 'turn'):
            score += 4
        if getattr(v, 'scene_visual_type', '') == 'abstract':
            score += 2
        choices.append(Pick(scene.id, index, round(start, 3), round(duration, 3),
                            str(src.resolve()), score, 'existing_AI_still_safe_to_animate'))
    chosen = []
    for item in sorted(choices, key=lambda p: (-p.score, p.start_sec, p.scene_id)):
        midpoint = item.start_sec + item.duration_sec/2
        if all(abs(midpoint-(p.start_sec+p.duration_sec/2)) >= spacing_sec for p in chosen):
            chosen.append(item)
        if len(chosen) == max_clips:
            break
    chosen.sort(key=lambda p: p.start_sec)
    unused = [{'scene_id': p.scene_id, 'reason': 'clip_budget_or_spacing'}
              for p in choices if p not in chosen]
    return {'mode': 'dry_run', 'engine': 'finance_cinematic_f2',
            'total_duration_sec': round(t, 3), 'total_scenes': len(graph.scenes),
            'selected_count': len(chosen), 'eligible_count': len(choices),
            'selected': [asdict(p) for p in chosen], 'skipped': rejected+unused,
            'note': 'Only existing local AI stills. Visuals are illustrative 2.5D motion, not neural AI video.'}


def prepare_specs(report: dict, folder: Path, *, width: int = 640, fps: int = 18) -> dict[str, Path]:
    """Write small source plates and F1 shot specs for approved dry-run picks."""
    if not 160 <= width <= 1280 or not 6 <= fps <= 30:
        raise EngineError('Invalid render resolution/FPS')
    picks = report.get('selected', [])
    mapping = {}
    for item in picks:
        source = Path(item['source'])
        if not source.is_file() or source.suffix.lower() not in STILL_EXTS:
            raise EngineError(f"Original AI still missing: {source}")
        with Image.open(source) as img:
            if img.width*img.height > MAX_SOURCE_PIXELS:
                raise EngineError(f"Source exceeds low-RAM limit: {source}")
            if img.width <= 0 or img.height <= 0:
                raise EngineError('Invalid image size')
            # Same aspect as SceneGraph: report carries exact scene-canvas ratio.
            aspect = float(report['output_width'])/float(report['output_height'])
            height = max(160, round(width/aspect))
            if width*height > 1_200_000:
                raise EngineError('Target exceeds CPU budget')
            img = img.convert('RGB')
            in_ratio = img.width/img.height
            if in_ratio > aspect:
                cropw = round(img.height*aspect)
                left = (img.width-cropw)//2
                img = img.crop((left, 0, left+cropw, img.height))
            else:
                croph = round(img.width/aspect)
                top = (img.height-croph)//2
                img = img.crop((0, top, img.width, top+croph))
            thumb = img.resize((width, height), Image.Resampling.LANCZOS)
        sid = item['scene_id']
        folder_id = hashlib.sha256(sid.encode()).hexdigest()[:12]
        local = Path(folder)/folder_id
        local.mkdir(parents=True, exist_ok=True)
        thumb.save(local/'plate.jpg', quality=90, optimize=True)
        camera = ('dolly_in', 'truck_right', 'dolly_out', 'truck_left')[item['index']%4]
        spec = {'background': 'plate.jpg', 'width':width, 'height':height, 'fps':fps,
                'duration_sec':item['duration_sec'], 'camera':camera,
                'camera_strength':0.08,
                'seed':int(folder_id[:6],16)%1000000,
                'effects':{'clouds':False,'dust':True,'light_glow':True},
                'layers':[]}
        path = local/'shot.json'
        path.write_text(json.dumps(spec, indent=2), encoding='utf-8')
        mapping[sid] = path
    return mapping


def auto_apply(graph: Any, report: dict, output_dir: Path, *, fps: int = 18,
               width: int = 640, cache_dir: Path | None = None):
    """Explicitly called ONLY by CLI --apply. Deep-copy from F1 bridge."""
    if not report.get('selected'):
        raise EngineError('No safe AI stills found. Keep original graph unchanged.')
    report = dict(report, output_width=graph.width, output_height=graph.height)
    specs = prepare_specs(report, Path(output_dir)/'specs', width=width, fps=fps)
    return attach_finance_clips(graph, specs, Path(output_dir)/'clips', cache_dir=cache_dir)
