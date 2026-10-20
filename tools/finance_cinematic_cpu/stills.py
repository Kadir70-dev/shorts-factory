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
import re
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
_LAST_CALL: dict[str, float] = {}     # provider -> monotonic time, process-wide
SCENE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
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
    variant: int = 0
    original_query: str | None = None    # set when a reviewed refinement replaced it


def load_missing(path: Path) -> list[dict]:
    items = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(items, list):
        raise EngineError('missing_ai_images.json must be a list')
    for it in items:
        if not isinstance(it, dict) or not it.get('scene_id') or not it.get('query'):
            raise EngineError('each missing item needs scene_id and query')
        if not isinstance(it['scene_id'], str) or not SCENE_ID_RE.match(it['scene_id']):
            raise EngineError(f'unsafe scene_id {it["scene_id"]!r}')
        if not isinstance(it['query'], str):
            raise EngineError('query must be a string')
    return items


def safe_scene_id(sid: Any) -> str:
    if not isinstance(sid, str) or not SCENE_ID_RE.match(sid):
        raise EngineError(f'unsafe scene_id {sid!r}')
    return sid


def inside(base: Path, rel: Any) -> Path | None:
    """Resolve a relative path under base (symlinks followed); None if it escapes."""
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
        return None
    root = Path(base).resolve()
    cand = (root / rel).resolve()
    return cand if cand.is_relative_to(root) else None


def eligible(graph: Any, items: list[dict], *, limit: int = 8) -> tuple[list[dict], list[dict]]:
    """Return (eligible, skipped). Re-uses F2 safety rules; only a missing still may block."""
    if not 1 <= limit <= MAX_STILLS:
        raise EngineError(f'limit must be 1..{MAX_STILLS}')
    report = select_scenes(graph, max_clips=20, spacing_sec=0)
    reasons = {x['scene_id']: x['reason'] for x in report['skipped']}
    known = {scene.id for scene in graph.scenes}
    ok, skipped, seen = [], [], set()
    for it in items:
        sid = it.get('scene_id')
        reason = reasons.get(sid)
        if not isinstance(sid, str) or not SCENE_ID_RE.match(sid):
            skipped.append({'scene_id': str(sid)[:64], 'reason': 'unsafe_scene_id'})
        elif sid not in known:
            skipped.append({'scene_id': sid, 'reason': 'unknown_scene_id'})
        elif sid in seen:
            skipped.append({'scene_id': sid, 'reason': 'duplicate_scene_id'})
        elif reason not in (None, 'missing_or_unsupported_source_still', 'clip_budget_or_spacing'):
            skipped.append({'scene_id': sid, 'reason': reason})
        elif any(t in it['query'].lower() for t in UNSAFE_TERMS):
            skipped.append({'scene_id': sid, 'reason': 'prompt_requests_authentic_material'})
        elif len(ok) >= limit:
            skipped.append({'scene_id': sid, 'reason': 'batch_limit'})
        else:
            ok.append(it)
            seen.add(sid)
    return ok, skipped


def full_prompt(query: str) -> str:
    """Same prompt shape as providers.ai_image_generate, minus the paid LLM rewrite."""
    from app.pipeline.providers import AI_IMAGE_NEGATIVE, AI_IMAGE_STYLE
    return f'{query.strip()}. {AI_IMAGE_STYLE}. Avoid: {AI_IMAGE_NEGATIVE}.'.strip('. ')


def seed_for(scene_id: str, query: str, variant: int = 0) -> int:
    key = f'{scene_id}:{query}' + (f':v{variant}' if variant else '')
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 1_000_000


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


FREE_LIMIT_RETRIES = 3          # the free 45s/IP window is shared by everything on the IP


async def _pollinations(prompt: str, seed: int, *, retries: int = FREE_LIMIT_RETRIES,
                        wait_sec: float = 50.0) -> Path:
    """Existing free provider; on a free-tier 402 wait out the window and retry."""
    from app.pipeline.providers import _pollinations_image
    for attempt in range(retries + 1):
        try:
            return Path(await _pollinations_image(prompt, seed))
        except RuntimeError as e:
            if '402' not in str(e) or attempt == retries:
                raise
            await asyncio.sleep(wait_sec)
    raise RuntimeError('unreachable')


