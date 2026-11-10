#!/usr/bin/env python3
"""Consent-gated, fact-locked 9:16 real-estate Reels composer.

Images come only from the manifest's ``image_slots``. A slot with no supplied file is
PENDING_ASSET: drafts show a neutral "IMAGE PENDING" frame, public exports are blocked.
Never substitutes stock, placeholder property or synthetic images. FFmpeg, Pillow, Python 3.10+.
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
PENDING, APPROVED = "PENDING_ASSET", "APPROVED"
SLOT_STATUSES = {PENDING, "PROVIDED", APPROVED}
SLOT_KINDS = {"developer_render", "ai_generated"}
DISCLOSURE = {
    None: "IMAGE PENDING · Draft placeholder, no property image",
    "developer_render": "Developer render · Illustrative · Subject to change",
    "ai_generated": "AI-generated illustration · Not a photo of Azizi Florence",
}
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
    slots = manifest.get("image_slots")
    if not isinstance(slots, dict) or not slots:
        raise ValueError("Manifest needs an image_slots map")
    for slot_id, slot in slots.items():
        validate_slot(slot_id, slot)
    scenes = manifest.get("scenes", [])
    scenes = [s for s in scenes if duration in s.get("variants", [30])]
    if len(scenes) < 3 or sum(s["seconds"] for s in scenes) != duration:
        raise ValueError(f"Scene duration must equal {duration} seconds")
    for s in scenes:
        combined = " ".join(str(s.get(k, "")) for k in ("headline", "sub", "narration"))
        if BANNED.search(combined):
            raise ValueError("Prohibited or unsupported real-estate claim: " + combined)
        if s.get("slot") not in slots:
            raise ValueError(f"Scene references unknown image slot: {s.get('slot')!r}")
    if public:
        blockers = slot_blockers(slots, scenes)
        if blockers:
            raise ValueError("Paid/public output blocked by image slots:\n  " + "\n  ".join(blockers))
    return scenes


def validate_slot(slot_id: str, slot: dict) -> None:
    file = slot.get("file")
    if file is not None and not re.fullmatch(r"[\w-]+\.\w{3,5}", str(file)):
        raise ValueError(f"Slot {slot_id}: file must be a simple filename inside the supplied assets directory")
    if slot.get("kind") not in SLOT_KINDS | {None}:
        raise ValueError(f"Slot {slot_id}: kind must be one of {sorted(SLOT_KINDS)}")
    if slot.get("status") not in SLOT_STATUSES:
        raise ValueError(f"Slot {slot_id}: status must be one of {sorted(SLOT_STATUSES)}")
    if file is None and slot.get("status") != PENDING:
        raise ValueError(f"Slot {slot_id}: a slot without a file must stay {PENDING}")
    if file is not None and slot.get("kind") is None:
        raise ValueError(f"Slot {slot_id}: set kind (developer_render or ai_generated) when supplying a file")


def slot_blockers(slots: dict, scenes: list[dict]) -> list[str]:
    """Reasons the slots used by these scenes are not cleared for public export."""
    blockers = []
    for slot_id in dict.fromkeys(s["slot"] for s in scenes):
        slot = slots[slot_id]
        if slot.get("file") is None or slot.get("status") == PENDING:
            blockers.append(f"{slot_id}: {PENDING}")
            continue
        if slot.get("status") != APPROVED or not slot.get("approved"):
            blockers.append(f"{slot_id}: image not approved")
        if not slot.get("rights_cleared"):
            blockers.append(f"{slot_id}: rights not cleared")
        if slot.get("kind") == "ai_generated" and not slot.get("ai_disclosure"):
            blockers.append(f"{slot_id}: AI-generated image needs ai_disclosure=true")
    return blockers


def resolve_slot(slot: dict, assets: Path | None) -> Path | None:
    """Path of the supplied image, or None when the slot is still PENDING_ASSET."""
    if slot.get("file") is None or slot.get("status") == PENDING or assets is None:
        return None
    path = assets / slot["file"]
    return path if path.is_file() else None


def placeholder(slot_id: str, description: str, output: Path) -> None:
    """Neutral blank frame for a draft preview. Deliberately not a property image."""
    image = Image.new("RGB", (WIDTH, HEIGHT), "#3B3F45")
    d = ImageDraw.Draw(image)
    d.rectangle((60, 60, WIDTH - 60, 1000), outline="#6E737A", width=4)
    label = "IMAGE PENDING"
    w = d.textbbox((0, 0), label, font=font(84))[2]
    d.text(((WIDTH - w) // 2, 430), label, font=font(84), fill="#C9CCD1")
    for i, line in enumerate((f"slot: {slot_id}", description)):
        w = d.textbbox((0, 0), line, font=font(34, True))[2]
        d.text(((WIDTH - w) // 2, 560 + i * 52), line, font=font(34, True), fill="#9A9EA5")
    image.save(output)


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


def card(scene: dict, output: Path, is_public: bool, permit: str, duration: int,
         kind: str | None = None) -> None:
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
    d.text((80, footer_y + 43), DISCLOSURE[kind], font=font(23, True), fill="#D9D0C2")
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


def render(manifest: Path, assets: Path | None, output: Path, duration: int, public: bool,
           permit: str, rights: bool, price: bool, voiceover: Path | None,
           preview_scale: float) -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("Install FFmpeg and ffprobe")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    scenes = validate(data, duration, public, permit, rights, price)
    slots = data["image_slots"]
    images = {sid: resolve_slot(slots[sid], assets) for sid in dict.fromkeys(s["slot"] for s in scenes)}
    missing = [sid for sid, path in images.items() if path is None]
    if public and missing:
        raise FileNotFoundError("Public export blocked, image files not found for slots: " + ", ".join(missing))
    for sid, path in images.items():
        print(f"  slot {sid:<22} {PENDING if path is None else slots[sid]['status'] + ' ' + path.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="realestate_reels_") as folder:
        temp = Path(folder)
        clips = []
        for idx, scene in enumerate(scenes, start=1):
            overlay = temp / f"card_{idx}.png"
            clip = temp / f"clip_{idx}.mp4"
            image = images[scene["slot"]]
            if image is None:
                image = temp / f"pending_{scene['slot']}.png"
                if not image.exists():
                    placeholder(scene["slot"], slots[scene["slot"]].get("description", ""), image)
            kind = slots[scene["slot"]].get("kind") if images[scene["slot"]] else None
            card(scene, overlay, public, permit, duration, kind)
            render_scene(image, overlay, scene["seconds"], clip,
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
    if missing:
        print(f"{len(missing)} image slot(s) {PENDING}: draft shows IMAGE PENDING frames")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=ROOT / "examples" / "azizi-florence.json")
    p.add_argument("--assets-dir", type=Path, help="Folder holding the files named in image_slots; omit for an all-pending draft")
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