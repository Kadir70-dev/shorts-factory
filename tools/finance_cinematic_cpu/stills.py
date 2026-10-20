"""F3: turn exported AI-still prompts into real local stills, then hand them to F2.

Additive and production-safe:
- Only scenes F2 already judged safe except for a missing source still are eligible
  (no charts, data, stat/source overlays, evidence cards or authentic-footage beats).
- Recovery first: an existing valid file at the suggested path, or an earlier
  generation of the exact same prompt in the shared content-addressed image cache.
- Generation is FREE-only by default (Pollinations, the existing provider). Billed
  providers are never called from here; they are reported as needing approval.
- Never writes the original SceneGraph; returns a deep copy with asset paths set.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from PIL import Image, ImageStat
from .auto import STILL_EXTS, UNSAFE_TERMS, select_scenes
from .engine import EngineError

FREE_PROVIDERS = ('pollinations',)
PAID_PROVIDERS = ('google_ai', 'huggingface', 'comfyui_remote')
MIN_SHORT_SIDE = 512
MIN_LUMA_STDDEV = 12.0          # rejects flat/blank plates and solid placeholders
MAX_STILLS = 24
FREE_MIN_INTERVAL_SEC = {'pollinations': 50.0}   # free tier: 1 image / 45s / IP


@dataclass(frozen=True)
class StillResult:
    scene_id: str
    status: str                 # recovered | generated | failed | skipped
    path: str | None
    provider: str | None
    prompt: str
    seed: int
    detail: str = ''
    sha256: str | None = None
    elapsed_sec: float = 0.0


def load_missing(path: Path) -> list[dict]:
    items = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(items, list):
        raise EngineError('missing_ai_images.json must be a list')
    for it in items:
        if not isinstance(it, dict) or not it.get('scene_id') or not it.get('query'):
            raise EngineError('each missing item needs scene_id and query')
    return items


def eligible(graph: Any, items: list[dict], *, limit: int = 8) -> tuple[list[dict], list[dict]]:
    """Return (eligible, skipped). Re-uses F2 safety rules; only a missing still may block."""
    if not 1 <= limit <= MAX_STILLS:
        raise EngineError(f'limit must be 1..{MAX_STILLS}')
    report = select_scenes(graph, max_clips=20, spacing_sec=0)
    reasons = {x['scene_id']: x['reason'] for x in report['skipped']}
    ok, skipped = [], []
    for it in items:
        sid = it['scene_id']
        reason = reasons.get(sid)
        if reason not in (None, 'missing_or_unsupported_source_still', 'clip_budget_or_spacing'):
            skipped.append({'scene_id': sid, 'reason': reason})
        elif any(t in it['query'].lower() for t in UNSAFE_TERMS):
            skipped.append({'scene_id': sid, 'reason': 'prompt_requests_authentic_material'})
        elif len(ok) >= limit:
            skipped.append({'scene_id': sid, 'reason': 'batch_limit'})
        else:
            ok.append(it)
    return ok, skipped


def full_prompt(query: str) -> str:
    """Same prompt shape as providers.ai_image_generate, minus the paid LLM rewrite."""
    from app.pipeline.providers import AI_IMAGE_NEGATIVE, AI_IMAGE_STYLE
    return f'{query.strip()}. {AI_IMAGE_STYLE}. Avoid: {AI_IMAGE_NEGATIVE}.'.strip('. ')


def seed_for(scene_id: str, query: str) -> int:
    return int(hashlib.sha256(f'{scene_id}:{query}'.encode()).hexdigest()[:8], 16) % 1_000_000


def validate_still(path: Path) -> str | None:
    """Return a rejection reason, or None when the file is a usable photo-like still."""
    p = Path(path)
    if not p.is_file() or p.suffix.lower() not in STILL_EXTS or p.stat().st_size < 1024:
        return 'missing_or_tiny_file'
    try:
        with Image.open(p) as im:
            im.verify()
        with Image.open(p) as im:
            if min(im.size) < MIN_SHORT_SIDE:
                return f'too_small_{im.size[0]}x{im.size[1]}'
            stat = ImageStat.Stat(im.convert('L').resize((128, 128)))
            if stat.stddev[0] < MIN_LUMA_STDDEV:
                return 'flat_or_placeholder_image'
    except Exception as e:  # noqa: BLE001
        return f'undecodable:{type(e).__name__}'
    return None


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _cache_hit(prompt: str, seed: int) -> Path | None:
    """Exact-prompt hit in the shared provider cache (generated earlier, reused free)."""
    from app.pipeline.providers import _img_cache
    from app.config import settings
    path = _img_cache(f'pollinations:{settings().pollinations_model}:{seed}:{prompt}', 'jpg')
    return path if path.exists() else None


async def _pollinations(prompt: str, seed: int) -> Path:
    from app.pipeline.providers import _pollinations_image
    return Path(await _pollinations_image(prompt, seed))


def resolve_stills(items: list[dict], episode_dir: Path, out_dir: Path, *,
                   generate: bool = True, provider: str = 'pollinations',
                   generator: Callable[[str, int], Any] | None = None,
                   min_interval_sec: float | None = None,
                   sleep: Callable[[float], None] = time.sleep) -> list[StillResult]:
    """Recover or generate one still per item into out_dir/<scene_id>.jpg."""
    if provider in PAID_PROVIDERS:
        raise EngineError(f'{provider} is billed; show cost estimate and get approval first')
    if provider not in FREE_PROVIDERS:
        raise EngineError(f'unknown provider {provider!r}')
    gen = generator or _pollinations
    gap = FREE_MIN_INTERVAL_SEC.get(provider, 0.0) if min_interval_sec is None else min_interval_sec
    last_call: float | None = None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for it in items:
        sid, query = it['scene_id'], it['query']
        prompt, seed = full_prompt(query), seed_for(sid, query)
        target = out_dir / f'{sid}.jpg'
        started = time.monotonic()
        src, how = None, None
        suggested = it.get('suggested_file')
        for cand in ([episode_dir / suggested] if suggested else []) + [target]:
            if validate_still(cand) is None:
                src, how = cand, 'recovered'
                break
        if src is None and (hit := _cache_hit(prompt, seed)) and validate_still(hit) is None:
            src, how = hit, 'recovered'
        if src is None and not generate:
            results.append(StillResult(sid, 'skipped', None, None, prompt, seed, 'generation disabled'))
            continue
        if src is None:
            if last_call is not None and (wait := gap - (time.monotonic() - last_call)) > 0:
                sleep(wait)                       # respect free-tier rate limit
            last_call = time.monotonic()
            try:
                src = Path(asyncio.run(gen(prompt, seed)) if asyncio.iscoroutinefunction(gen)
                           else gen(prompt, seed))
                how = 'generated'
            except Exception as e:  # noqa: BLE001
                results.append(StillResult(sid, 'failed', None, provider, prompt, seed,
                                           f'{type(e).__name__}: {str(e)[:160]}',
                                           elapsed_sec=round(time.monotonic()-started, 2)))
                continue
        bad = validate_still(src)
        if bad:
            results.append(StillResult(sid, 'failed', None, provider, prompt, seed, f'rejected:{bad}',
                                       elapsed_sec=round(time.monotonic()-started, 2)))
            continue
        if src.resolve() != target.resolve():
            with Image.open(src) as im:
                im.convert('RGB').save(target, 'JPEG', quality=92)
        results.append(StillResult(sid, how, str(target.resolve()),
                                   provider if how == 'generated' else 'local',
                                   prompt, seed, sha256=_sha(target),
                                   elapsed_sec=round(time.monotonic()-started, 2)))
    write_provenance(results, out_dir / 'provenance.json')
    return results


def write_provenance(results: list[StillResult], path: Path) -> None:
    data = {'engine': 'finance_cinematic_f3', 'ai_generated_illustration': True,
            'note': 'AI-generated illustrative stills; not archival photographs or evidence.',
            'stills': [asdict(r) for r in results]}
    Path(path).write_text(json.dumps(data, indent=2), encoding='utf-8')


def graph_with_stills(graph: Any, results: list[StillResult]):
    """Deep copy with asset_path set for usable stills only. Original untouched."""
    paths = {r.scene_id: r.path for r in results if r.path and r.status in ('recovered', 'generated')}
    edited = graph.model_copy(deep=True)
    for scene in edited.scenes:
        if scene.id in paths:
            scene.visual.asset_path = paths[scene.id]
    return edited
