#!/usr/bin/env python3
"""
Swap the approved geography sequence into an ALREADY RENDERED job, rebuilding
only the scenes that changed.

One continuous flight is rendered for the combined duration of the two beats and
then split on the beat boundary, so the camera move carries across the cut
instead of restarting. The scenes are repointed at the halves and the existing
`render_ffmpeg.render` is called: its manifest rebuilds only the clips whose
inputs changed, re-concatenates, re-burns captions and re-muxes the original
audio. Narration, chart, footage, music and SFX are never touched.

    .venv/bin/python scripts/replace_geo_scenes.py --job vid_forex_explained_v1 \
        --scenes s2 s3 --from-region "United States of America" --to-region Germany
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--scenes", nargs=2, default=["s2", "s3"])
    parser.add_argument("--from-region", default="United States of America")
    parser.add_argument("--to-region", default="Germany")
    parser.add_argument("--from-label", default="USD")
    parser.add_argument("--to-label", default="EUR")
    parser.add_argument("--height", type=int, default=960)
    args = parser.parse_args()

    from app.brand import load_theme
    from app.config import load_channel, settings
    from app.pipeline import geo_data, postprocess, render_ffmpeg, threejs_engine
    from app.schemas.scene import SceneGraph

    job = settings().data_dir / "jobs" / args.job
    graph = SceneGraph.model_validate_json((job / "scene_graph.json").read_text())
    first, second = (next(s for s in graph.scenes if s.id == sid) for sid in args.scenes)
    fps = graph.fps
    # Frame counts, not seconds: the split has to land exactly on the boundary the
    # renderer will use, or the second clip starts a frame into the wrong shot.
    frames_a = max(1, round(first.duration_sec * fps))
    frames_b = max(1, round(second.duration_sec * fps))
    seconds = (frames_a + frames_b) / fps
    height = args.height
    width = round(height * 9 / 16 / 2) * 2

    theme = load_theme(graph.brand_id or "k70")
    world, source = geo_data.borders(geo_data.WORLD_URL, only=args.from_region)
    _, target = geo_data.borders(geo_data.WORLD_URL, only=args.to_region)
    src_lon, src_lat = geo_data.centroid(source)
    dst_lon, dst_lat = geo_data.centroid(target)

    out_dir = job / "geo"
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": f"{args.job}_geo", "outputDir": str(frames_dir),
        "template": "globe_flight", "width": width, "height": height,
        "fps": fps, "frames": frames_a + frames_b, "seed": 11,
        "title": "", "label": "", "values": [], "labels": [],
        "palette": theme.palette, "fontFamily": theme.display.name,
        "world": world,
        "regions": [
            {"rings": source, "label": args.from_label, "lon": src_lon,
             "lat": src_lat, "tone": "primary"},
            {"rings": target, "label": args.to_label, "lon": dst_lon,
             "lat": dst_lat, "tone": "secondary"},
        ],
        "route": {"from": [src_lon, src_lat], "to": [dst_lon, dst_lat],
                  "fromLabel": args.from_label, "toLabel": args.to_label},
        "flight": [
            {"lon": -48.0, "lat": 34.0, "altitude": 4.30, "hold": 1.0},
            {"lon": src_lon, "lat": src_lat, "altitude": 1.55, "hold": 1.3},
            {"lon": -42.0, "lat": 46.0, "altitude": 2.70, "hold": 1.2},
            {"lon": dst_lon, "lat": dst_lat, "altitude": 1.22, "hold": 1.4},
        ],
    }
    print(f"   flight : {seconds:.2f}s = {args.scenes[0]} {frames_a}f + "
          f"{args.scenes[1]} {frames_b}f @ {width}x{height}")

    started = time.perf_counter()
    result = await threejs_engine._worker_render(payload)
    whole = out_dir / "flight.mp4"
    await threejs_engine._encode(frames_dir, fps, whole)
    await threejs_engine.close_worker()
    geo_s = time.perf_counter() - started

    # Split on the frame boundary. Re-encoded rather than stream-copied because a
    # copy can only cut on a keyframe, which would drift the boundary.
    halves = []
    for index, (count, offset) in enumerate(((frames_a, 0), (frames_b, frames_a))):
        piece = out_dir / f"{args.scenes[index]}_geo.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(whole),
             "-vf", f"select='between(n\\,{offset}\\,{offset + count - 1})',setpts=PTS-STARTPTS",
             "-frames:v", str(count), "-an", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps), "-y", str(piece)],
            check=True)
        halves.append(piece)
        print(f"   {args.scenes[index]}: {piece.name} ({count} frames)")

    for scene, piece in zip((first, second), halves):
        scene.visual.asset_path = str(piece)
        scene.visual.type = "threejs"
        scene.visual.motion = "none"
        scene.visual.layers = []

    started = time.perf_counter()
    raw = await render_ffmpeg.render(graph, job / "render_raw.mp4")
    channel = load_channel(graph.meta.channel_id)
    final = await postprocess.finalize(graph, str(raw), channel)
    compose_s = time.perf_counter() - started
    (job / "scene_graph.json").write_text(graph.model_dump_json(indent=2))

    print(f"\n   geo render   : {geo_s:.1f}s · worker RSS {float(result.get('rssMb', 0)):.0f}MB")
    print(f"   recomposition: {compose_s:.1f}s")
    print(f"   final        : {final['mp4']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
