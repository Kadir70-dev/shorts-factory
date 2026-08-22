#!/usr/bin/env python3
"""Rerender a completed job after declaring specific 3D->motion fallbacks."""
import argparse, asyncio, json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps'/'api'))

async def run(job_id:str, scene_ids:list[str])->int:
    from app.pipeline import qa,render_ffmpeg,visual_budget
    from app.schemas.scene import SceneGraph
    job=ROOT/'data'/'jobs'/job_id
    raw=json.loads((job/'scene_graph.json').read_text(encoding='utf-8'))
    wanted=set(scene_ids)
    for scene in raw['scenes']:
        if scene['id'] in wanted:
            v=scene['visual']
            if v.get('type')!='motion_gfx' or not v.get('asset_path'):
                raise RuntimeError(f"{scene['id']} is not a resolved motion fallback")
            v['budget_channel']='motion_gfx';v['strategy']='motion_gfx'
            v['decision_reason'] += ' [production QA: resolved 3D fallback declared as motion graphics]'
    graph=SceneGraph.model_validate(raw)
    (job/'scene_graph.json').write_text(graph.model_dump_json(indent=2),encoding='utf-8')
    delivered=visual_budget.measure(graph)
    (job/'visual_breakdown.json').write_text(json.dumps(delivered.as_dict(),indent=2),encoding='utf-8')
    out=job/'final.mp4';await render_ffmpeg.render(graph,out)
    rep=qa.analyze(graph,str(out),render_seconds=0,ram_peak_mb=0,min_free_mb=-1,
                   consistency=None,timed_out=False,budget_report=delivered)
    (job/'qa_report.json').write_text(rep.model_dump_json(indent=2),encoding='utf-8')
    (job/'qa_report.txt').write_text(qa.format_report(rep),encoding='utf-8')
    print(qa.format_report(rep));return 0 if rep.passed else 1

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--job',required=True);ap.add_argument('--scene',action='append',required=True)
    a=ap.parse_args();raise SystemExit(asyncio.run(run(a.job,a.scene)))
