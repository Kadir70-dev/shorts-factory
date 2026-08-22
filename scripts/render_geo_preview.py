#!/usr/bin/env python3
"""
Preview ONE continuous geography scene for visual approval:

    world  →  USA highlight  →  curved route  →  Germany highlight

Drives the existing Three.js worker and encoder. Renders nothing else and
touches no job folder, so an approved look can be promoted afterwards without
re-rendering anything that already passed.

    .venv/bin/python scripts/render_geo_preview.py --seconds 6.5 --height 960
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def peak_child_rss_mb() -> float:
    import resource
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=6.5)
    parser.add_argument("--height", type=int, default=960, help="960 = 540x960")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--force-2d", action="store_true")
    args = parser.parse_args()

    from app.brand import load_theme
    from app.pipeline import geo_data, threejs_engine

    height = args.height
    width = round(height * 9 / 16 / 2) * 2                       # 9:16, even
    frames = int(args.seconds * args.fps)
    theme = load_theme("k70")

    world, usa = geo_data.borders(geo_data.WORLD_URL, only="United States of America")
    _, germany = geo_data.borders(geo_data.WORLD_URL, only="Germany")
    usa_lon, usa_lat = geo_data.centroid(usa)
    ger_lon, ger_lat = geo_data.centroid(germany)

    payload = {
        "id": "geo_preview_usd_eur",
        "template": "globe_flight", "width": width, "height": height,
        "fps": args.fps, "frames": frames, "seed": 11,
        "title": "", "label": "",
        "values": [], "labels": [],
        "palette": theme.palette, "fontFamily": theme.display.name,
        "world": world,
        "regions": [
            {"rings": usa, "label": "USD", "lon": usa_lon, "lat": usa_lat,
             "tone": "primary"},
            {"rings": germany, "label": "EUR", "lon": ger_lon, "lat": ger_lat,
             "tone": "secondary"},
        ],
        "route": {"from": [usa_lon, usa_lat], "to": [ger_lon, ger_lat],
                  "fromLabel": "USD", "toLabel": "EUR"},
        # ONE unbroken move. The mid-Atlantic leg exists so the camera pulls back
        # while the route draws — the hand-off reads as travel, not as a cut.
        "flight": [
            {"lon": -48.0, "lat": 34.0, "altitude": 4.30, "hold": 1.0},
            {"lon": usa_lon, "lat": usa_lat, "altitude": 1.55, "hold": 1.3},
            {"lon": -42.0, "lat": 46.0, "altitude": 2.70, "hold": 1.2},
            {"lon": ger_lon, "lat": ger_lat, "altitude": 1.22, "hold": 1.4},
        ],
    }
    key = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()[:24]
    out_dir = ROOT / "data" / "previews" / f"geo_{key}"
    (out_dir / "frames").mkdir(parents=True, exist_ok=True)
    payload["outputDir"] = str(out_dir / "frames")
    output = out_dir / "geo_preview.mp4"

    print(f"   target : {width}x{height} · {frames} frames · {args.seconds}s")
    print(f"   USA    : ({usa_lon:.1f}, {usa_lat:.1f})   Germany: ({ger_lon:.1f}, {ger_lat:.1f})")

    started = time.perf_counter()
    engine, rss = "threejs", 0.0
    try:
        if args.force_2d:
            raise RuntimeError("2D forced by flag")
        result = await threejs_engine._worker_render(payload)
        rss = float(result.get("rssMb", 0))
        await threejs_engine._encode(out_dir / "frames", args.fps, output)
    except Exception as error:                      # noqa: BLE001 — this IS the fallback
        print(f"   ⚠ 3D unavailable ({type(error).__name__}: {str(error)[:120]}) → 2D map")
        engine = "fallback_2d"
        sys.path.insert(0, str(ROOT / "scripts"))
        from render_geo_prototype import fallback_2d
        payload.setdefault("highlight", payload["regions"][0]["rings"])
        payload.setdefault("focus", payload["regions"][1]["rings"])
        fallback_2d(payload, output)
    render_s = time.perf_counter() - started
    await threejs_engine.close_worker()

    # Contact sheet at the four beats of the move, for eyeballing in one image.
    sheet = out_dir / "contact_sheet.jpg"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(output),
                    "-vf", f"select='not(mod(n\\,{max(1, frames // 4)}))',scale=360:-1,tile=4x1",
                    "-frames:v", "1", "-q:v", "3", "-y", str(sheet)], check=False)
    for label, at in (("a_world", 0.10), ("b_usa", 0.35), ("c_route", 0.62), ("d_germany", 0.92)):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss",
                        f"{args.seconds * at:.2f}", "-i", str(output), "-frames:v", "1",
                        "-q:v", "2", "-y", str(out_dir / f"{label}.jpg")], check=False)

    print(f"\n   engine : {engine}")
    print(f"   render : {render_s:.1f}s · worker RSS {rss:.0f}MB · children peak {peak_child_rss_mb():.0f}MB")
    print(f"   preview: {output}")
    print(f"   sheet  : {sheet}")
    if render_s > 90:
        print("   ⚠ over the 90s budget — rerun with --force-2d for the flat map")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