def resolve_stills(items: list[dict], episode_dir: Path, out_dir: Path, *,
                   generate: bool = True, provider: str = 'pollinations',
                   generator: Callable[[str, int], Any] | None = None,
                   min_interval_sec: float | None = None,
                   sleep: Callable[[float], None] = time.sleep,
                   variants: dict[str, int] | None = None,
                   refinements: dict[str, str] | None = None) -> list[StillResult]:
    """Recover or generate one still per item into out_dir/<scene_id>.jpg."""
    if provider in PAID_PROVIDERS:
        raise EngineError(f'{provider} is billed; show cost estimate and get approval first')
    if provider not in FREE_PROVIDERS:
        raise EngineError(f'unknown provider {provider!r}')
    gen = generator or _pollinations
    gap = FREE_MIN_INTERVAL_SEC.get(provider, 0.0) if min_interval_sec is None else min_interval_sec
    variants, refinements = variants or {}, refinements or {}
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for it in items:
        sid, query = safe_scene_id(it.get('scene_id')), it['query']
        original = None
        if sid in refinements:                 # reviewed wording; same visual intent
            refined = refinements[sid]
            if not isinstance(refined, str) or not 10 <= len(refined) <= 600 \
                    or any(t in refined.lower() for t in UNSAFE_TERMS):
                raise EngineError(f'invalid refinement for {sid}')
            original, query = query, refined.strip()
        variant = int(variants.get(sid, 0))
        prompt, seed = full_prompt(query), seed_for(sid, query, variant)
        target = out_dir / (f'{sid}.v{variant}.jpg' if variant else f'{sid}.jpg')
        if not target.parent == out_dir:
            raise EngineError(f'output path escapes {out_dir}')
        started = time.monotonic()
        src, how = None, None
        suggested = inside(episode_dir, it.get('suggested_file')) if it.get('suggested_file') else None
        # A forced variant must produce a NEW image, so skip local recovery for it.
        local = [] if variant else ([suggested] if suggested else []) + [target]
        for cand in local:
            if validate_still(cand) is None:
                src, how = cand, 'recovered'
                break
        if src is None and (hit := _cache_hit(prompt, seed)) and validate_still(hit) is None:
            src, how = hit, 'recovered'
        if src is None and not generate:
            results.append(StillResult(sid, 'skipped', None, None, prompt, seed, 'generation disabled', variant=variant, original_query=original))
            continue
        if src is None:
            last_call = _LAST_CALL.get(provider)
            if last_call is not None and (wait := gap - (time.monotonic() - last_call)) > 0:
                sleep(wait)                       # respect free-tier rate limit
            _LAST_CALL[provider] = time.monotonic()
            try:
                src = Path(asyncio.run(gen(prompt, seed)) if asyncio.iscoroutinefunction(gen)
                           else gen(prompt, seed))
                how = 'generated'
            except Exception as e:  # noqa: BLE001
                results.append(StillResult(sid, 'failed', None, provider, prompt, seed,
                                           f'{type(e).__name__}: {str(e)[:160]}',
                                           elapsed_sec=round(time.monotonic()-started, 2), variant=variant, original_query=original))
                continue
        bad = validate_still(src)
        if bad:
            results.append(StillResult(sid, 'failed', None, provider, prompt, seed, f'rejected:{bad}',
                                       elapsed_sec=round(time.monotonic()-started, 2), variant=variant, original_query=original))
            continue
        if src.resolve() != target.resolve():
            with Image.open(src) as im:
                im.convert('RGB').save(target, 'JPEG', quality=92)
        results.append(StillResult(sid, how, str(target.resolve()),
                                   provider if how == 'generated' else 'local',
                                   prompt, seed, sha256=_sha(target),
                                   elapsed_sec=round(time.monotonic()-started, 2),
                                   variant=variant, original_query=original))
    write_provenance(results, out_dir / 'provenance.json')
    return results


def write_provenance(results: list[StillResult], path: Path) -> None:
    """Append-only history: earlier entries (e.g. replaced variants) are kept."""
    path = Path(path)
    old = json.loads(path.read_text(encoding='utf-8')).get('stills', []) if path.exists() else []
    new = [asdict(r) for r in results]
    keep = [o for o in old if (o.get('scene_id'), o.get('seed'), o.get('status'))
            not in {(n['scene_id'], n['seed'], n['status']) for n in new}]
    data = {'engine': 'finance_cinematic_f3', 'ai_generated_illustration': True,
            'note': 'AI-generated illustrative stills; not archival photographs or evidence. '
                    'Provider marks are left intact per provider terms.',
            'stills': keep + new}
    Path(path).write_text(json.dumps(data, indent=2), encoding='utf-8')


def graph_with_stills(graph: Any, results: list[StillResult]):
    """Deep copy with asset_path set for usable stills only. Original untouched."""
    paths = {r.scene_id: r.path for r in results if r.path and r.status in ('recovered', 'generated')}
    edited = graph.model_copy(deep=True)
    for scene in edited.scenes:
        if scene.id in paths:
            scene.visual.asset_path = paths[scene.id]
    return edited
