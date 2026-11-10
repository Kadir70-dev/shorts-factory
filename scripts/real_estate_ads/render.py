#!/usr/bin/env python3
"""Consent-gated, fact-locked 9:16 real-estate Reels composer.

Uses locally provided, appropriately licensed developer renders; never substitutes
unrelated stock or generated property images. FFmpeg, Pillow, Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT = next((Path(p) for p in (
    "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
) if Path(p).is_file()), None)
REGULAR = next((Path(p) for p in (
    "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
) if Path(p).is_file()), FONT)
WIDTH, HEIGHT, FPS = 1080, 1920, 30
BANNED = re.compile(r"(guaranteed\s+(?:return|rental|roi)|last\s+\d+\s+units|payment\s+plan\s+(?:verified|confirmed)|handover\s+(?:guaranteed|confirmed)|villa\s+from\s+aed\s*2[.,]?09\s*m)", re.I)


def font(size: int, regular: bool = False) -> ImageFont.FreeTypeFont:
    target = REGULAR if regular else FONT
    if not target:
        raise RuntimeError("Install the Lato or DejaVu Sans fonts to render captions")
    return ImageFont.truetype(str(target), size)


def validate(manifest: dict, duration: int, public: bool, permit: str, rights: bool, price: bool) -> list[dict]:
    if manifest.get("location") != "Um Fanain, Sharjah":
        raise ValueError("Location must be Um Fanain, Sharjah (not Dubai)")
    if manifest.get("developer") != "Azizi Developments":
        raise ValueError("Incorrect developer")
    if manifest.get("starting_price_aed") != 2090000:
        raise ValueError("Starting price must match verified broker page; reconfirm before paid release")
    if public and (not rights or not price or not permit.strip()):
        raise ValueError("Paid/public output blocked: confirm commercial render rights, current price, and applicable ad/permit ID")
    scenes = manifest.get("scenes", [])
    scenes = [s for s in scenes if duration in s.get("variants", [30])]
    if len(scenes) < 3 or sum(s["seconds"] for s in scenes) != duration:
        raise ValueError(f"Scene duration must equal {duration} seconds")
    for s in scenes:
        combined = " ".join(str(s.get(k, "")) for k in ("headline", "sub", "narration"))
        if BANNED.search(combined):
            raise ValueError("Prohibited or unsupported real-estate claim: " + combined)
        if not re.fullmatch(r"[\w-]+\.\w{3,5}", s.get("asset", "")):
            raise ValueError("Asset must be a simple filename inside the supplied assets directory")
    return scenes


def wrap_text(draw: ImageDraw.ImageDraw, text: str, text_font, max_width: int) -> list[str]:
    result = []
    for part in text.split("\n"):
        line = ""
        for word in part.split():
            attempt = f"{line} {word}".strip()
            if line and draw.textbbox((0, 0), attempt, font=text_font)[2] > max_width:
                result.append(line)
                line = word
            else:
                line = attempt
        result.append(line)
    return result


def card(scene: dict, output: Path, is_public: bool, permit: str, duration: int) -> None:
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    # Custom premium navy vignette below the image. Keep property details visible.
    for y in range(800, HEIGHT):
        intensity = (y - 800) / (HEIGHT - 800)
        alpha = int(210 * intensity ** 1.3)
        d.line([(0, y), (WIDTH, y)], fill=(7, 18, 39, alpha), width=1)
    d.rounded_rectangle((74, 116, 595, 176), 28, fill=(10, 22, 45, 195), outline=(186, 166, 126, 140), width=2)
    d.text((100, 131), "AUTOMAN STAR REAL ESTATE", font=font(25), fill="#F3E8CF")
    heading = scene["headline"].upper()
    lines = wrap_text(d, heading, font(78), 905)
    y = 1150 if len(lines) < 3 else 1050
    for line in lines:
        d.text((79, y), line, font=font(78), fill="#FFFFFF", stroke_width=1, stroke_fill="#0E1730")
        y += 98
    d.rectangle((80, y + 24, 193, y + 30), fill="#C8A86A")
    subfont = font(39, regular=True)
    if scene.get("price"):
        d.text((80, 1390), "Indicative project starting price*", font=font(33, True), fill="#F5E2BC")
    else:
        for line in wrap_text(d, scene.get("sub", ""), subfont, 890):
            d.text((80, y + 71), line, font=subfont, fill="#E8E4DC")
            y += 55
    footer_y = 1665
    d.text((80, footer_y), "Azizi Florence  |  Um Fanain, Sharjah", font=font(28, True), fill="#F8F0E5")
    d.text((80, footer_y + 43), "Developer renders · Illustrative · Subject to change", font=font(23, True), fill="#D9D0C2")
    if scene.get("price"):
        d.text((80, 1620), "*Current pricing and availability subject to confirmation", font=font(22, True), fill="#EEE2D2")
    if is_public:
        d.text((80, 1790), f"Ad / permit reference: {permit}", font=font(24, True), fill="#F4E3C3")
    else:
        d.rounded_rectangle((80, 1805, 1000, 1874), 12, fill=(129, 34, 42, 210))
        d.text((106, 1822), "DRAFT · NOT APPROVED FOR PAID AD DISTRIBUTION", font=font(24), fill="#FFFFFF")
    canvas.save(output)


def call(cmd: list[str]) -> None:
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError("FFmpeg failed:\n" + p.stderr[-6000:])


def render_scene(image: Path, overlay: Path, seconds: int, output: Path,
                 preview_scale: float, price: bool) -> None:
    w, h = int(WIDTH * preview_scale), int(HEIGHT * preview_scale)
    w -= w % 2
    h -= h % 2
    # Offline reproducible image video plus professional overlay fade-in.
    filters = (
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},setsar=1,zoompan=z='min(zoom+0.00065,1.13)':"
        f"d={seconds * FPS}:s={w}x{h}:fps={FPS},trim=duration={seconds},setpts=PTS-STARTPTS[bg];"
        f"[1:v]scale={w}:{h},format=rgba,fade=t=in:st=0:d=0.4:alpha=1[txt];"
        f"[bg][txt]overlay=shortest=1:format=auto,format=yuv420p[v]"
    )
    if price:
        # Numeric counter is a real animated expression, not an invented ROI chart.
        # Covers the first 1.5 sec and then holds the given price.
        color = "#F9E5B4"
        size = max(23, round(87 * preview_scale))
        y = int(1480 * preview_scale)
        filters += (f";[v]drawtext=fontfile={FONT}:"
                    "text='AED %{eif\\:min(2090000\\,t*2090000/1.5)\\:d}':"
                    f"fontcolor={color}:fontsize={size}:x=(w-text_w)/2:y={y}:"
                    "box=1:boxcolor=0x10203A@0.82:boxborderw=17:enable='lt(t\\,1.5)'[v1];"
                    f"[v1]drawtext=fontfile={FONT}:text='AED 2.09M':"
                    f"fontcolor={color}:fontsize={size}:x=(w-text_w)/2:y={y}:"
                    "box=1:boxcolor=0x10203A@0.82:boxborderw=17:enable='gte(t\\,1.5)'[out]")
        mapname = "[out]"
    else:
        mapname = "[v]"
    call(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
          "-loop", "1", "-framerate", str(FPS), "-i", str(image),
          "-loop", "1", "-framerate", str(FPS), "-i", str(overlay),
          "-filter_complex", filters, "-map", mapname, "-frames:v", str(seconds * FPS),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-r", str(FPS), str(output)])


def render(manifest: Path, assets: Path, output: Path, duration: int, public: bool,
           permit: str, rights: bool, price: bool, voiceover: Path | None,
           preview_scale: float) -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("Install FFmpeg and ffprobe")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    scenes = validate(data, duration, public, permit, rights, price)
    for scene in scenes:
        p = assets / scene["asset"]
        if not p.is_file():
            raise FileNotFoundError(f"Missing LICENSED project render: {p}. Do not substitute unrelated stock.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="realestate_reels_") as folder:
        temp = Path(folder)
        clips = []
        for idx, scene in enumerate(scenes, start=1):
            overlay = temp / f"card_{idx}.png"
            clip = temp / f"clip_{idx}.mp4"
            card(scene, overlay, public, permit, duration)
            render_scene(assets / scene["asset"], overlay, scene["seconds"], clip,
                         preview_scale, bool(scene.get("price")))
            clips.append(clip)
        concat = temp / "concat.txt"
        concat.write_text("".join(f"file '{x.as_posix()}'\n" for x in clips))
        joined = temp / "joined.mp4"
        call(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
              "-c", "copy", str(joined)])
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(joined)]
        if voiceover:
            if not voiceover.is_file():
                raise FileNotFoundError(voiceover)
            cmd += ["-i", str(voiceover), "-map", "0:v:0", "-map", "1:a:0", "-af", f"apad,atrim=duration={duration}", "-c:a", "aac", "-b:a", "160k"]
        else:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v:0", "-map", "1:a:0", "-t", str(duration), "-c:a", "aac", "-b:a", "128k"]
        cmd += ["-c:v", "copy", "-movflags", "+faststart", str(output)]
        call(cmd)
    print("Created", output, f"({duration}s, {int(preview_scale * WIDTH)}px target width)")
    print("Mode:", "PUBLIC-CREATIVE-READY; platform/legal review still required" if public else "DRAFT ONLY")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=ROOT / "examples" / "azizi-florence.json")
    p.add_argument("--assets-dir", type=Path, required=True, help="Local, commercially licensed developer renders")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--duration", type=int, choices=(15, 30), default=30)
    p.add_argument("--voiceover", type=Path)
    p.add_argument("--preview-scale", type=float, choices=(1.0, 0.5, 1 / 3), default=1.0)
    p.add_argument("--public", action="store_true", help="Remove DRAFT watermark; only for cleared ad creative")
    p.add_argument("--permit-id", default="")
    p.add_argument("--confirm-render-rights", action="store_true")
    p.add_argument("--confirm-current-price", action="store_true")
    a = p.parse_args()
    render(a.manifest, a.assets_dir, a.output, a.duration, a.public, a.permit_id,
           a.confirm_render_rights, a.confirm_current_price, a.voiceover, a.preview_scale)


if __name__ == "__main__":
    main()