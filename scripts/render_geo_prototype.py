#!/usr/bin/env python3
"""
PROTOTYPE — continuous camera flight World → USA → state, handed off to the
short's existing USA visual with a frame-matched connector.

Everything here drives the EXISTING Three.js worker (`globe_flight` template) and
the existing encoder in `pipeline/threejs_engine.py`. There is no second
pipeline: brand palette comes from the brand manager, borders come from the
content-addressed geo cache, the connector is plain FFmpeg, and a pure-numpy 2D
map render stands in whenever the browser cannot run.

    .venv/bin/python scripts/render_geo_prototype.py --state Texas
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def build(state: str, seconds: float, fps: int, quality: str) -> dict:
    from app.brand import load_theme
    from app.pipeline import geo_data, threejs_engine

    width, height = (1080, 1920) if quality == "final" else (360, 640)   # 9:16
    frames = int(seconds * fps)
    theme = load_theme("k70")

    world, usa = geo_data.borders(geo_data.WORLD_URL, only="United States of America")
    states, focus = geo_data.borders(geo_data.STATES_URL, only=state)
    usa_lon, usa_lat = geo_data.centroid(usa)
    state_lon, state_lat = geo_data.centroid(focus)
    if not focus:
        raise SystemExit(f"no state named {state!r} in the boundary file")

    payload = {
        "id": f"geo_{state.lower().replace(' ', '_')}",
        "template": "globe_flight", "width": width, "height": height,
        "fps": fps, "frames": frames, "seed": 7,
        "title": f"{state}, USA", "label": state,
        "values": [], "labels": [],
        "palette": theme.palette, "fontFamily": theme.display.name,
        "world": world + states,
        "highlight": usa,
        "focus": focus,
        # One continuous move: whole globe → country → state. `hold` weights the
        # legs so the descent reads as deceleration rather than three cuts.
        "flight": [
            {"lon": usa_lon - 55, "lat": 18.0, "altitude": 3.40, "hold": 1.0},
            {"lon": usa_lon, "lat": usa_lat, "altitude": 1.05, "hold": 1.6},
            {"lon": state_lon, "lat": state_lat, "altitude": 0.30, "hold": 1.4},
        ],
        "pins": [{"lon": state_lon, "lat": state_lat, "label": state.upper()}],
    }
    # Content-addressed: same borders + same flight + same brand → same file.
    key = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()
    out_dir = ROOT / "data" / "cache" / "threejs" / key
    payload["outputDir"] = str(out_dir / "frames")
    return {"payload": payload, "key": key, "dir": out_dir,
            "mp4": out_dir / "flight.mp4", "theme": theme}


def fallback_2d(payload: dict, output: Path) -> None:
    """SAFE 2D MAP — same rings, same flight, no GPU. Equirectangular projection
    rasterised with numpy and piped straight into FFmpeg, so a host without a
    working browser still ships the beat instead of a blank frame."""
    import numpy as np

    w, h, frames = payload["width"], payload["height"], payload["frames"]
    palette = payload["palette"]

    def rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

    legs = payload["flight"]
    weights = [max(.05, leg["hold"]) for leg in legs]
    total = sum(weights)
    proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-framerate", str(payload["fps"]),
         "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-y", str(output)], stdin=subprocess.PIPE)
    for frame in range(frames):
        progress = frame / max(1, frames - 1)
        travelled, index = progress * total, 0
        while index < len(legs) - 1 and travelled > weights[index]:
            travelled -= weights[index]
            index += 1
        a, b = legs[max(0, index - 1)], legs[index]
        t = min(1.0, travelled / weights[index])
        smooth = t * t * (3 - 2 * t)
        lon = a["lon"] + (b["lon"] - a["lon"]) * smooth
        lat = a["lat"] + (b["lat"] - a["lat"]) * smooth
        span = a["altitude"] + (b["altitude"] - a["altitude"]) * smooth
        span = max(2.0, span * 52.0)                   # altitude → degrees across
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        canvas[:, :] = rgb(palette.get("bg", "#0b1220"))

        def draw(rings, colour, thickness):
            paint = np.array(rgb(colour), dtype=np.uint8)
            for ring in rings:
                pts = np.asarray(ring, dtype=np.float64)
                x = (pts[:, 0] - lon) / span * w + w / 2
                y = h / 2 - (pts[:, 1] - lat) / (span * h / w) * h
                for i in range(len(pts) - 1):
                    steps = 24
                    xs = np.linspace(x[i], x[i + 1], steps).astype(int)
                    ys = np.linspace(y[i], y[i + 1], steps).astype(int)
                    keep = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
                    for dx in range(thickness):
                        canvas[np.clip(ys[keep] + dx, 0, h - 1), xs[keep]] = paint

        draw(payload["world"], palette.get("grid", "#22304d"), 1)
        draw(payload["highlight"], palette.get("secondary", "#3d7bfd"), 2)
        draw(payload["focus"], palette.get("primary", "#f5b301"), 3)
        proc.stdin.write(canvas.tobytes())
    proc.stdin.close()
    proc.wait()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="Texas")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--quality", choices=["preview", "final"], default="final")
    parser.add_argument("--connect", default=str(
        ROOT / "data/cache/threejs/16d09e5e5ef0674f49bff830a3a801540bbfdb5b1f63c6fdc3339c17b7c20aa2/render.mp4"),
        help="existing USA visual to connect to")
    args = parser.parse_args()

    from app.pipeline import threejs_engine

    plan = await build(args.state, args.seconds, args.fps, args.quality)
    payload, out_dir = plan["payload"], plan["dir"]
    (out_dir / "frames").mkdir(parents=True, exist_ok=True)
    legs = " → ".join("({:.0f},{:.0f})@{}".format(leg["lon"], leg["lat"], leg["altitude"])
                      for leg in payload["flight"])
    print(f"   flight: {legs}")
    print(f"   rings : world={len(payload['world'])} highlight={len(payload['highlight'])} "
          f"focus={len(payload['focus'])}")

    started = time.perf_counter()
    engine, rss = "threejs", 0.0
    if plan["mp4"].is_file():
        engine = "cache_hit"
    else:
        try:
            result = await threejs_engine._worker_render(payload)
            rss = float(result.get("rssMb", 0))
            await threejs_engine._encode(out_dir / "frames", payload["fps"], plan["mp4"])
        except Exception as error:                     # noqa: BLE001 — this IS the fallback
            print(f"   ⚠ Three.js unavailable ({type(error).__name__}: "
                  f"{str(error)[:110]}) → safe 2D map")
            engine = "fallback_2d"
            fallback_2d(payload, plan["mp4"])
    render_s = time.perf_counter() - started
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024

    # FRAME-MATCHED CONNECTOR — the flight's LAST frame is extracted and used as
    # the first frame of the hand-off, so the cut lands on identical pixels
    # instead of a jump. Same trick as a scroll-driven scene change: the next
    # scene starts exactly where the camera stopped.
    still = out_dir / "connector_frame.png"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-sseof", "-0.05",
                    "-i", str(plan["mp4"]), "-frames:v", "1", "-y", str(still)],
                   check=False)
    joined = out_dir / "prototype.mp4"
    following = Path(args.connect)
    if following.is_file():
        listing = out_dir / "concat.txt"
        listing.write_text(f"file '{plan['mp4']}'\nfile '{following}'\n")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat",
                        "-safe", "0", "-i", str(listing), "-c:v", "libx264", "-preset",
                        "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r",
                        str(payload["fps"]), "-vf",
                        f"scale={payload['width']}:{payload['height']}:force_original_aspect_ratio=increase,"
                        f"crop={payload['width']}:{payload['height']},setsar=1",
                        "-y", str(joined)], check=False)
    print(f"\n   engine       : {engine}")
    print(f"   render       : {render_s:.1f}s · worker RSS {rss:.0f}MB · "
          f"children peak {peak:.0f}MB")
    print(f"   flight mp4   : {plan['mp4']}")
    print(f"   connector    : {still if still.is_file() else '—'}")
    print(f"   prototype    : {joined if joined.is_file() else '(no connect target)'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
