"""F3 still recovery/generation tests; CPU-only, no network, fake generator."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'apps'/'api'))
from tools.finance_cinematic_cpu.engine import EngineError
from tools.finance_cinematic_cpu import stills
from test_finance_cinematic_auto import _graph, _scene


def _photo(path, size=(768, 1344)):
    rng = np.random.default_rng(1)
    blocks = rng.integers(0, 255, (14, 8, 3), dtype=np.uint8)   # photo-like large structure
    Image.fromarray(blocks).resize(size, Image.NEAREST).save(path)
    return path


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    monkeypatch.setattr(stills, '_LAST_CALL', {})
    monkeypatch.setattr(stills, '_cache_hit', lambda prompt, seed: None)
    monkeypatch.setattr(stills, 'full_prompt', lambda q: q + '. style')


def test_eligible_respects_f2_safety_and_limit():
    g = _graph(_scene('a'), _scene('b'), _scene('chart', kind='dataviz'),
               _scene('ev', overlays=[type('O', (), {'type': 'source'})()]), _scene('c'))
    items = [{'scene_id': s, 'query': 'night skyline'} for s in ('a', 'chart', 'ev', 'b', 'c')]
    ok, skipped = stills.eligible(g, items, limit=2)
    assert [i['scene_id'] for i in ok] == ['a', 'b']
    reasons = {s['scene_id']: s['reason'] for s in skipped}
    assert reasons == {'chart': 'not_an_AI_still', 'ev': 'number_or_evidence_overlay', 'c': 'batch_limit'}


def test_eligible_blocks_authentic_material_prompts():
    ok, skipped = stills.eligible(_graph(_scene('a')),
                                  [{'scene_id': 'a', 'query': 'historical photograph of a bank'}])
    assert not ok and skipped[0]['reason'] == 'prompt_requests_authentic_material'


def test_validate_rejects_placeholders(tmp_path):
    flat = tmp_path/'flat.jpg'
    Image.new('RGB', (800, 1400), (20, 30, 60)).save(flat)
    small = _photo(tmp_path/'small.jpg', (300, 300))
    assert stills.validate_still(flat) == 'flat_or_placeholder_image'
    assert stills.validate_still(small).startswith('too_small')
    assert stills.validate_still(_photo(tmp_path/'ok.jpg')) is None


def test_resolve_recovers_then_generates_and_writes_provenance(tmp_path):
    ep = tmp_path/'ep'
    (ep/'assets/ai_stills').mkdir(parents=True)
    _photo(ep/'assets/ai_stills/a.jpg')
    calls = []

    def fake(prompt, seed):
        calls.append(seed)
        return _photo(tmp_path/f'gen_{seed}.jpg')
    items = [{'scene_id': 'a', 'query': 'q1', 'suggested_file': 'assets/ai_stills/a.jpg'},
             {'scene_id': 'b', 'query': 'q2'}]
    res = stills.resolve_stills(items, ep, tmp_path/'out', generator=fake, min_interval_sec=0)
    assert [r.status for r in res] == ['recovered', 'generated'] and len(calls) == 1
    assert all(Path(r.path).is_file() and r.sha256 for r in res)
    prov = json.loads((tmp_path/'out/provenance.json').read_text())
    assert prov['ai_generated_illustration'] and len(prov['stills']) == 2
    # deterministic seed + idempotent re-run (target now recovered, no new call)
    again = stills.resolve_stills(items, ep, tmp_path/'out', generator=fake)
    assert [r.status for r in again] == ['recovered', 'recovered'] and len(calls) == 1


def test_failed_or_placeholder_generation_is_not_attached(tmp_path):
    def boom(prompt, seed):
        raise RuntimeError('rate limited')

    def flat(prompt, seed):
        p = tmp_path/'flat.jpg'
        Image.new('RGB', (800, 1400), 'navy').save(p)
        return p
    r1 = stills.resolve_stills([{'scene_id': 'a', 'query': 'q'}], tmp_path, tmp_path/'o1', generator=boom, min_interval_sec=0)
    r2 = stills.resolve_stills([{'scene_id': 'a', 'query': 'q'}], tmp_path, tmp_path/'o2', generator=flat, min_interval_sec=0)
    assert r1[0].status == 'failed' and 'rate limited' in r1[0].detail
    assert r2[0].status == 'failed' and 'placeholder' in r2[0].detail
    g = _graph(_scene('a'))
    assert stills.graph_with_stills(g, r1 + r2).scenes[0].visual.asset_path is None


def test_paid_provider_requires_approval(tmp_path):
    with pytest.raises(EngineError, match='billed'):
        stills.resolve_stills([], tmp_path, tmp_path/'o', provider='google_ai')


def test_graph_copy_leaves_original_untouched(tmp_path):
    g = _graph(_scene('a'))
    r = stills.StillResult('a', 'generated', str(tmp_path/'a.jpg'), 'pollinations', 'p', 1)
    new = stills.graph_with_stills(g, [r])
    assert new.scenes[0].visual.asset_path == str(tmp_path/'a.jpg')
    assert g.scenes[0].visual.asset_path is None


def test_free_tier_calls_are_paced(tmp_path):
    waits = []
    gen = lambda prompt, seed: _photo(tmp_path/f'g{seed}.jpg')
    items = [{'scene_id': s, 'query': s} for s in ('a', 'b', 'c')]
    stills.resolve_stills(items, tmp_path, tmp_path/'o', generator=gen,
                          min_interval_sec=50, sleep=waits.append)
    assert len(waits) == 2 and all(45 < w <= 50 for w in waits)


# ---- hardening regressions -------------------------------------------------
@pytest.mark.parametrize('bad', ['../x', 'a/b', '..', '', 'a b', 's1\x00', 'x' * 65, 7])
def test_unsafe_scene_ids_rejected_everywhere(tmp_path, bad):
    f = tmp_path/'m.json'
    f.write_text(json.dumps([{'scene_id': bad, 'query': 'q'}]))
    with pytest.raises(EngineError):
        stills.load_missing(f)
    with pytest.raises(EngineError, match='unsafe scene_id'):
        stills.resolve_stills([{'scene_id': bad, 'query': 'q'}], tmp_path, tmp_path/'o',
                              generator=lambda p, s: _photo(tmp_path/'g.jpg'))
    ok, skipped = stills.eligible(_graph(_scene('a')), [{'scene_id': bad, 'query': 'q'}])
    assert not ok and skipped[0]['reason'] == 'unsafe_scene_id'
    assert not list(tmp_path.parent.glob('x*.jpg'))


def test_unknown_and_duplicate_scene_ids_skipped():
    items = [{'scene_id': 'ghost', 'query': 'q'}, {'scene_id': 'a', 'query': 'q'},
             {'scene_id': 'a', 'query': 'q2'}]
    ok, skipped = stills.eligible(_graph(_scene('a')), items)
    assert [i['scene_id'] for i in ok] == ['a']
    assert {(s['scene_id'], s['reason']) for s in skipped} == {
        ('ghost', 'unknown_scene_id'), ('a', 'duplicate_scene_id')}


@pytest.mark.parametrize('rel', ['../outside.jpg', '/abs/outside.jpg', 'link.jpg'])
def test_suggested_file_outside_episode_is_never_recovered(tmp_path, rel):
    ep = tmp_path/'ep'
    ep.mkdir()
    outside = _photo(tmp_path/'outside.jpg')
    (ep/'link.jpg').symlink_to(outside)              # symlink escaping the episode dir
    if rel.startswith('/abs'):
        rel = str(outside)
    calls = []
    gen = lambda p, s: calls.append(s) or _photo(tmp_path/f'g{s}.jpg')
    res = stills.resolve_stills([{'scene_id': 'a', 'query': 'q', 'suggested_file': rel}],
                                ep, tmp_path/'o', generator=gen, min_interval_sec=0)
    assert res[0].status == 'generated' and len(calls) == 1
    assert stills.inside(ep, rel) is None


def test_suggested_file_inside_episode_still_recovered(tmp_path):
    ep = tmp_path/'ep'
    (ep/'assets').mkdir(parents=True)
    _photo(ep/'assets/a.jpg')
    res = stills.resolve_stills([{'scene_id': 'a', 'query': 'q', 'suggested_file': 'assets/../assets/a.jpg'}],
                                ep, tmp_path/'o', generator=lambda p, s: 1/0)
    assert res[0].status == 'recovered'


def test_variant_forces_new_image_and_keeps_provenance_history(tmp_path):
    gen = lambda p, s: _photo(tmp_path/f'g{s}.jpg', (768 + s % 7, 1344))
    item = [{'scene_id': 'a', 'query': 'q'}]
    first = stills.resolve_stills(item, tmp_path, tmp_path/'o', generator=gen, min_interval_sec=0)
    second = stills.resolve_stills(item, tmp_path, tmp_path/'o', generator=gen, min_interval_sec=0,
                                   variants={'a': 1})
    assert second[0].status == 'generated' and second[0].variant == 1
    assert second[0].seed != first[0].seed and second[0].path.endswith('a.v1.jpg')
    assert Path(first[0].path).is_file()              # original still kept
    prov = json.loads((tmp_path/'o/provenance.json').read_text())['stills']
    assert [(x['variant'], x['status']) for x in prov] == [(0, 'generated'), (1, 'generated')]


def test_pacing_spans_separate_calls_and_failures_keep_variant(tmp_path):
    waits = []
    gen = lambda p, s: _photo(tmp_path/f'g{s}.jpg')
    stills.resolve_stills([{'scene_id': 'a', 'query': 'q'}], tmp_path, tmp_path/'o',
                          generator=gen, min_interval_sec=50, sleep=waits.append)
    res = stills.resolve_stills([{'scene_id': 'b', 'query': 'q'}], tmp_path, tmp_path/'o',
                                generator=lambda p, s: 1/0, min_interval_sec=50,
                                sleep=waits.append, variants={'b': 3})
    assert len(waits) == 1 and res[0].status == 'failed' and res[0].variant == 3


def test_refinement_recorded_in_provenance_and_validated(tmp_path):
    gen = lambda p, s: _photo(tmp_path/f'g{s}.jpg')
    res = stills.resolve_stills([{'scene_id': 'a', 'query': 'orig'}], tmp_path, tmp_path/'o',
                                generator=gen, min_interval_sec=0, variants={'a': 1},
                                refinements={'a': 'still life chain on black velvet, no people'})
    assert res[0].original_query == 'orig' and 'velvet' in res[0].prompt
    for bad in ('short', 'historical photograph of the vault'):
        with pytest.raises(EngineError, match='invalid refinement'):
            stills.resolve_stills([{'scene_id': 'a', 'query': 'orig'}], tmp_path, tmp_path/'o',
                                  generator=gen, refinements={'a': bad})


def test_pollinations_wrapper_retries_only_free_limit(monkeypatch, tmp_path):
    import asyncio
    from app.pipeline import providers
    calls = []

    async def fake(prompt, seed):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError('pollinations unavailable after 13s (402 application/json)')
        return str(tmp_path/'ok.jpg')
    monkeypatch.setattr(providers, '_pollinations_image', fake)
    assert asyncio.run(stills._pollinations('p', 1, wait_sec=0)).name == 'ok.jpg' and len(calls) == 3

    async def down(prompt, seed):
        calls.append(1)
        raise RuntimeError('pollinations unavailable (503)')
    monkeypatch.setattr(providers, '_pollinations_image', down)
    calls.clear()
    with pytest.raises(RuntimeError, match='503'):
        asyncio.run(stills._pollinations('p', 1, wait_sec=0))
    assert len(calls) == 1
