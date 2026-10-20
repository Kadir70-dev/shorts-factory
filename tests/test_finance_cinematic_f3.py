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
    r1 = stills.resolve_stills([{'scene_id': 'a', 'query': 'q'}], tmp_path, tmp_path/'o1', generator=boom)
    r2 = stills.resolve_stills([{'scene_id': 'a', 'query': 'q'}], tmp_path, tmp_path/'o2', generator=flat)
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
