"""F2: scan existing completed K70 SceneGraph and optionally insert AI-still motion.

Dry-run by default; --apply only creates NEW graph and optional NEW final MP4.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/'apps'/'api'))
from tools.finance_cinematic_cpu.auto import auto_apply, select_scenes


def main():
    p = argparse.ArgumentParser(description='F2 auto-select existing AI stills for cinematic CPU motion')
    p.add_argument('--graph', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--max-clips', type=int, default=8)
    p.add_argument('--spacing-sec', type=float, default=25)
    p.add_argument('--width', type=int, default=640)
    p.add_argument('--fps', type=int, default=18)
    p.add_argument('--apply', action='store_true', help='render motion clips and write a NEW graph')
    p.add_argument('--out-video', type=Path, help='optional NEW rendered documentary; requires --apply')
    args = p.parse_args()
    from app.schemas.scene import SceneGraph
    graph = SceneGraph.model_validate_json(args.graph.read_text(encoding='utf-8'))
    report = select_scenes(graph, max_clips=args.max_clips, spacing_sec=args.spacing_sec)
    print(json.dumps({'selected_count':report['selected_count'], 'total_scenes':report['total_scenes'],
                      'selected':report['selected'], 'skipped_count':len(report['skipped'])}, indent=2))
    if args.out_video and not args.apply:
        p.error('--out-video requires --apply')
    if not args.apply:
        print('DRY RUN ONLY: pass --apply to create cinematic clips + NEW graph')
        return
    out = args.out_dir.resolve()
    original = args.graph.resolve()
    if out == original or original.is_relative_to(out):
        p.error('Output directory cannot contain original SceneGraph')
    fresh_graph = out/'scene_graph_finance_f2.json'
    report_file = out/'selection_report.json'
    if fresh_graph.exists() or report_file.exists():
        p.error('Output graph/report exists; choose a fresh --out-dir')
    if args.out_video is not None and args.out_video.resolve().exists():
        p.error('Refusing to overwrite final MP4')
    edited = auto_apply(graph, report, out, width=args.width, fps=args.fps,
                        cache_dir=out/'cache')
    out.mkdir(parents=True,exist_ok=True)
    fresh_graph.write_text(edited.model_dump_json(indent=2), encoding='utf-8')
    report_file.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('NEW SceneGraph:', fresh_graph)
    if args.out_video:
        from app.pipeline import render_ffmpeg
        path = args.out_video.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(render_ffmpeg.render(edited, path))
        print('NEW final finance video:', path)


if __name__ == '__main__':
    main()
