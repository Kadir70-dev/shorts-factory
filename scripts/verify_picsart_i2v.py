#!/usr/bin/env python3
"""
Picsart IMAGE-TO-VIDEO verification — proves the new opt-in cinematic-motion path
end-to-end WITHOUT a full render.

Flow exercised (the desired "IMAGE → VIDEO" branch):
  1. get a still  — generate one via the existing AI-image chain (ComfyUI →
     Google → HF → Pollinations), or pass --image to use a local file.
  2. animate it   — providers.picsart_image_to_video(still) → 3–5s clip.
  3. QA the clip  — ffprobe asserts it has a video stream and a 3–5s duration,
     and ffmpeg blackdetect asserts it is NOT an all-black frame.

    # generate a still + animate it (needs ENABLE_IMAGE_TO_VIDEO=1 + PICSART_API_KEY):
    .venv/bin/python scripts/verify_picsart_i2v.py

    .venv/bin/python scripts/verify_picsart_i2v.py --image data/cache/some.png
    .venv/bin/python scripts/verify_picsart_i2v.py --subject "watergate scandal, dark oval office"

Exit codes: 0 = clip verified · 2 = skipped (feature off / no key) · 1 = failure.
This is the QA-agent probe for the Picsart layer; it NEVER touches the rest of the
pipeline, so a red result here can't affect a normal (flag-off) render.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

BAR = "═" * 70


async def _ffprobe(path: str) -> dict:
    """Return {duration, has_video} for a media file via ffprobe (JSON)."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    data = json.loads(out or b"{}")
    streams = data.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    dur = float(data.get("format", {}).get("duration", 0) or 0)
    return {"duration": dur, "has_video": has_video}


async def _is_black(path: str) -> bool:
    """True if ffmpeg blackdetect flags (nearly) the WHOLE clip as black."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-i", path,
        "-vf", "blackdetect=d=0.5:pix_th=0.10", "-an", "-f", "null", "-",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    text = err.decode(errors="ignore")
    # blackdetect prints a line per black interval; any long interval ≈ dead clip.
    return "black_start:0" in text and "blackdetect" in text


async def _get_still(args) -> str:
    if args.image:
        p = Path(args.image)
        if not p.exists():
            print(f"   ✗ --image not found: {p}")
            sys.exit(1)
        print(f"   • using provided still: {p}")
        return str(p)
    # generate one through the existing AI-image chain.
    from app.pipeline.providers import ai_image_generate
    print(f"   • generating a still via the AI-image chain… subject={args.subject!r}")
    try:
        path = await ai_image_generate(args.subject, "vid_probe", "s_probe",
                                       category="history", seed=1)
        print(f"   ✓ still ready → {Path(path).name}")
        return path
    except Exception as e:  # noqa: BLE001
        print(f"   ✗ could not generate a still ({type(e).__name__}: {str(e)[:90]})")
        print("     pass --image <file> to test Picsart against a known image.")
        sys.exit(1)


async def main_async(args) -> int:
    from app.config import settings
    from app.pipeline.providers import (build_video_prompt,
                                        clamp_i2v_seconds,
                                        picsart_image_to_video)

    s = settings()
    print(f"{BAR}\nPICSART IMAGE-TO-VIDEO · verification\n{BAR}")
    print(f"   enable_image_to_video={s.enable_image_to_video} · "
          f"provider={s.ai_video_provider} · model={s.picsart_model} · "
          f"quality={s.picsart_quality}")

    if not s.enable_image_to_video:
        print("   it's OFF (ENABLE_IMAGE_TO_VIDEO=0). Set ENABLE_IMAGE_TO_VIDEO=1 "
              "to test the live path. SKIPPED.")
        return 2
    if not s.picsart_api_key:
        print("   no PICSART_API_KEY set. SKIPPED (the pipeline would fall back to "
              "the still + Ken Burns motion).")
        return 2

    still = await _get_still(args)
    prompt = build_video_prompt(args.subject)
    dur = clamp_i2v_seconds(args.length)
    print(f"   • Picsart image→video ({dur:.0f}s)… prompt={prompt[:70]!r}")
    try:
        clip = await picsart_image_to_video(still, prompt, dur,
                                            "vid_probe", "s_probe", seed=1)
    except Exception as e:  # noqa: BLE001
        print(f"   ✗ Picsart failed: {type(e).__name__}: {str(e)[:160]}")
        print("     (in the real pipeline this degrades to the still + Ken Burns.)")
        return 1

    info = await _ffprobe(clip)
    black = await _is_black(clip)
    print(f"\n   clip: {clip}")
    print(f"   has_video={info['has_video']} · duration={info['duration']:.2f}s "
          f"· black={black}")

    ok = True
    if not info["has_video"]:
        print("   ✗ no video stream"); ok = False
    if not (2.5 <= info["duration"] <= 5.6):
        print(f"   ✗ duration {info['duration']:.2f}s outside the 3–5s window"); ok = False
    if black:
        print("   ✗ clip looks all-black"); ok = False
    print(f"\n   {'✅ PICSART CLIP VERIFIED' if ok else '❌ verification FAILED'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="use this local still instead of generating one")
    ap.add_argument("--subject", default="watergate scandal cover-up, dark oval office, "
                    "cinematic documentary", help="subject for the still + motion prompt")
    ap.add_argument("--length", type=float, default=4.0, help="target clip seconds (3–5)")
    args = ap.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
