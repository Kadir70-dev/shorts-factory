"""
Render stage. We DON'T shell out to `npx remotion render` per job (cold Node
start + bundle every time). Instead Remotion runs as a small render service
(apps/remotion/render-server.ts) that keeps the bundle warm. We POST the
SceneGraph and get back an mp4 path on the shared data volume.

Fallback path (no service): call the CLI. Kept here for local dev.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from ..config import settings
from ..schemas.scene import SceneGraph


async def render_remotion(graph: SceneGraph) -> str:
    work = settings().data_dir / "jobs" / graph.meta.video_id
    out = work / "raw.mp4"
    props_path = work / "scene_graph.json"
    props_path.write_text(graph.model_dump_json())

    # CPU/stability mode: render with pure ffmpeg, never touch Remotion/Node.
    if settings().render_backend.lower() == "ffmpeg":
        from . import render_ffmpeg
        return await render_ffmpeg.render(graph, out)

    try:
        async with httpx.AsyncClient(timeout=900) as c:
            r = await c.post(
                f"{settings().remotion_render_url}/render",
                json={"composition": "Short",
                      "props_path": str(props_path),
                      "out": str(out),
                      "frames": graph.total_frames,
                      "fps": graph.fps},
            )
            r.raise_for_status()
        return str(out)
    except Exception:
        pass

    # 2nd choice: Remotion CLI (cold bundle). 3rd: pure-ffmpeg renderer.
    try:
        return await _render_cli(props_path, out, graph)
    except Exception:
        from . import render_ffmpeg
        return await render_ffmpeg.render(graph, out)


async def _render_cli(props: Path, out: Path, graph: SceneGraph) -> str:
    remotion_dir = Path(__file__).resolve().parents[4] / "apps" / "remotion"
    proc = await asyncio.create_subprocess_exec(
        "npx", "remotion", "render", "Short", str(out),
        f"--props={props}", f"--frames=0-{graph.total_frames - 1}",
        cwd=str(remotion_dir),
    )
    rc = await proc.wait()
    if rc != 0 or not out.exists():
        raise RuntimeError("remotion CLI render failed")
    return str(out)
