"""F1 CLI sidecar: explicitly chosen cinematic MP4s into an existing SceneGraph.

Never overwrites the original graph or original final video. Does not modify
the K70 frozen production pipeline. Optional rerender uses existing FFmpeg.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "apps" / "api"))
from tools.finance_cinematic_cpu.bridge import attach_finance_clips
from tools.finance_cinematic_cpu.engine import EngineError


def _mapping(path: Path) -> dict[str, Path]:
    path = Path(path).resolve()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw or len(raw) > 20:
        raise EngineError("Mapping must have 1..20 scene_id → local shot spec entries")
    result = {}
    for sid, item in raw.items():
        if not isinstance(sid, str) or not sid or not isinstance(item, str):
            raise EngineError("Mapping keys and values must be nonempty strings")
        rel = Path(item)
        if rel.is_absolute() or "://" in item:
            raise EngineError("Mapping shot JSON must be a relative local path")
        full = (path.parent / rel).resolve()
        if not full.is_relative_to(path.parent) or full.suffix.lower() != ".json" or not full.is_file():
            raise EngineError(f"Invalid local mapping path for {sid}")
        result[sid] = full
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Opt-in 2.5D finance clip injection into finished SceneGraph")
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--out-graph", type=Path, required=True)
    parser.add_argument("--clip-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--out-video", type=Path, default=None,
                        help="Optional NEW 8–10 minute final MP4 via existing renderer")
    args = parser.parse_args()
    original, destination = args.graph.resolve(), args.out_graph.resolve()
    if original == destination or destination.exists():
        parser.error("Never overwrite original or pre-existing graph; select fresh --out-graph")
    if args.out_video is not None and args.out_video.resolve().exists():
        parser.error("Refusing to overwrite existing final video")
    from app.schemas.scene import SceneGraph
    graph = SceneGraph.model_validate_json(original.read_text(encoding="utf-8"))
    mapping = _mapping(args.mapping)
    edited = attach_finance_clips(graph, mapping, args.clip_dir, cache_dir=args.cache_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(edited.model_dump_json(indent=2), encoding="utf-8")
    print(f"New SceneGraph: {destination} | replaced {len(mapping)} illustrative scenes")
    if args.out_video:
        from app.pipeline import render_ffmpeg
        target = args.out_video.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(render_ffmpeg.render(edited, target))
        print(f"Final finance MP4: {target}")


if __name__ == "__main__":
    main()
