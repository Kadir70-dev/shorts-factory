"""F3: recover/generate safe AI stills for a SceneGraph copy, then animate via F1/F2.

Free-only generation (Pollinations). Never overwrites the original graph or MP4s.
    python scripts/finance_cinematic_f3.py \
      --graph data/series/bitcoin_history/ep01/scene_graph.json \
      --missing data/series/bitcoin_history/ep01/assets/missing_ai_images.json \
      --out-dir data/finance_f3/bitcoin_ep01 --limit 8 --render-clips
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/'apps'/'api'))
from tools.finance_cinematic_cpu.auto import auto_apply, select_scenes
from tools.finance_cinematic_cpu.p0 import spread_items
from tools.finance_cinematic_cpu.stills import (eligible, graph_with_stills, load_missing,
                                                resolve_stills)


def main():
    p = argparse.ArgumentParser(description='F3 AI stills -> F2 cinematic clips')
    p.add_argument('--graph', type=Path, required=True)
    p.add_argument('--missing', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--limit', type=int, default=8)
    p.add_argument('--no-generate', action='store_true', help='recover local stills only')
    p.add_argument('--render-clips', action='store_true', help='run F1/F2 on recovered stills')
    p.add_argument('--max-clips', type=int, default=8)
    p.add_argument('--balanced', action='store_true',
                   help='P0: spread eligible new AI stills across the entire episode')
    p.add_argument('--spacing-sec', type=float, default=25)
    p.add_argument('--width', type=int, default=640)
    p.add_argument('--fps', type=int, default=18)
    p.add_argument('--variant', action='append', default=[], metavar='SCENE=N',
                   help='force a new free generation with seed variant N (keeps provenance)')
    p.add_argument('--refine', type=Path, help='JSON {scene_id: reviewed prompt}; original kept in provenance')
    p.add_argument('--out-video', type=Path, help='NEW full render; needs narration audio present')
    a = p.parse_args()
    from app.schemas.scene import SceneGraph
    original = a.graph.resolve()
    out = a.out_dir.resolve()
    if out == original.parent or original.is_relative_to(out):
        p.error('--out-dir must not contain the original SceneGraph')
    new_graph = out/'scene_graph_finance_f3.json'
    if new_graph.exists():
        p.error(f'{new_graph} exists; choose a fresh --out-dir')
    if a.out_video and (not a.render_clips or a.out_video.resolve().exists()):
        p.error('--out-video needs --render-clips and a path that does not exist yet')
    variants = {}
    for v in a.variant:
        sid, _, n = v.partition('=')
        if not n.isdigit() or not 1 <= int(n) <= 99:
            p.error(f'bad --variant {v!r}; use SCENE=N with N in 1..99')
        variants[sid] = int(n)
    graph = SceneGraph.model_validate_json(original.read_text(encoding='utf-8'))
    items = load_missing(a.missing)
    if a.balanced:
        # First validate all candidates with unchanged F3 safety rules, then
        # distribute the requested batch across the FULL timeline.
        all_ok, skipped = eligible(graph, items, limit=24)
        ok = spread_items(graph, all_ok, limit=a.limit)
        picked = {item['scene_id'] for item in ok}
        skipped += [{'scene_id': item['scene_id'], 'reason': 'balanced_batch_limit'}
                    for item in all_ok if item['scene_id'] not in picked]
    else:
        ok, skipped = eligible(graph, items, limit=a.limit)
    print(json.dumps({'eligible': [i['scene_id'] for i in ok], 'skipped': skipped}, indent=2))
    t0 = time.monotonic()
    results = resolve_stills(ok, original.parent, out/'stills', generate=not a.no_generate,
                             variants=variants,
                             refinements=json.loads(a.refine.read_text()) if a.refine else None)
    for r in results:
        print(f'{r.scene_id:6} {r.status:10} {r.elapsed_sec:6.1f}s {r.path or r.detail}')
    edited = graph_with_stills(graph, results)
    new_graph.write_text(edited.model_dump_json(indent=2), encoding='utf-8')
    summary = {'stills_sec': round(time.monotonic()-t0, 2), 'new_graph': str(new_graph),
               'counts': {s: sum(r.status == s for r in results)
                          for s in ('recovered', 'generated', 'failed', 'skipped')}}
    if a.render_clips:
        report = select_scenes(edited, max_clips=a.max_clips, spacing_sec=a.spacing_sec)
        summary['clips_selected'] = report['selected_count']
        if report['selected_count']:
            t1 = time.monotonic()
            animated = auto_apply(edited, report, out, width=a.width, fps=a.fps,
                                  cache_dir=out/'cache')
            summary['clips_sec'] = round(time.monotonic()-t1, 2)
            clip_graph = out/'scene_graph_finance_f3_clips.json'
            clip_graph.write_text(animated.model_dump_json(indent=2), encoding='utf-8')
            (out/'selection_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            summary['clip_graph'] = str(clip_graph)
            summary['clips'] = sorted(str(x) for x in (out/'clips').glob('*.mp4'))
            if a.out_video:
                from app.pipeline import render_ffmpeg
                a.out_video.parent.mkdir(parents=True, exist_ok=True)
                asyncio.run(render_ffmpeg.render(animated, a.out_video.resolve()))
                summary['out_video'] = str(a.out_video.resolve())
    (out/'f3_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
