#!/usr/bin/env python3
"""Three-second real-footage + K70 newspaper-card sample.

Requires a rights-cleared local video. We do NOT ship stock footage, pretend
unknown media is licensed, or use fake newspaper logos/screenshots.

Example:
 python scripts/k70_finance_news_preview.py \
   --clip data/k70_usa_inflation_20261117/footage/pexels_29369224.mp4 \
   --clip-source https://www.pexels.com/video/woman-shopping-for-organic-potatoes-29369224/ \
   --license https://www.pexels.com/license/ \
   --out /tmp/k70_press_usa.mp4

Render stays local and never publishes anything.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.pipeline import dataviz_adv as A  # noqa: E402
from app.pipeline.dataviz_adv.core import FPS, new_layer  # noqa: E402

BLS_NEWS = "https://www.bls.gov/news.release/archives/cpi_07132022.htm"


def https_url(value: str) -> bool:
    x = urlparse(value)
    return x.scheme == "https" and bool(x.netloc) and not x.username and not x.password


def main() -> int:
    ap = argparse.ArgumentParser(description="K70 newspaper card on authentic licensed footage")
    ap.add_argument("--clip", type=Path, required=True, help="Local legally sourced MP4")
    ap.add_argument("--clip-source", required=True, help="Original page of that footage")
    ap.add_argument("--license", required=True, help="License / reuse permission URL")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--theme", choices=("aurora", "ocean", "sunset"), default="aurora")
    ap.add_argument("--headline", default="U.S. inflation hits 9.1% in June 2022")
    ap.add_argument("--publisher", default="U.S. Bureau of Labor Statistics")
    ap.add_argument("--date", default="2022-07-13", help="Date SOURCE was released")
    ap.add_argument("--source-url", default=BLS_NEWS)
    args = ap.parse_args()

    if not args.clip.is_file():
        ap.error(f"Footage missing: {args.clip}. Download/review rights first; no fake video fallback.")
    if not args.out.name.endswith(".mp4"):
        ap.error("Output filename must end in .mp4")
    if not https_url(args.clip_source) or not https_url(args.license):
        ap.error("Rights review requires HTTPS footage-source AND license URLs.")

    brief = A.NewsBrief(args.headline, args.publisher, args.date, args.source_url).validate()
    th = A.ChartTheme.load("k70_chart_" + args.theme)
    dur = 3.0
    frames = round(dur * FPS)

    def overlay(t: float):
        L = new_layer()
        A.draw_news_brief(L, th, brief, t, hold=dur)
        return L

    # All 90 frames: text fit/overlap gates BEFORE spending time on FFmpeg.
    issues = []
    for i in range(frames):
        t = i / FPS
        _, boxes = A.qa.draw_and_record(lambda lay, tt: A.draw_news_brief(lay, th, brief, tt, hold=dur), t)
        issues += [f"frame {i}: {issue}" for issue in A.qa.text_issues(boxes)]
        issues += [f"frame {i}: {issue}" for issue in A.qa.overlap_issues(
            boxes, ("press-headline", "press-source", "press-date", "press-topic", "press-brand")
        )]
    if issues:
        raise RuntimeError("Newspaper card QA failed: " + "; ".join(issues[:8]))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    A.compose.render_video(args.out, frames, [(args.clip, 0, dur)], overlay, A.compose.Bg("plain"), first_scene=True)
    probe = A.qa.probe(args.out)
    if probe["w"] != 1080 or probe["h"] != 1920 or abs(probe["fps"] - FPS) > 0.01 or probe["frames"] != frames:
        raise RuntimeError(f"Unexpected render format: {probe}")
    sidecar = args.out.with_suffix(".sources.json")
    sidecar.write_text(json.dumps({
        "type": "K70 original newspaper-style editorial card (NOT a media screenshot)",
        "news_summary": vars(brief), "video_clip": str(args.clip),
        "footage_page": args.clip_source, "footage_license": args.license,
        "rights": "Reconfirm original clip and depicted people/brands before publishing",
        "output": str(args.out), "render": probe,
    }, indent=2))
    print(f"OK: {args.out} | {frames} frames, verified layout, source sidecar {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
