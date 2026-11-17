"""
FFmpeg countdown renderer — 1080x1920, 30 fps, H.264 + AAC, CPU only.

Timeline:  hook teaser (#1 setup + "WAIT FOR #1")  →  #5 … #1  →  end card

Each part is rendered to an MKV intermediate (H.264 video + PCM audio) with
identical encode settings, so the final concat stream-copies the video and the
audio stays sample-accurate (no AAC priming drift between parts). The single
lossy audio encode happens in the finish pass together with the same EBU R128
-14 LUFS target app/pipeline/postprocess.py uses for the main pipeline.

Per clip: blurred cover background, the clip fitted and slowly pushed in, a
quick punch-in at the payoff, a white flash cut, the rank badge sliding in, the
caption fading in, and a soft synthetic whoosh under the cut.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from . import plates
from .plates import CAPTION_POS, H, W

FPS = 30
FG_MIN_H = 760          # 16:9 sources are cropped at the sides to this height
FG_MAX_H = 760          # non-portrait pictures never rise behind the title plate
FG_CENTER_Y = 900
TITLE_Y = 170
BADGE_POS = (60, 1200)
HOOK_Y = 1240
VENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS), "-bf", "2"]
AINT = ["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"]


def _ff(args: list[str], timeout: int = 1200) -> None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-800:]}")


def _frames(d: float) -> float:
    return round(d * FPS) / FPS


def _out(d: float) -> list[str]:
    """Exact frame count + exact audio length: parts concat with zero drift."""
    return ["-frames:v", str(round(d * FPS))]


def _samples(d: float) -> int:
    """Audio samples for a frame-aligned duration (1600 per frame at 48k/30)."""
    return round(d * FPS) * (48000 // FPS)


PAD = "tpad=stop_mode=clone:stop_duration=0.5,"


def fg_size(src_w: int, src_h: int) -> tuple[int, int]:
    """Foreground box. Portrait sources (taller than 4:3 upright) fill the
    frame. Everything else is a full-width band of FG_MIN_H, cover-cropped, so
    the picture keeps clear of the title plate whatever its aspect (a 4:3 or
    side-cropped compilation picture included)."""
    if src_h / src_w >= 1.34:
        return W, H
    h = round(W * src_h / src_w)
    h = min(FG_MAX_H, max(FG_MIN_H, h))
    return W, h - h % 2


def source_prefilter(part: dict, src_w: int, src_h: int) -> tuple[str, int, int]:
    """For clips cut from a ranking compilation: drop the source's title bars
    (crop to the live picture) and its burned-in rank graphic.

    A graphic hugging an edge of the picture is cropped away when that costs
    at most 20 % of the picture. Interpolating it out (delogo) leaves a visible
    smear there. Graphics elsewhere are removed with delogo.
    Returns (filter prefix, picture width, picture height)."""
    crop = part.get("crop") or ""
    cw, ch, cx, cy = ((int(v) for v in str(crop).split(":")) if crop
                      else (src_w, src_h, 0, 0))
    box = part.get("overlay_box")
    delogo = ""
    if box:
        x, y, bw, bh = (int(v) for v in box)
        sx, sy = 0.08 * cw, 0.08 * ch
        options = []                                  # (fraction lost, new crop)
        if x - cx < sx:                               # touches left edge
            cut = x + bw - cx
            options.append((cut / cw, (cw - cut, ch, cx + cut, cy)))
        if (cx + cw) - (x + bw) < sx:                 # right edge
            cut = cx + cw - x
            options.append((cut / cw, (cw - cut, ch, cx, cy)))
        if y - cy < sy:                               # top edge
            cut = y + bh - cy
            options.append((cut / ch, (cw, ch - cut, cx, cy + cut)))
        if (cy + ch) - (y + bh) < sy:                 # bottom edge
            cut = cy + ch - y
            options.append((cut / ch, (cw, ch - cut, cx, cy)))
        best = min(options, default=None)
        if best and best[0] <= 0.2:
            cw, ch, cx, cy = (int(v) // 2 * 2 for v in best[1])
        else:
            x, y = max(1, x), max(1, y)
            bw, bh = min(bw, src_w - x - 2), min(bh, src_h - y - 2)
            if bw > 4 and bh > 4:
                delogo = f"delogo=x={x}:y={y}:w={bw}:h={bh},"
    pre = delogo
    if (cw, ch) != (src_w, src_h):
        pre += f"crop={cw}:{ch}:{cx}:{cy},"
    return pre, cw, ch


def _video_chain(src_w: int, src_h: int, d: float, punch_at: float | None,
                 dim: float = 0.0, pre: str = "") -> tuple[str, int]:
    fw, fh = fg_size(src_w, src_h)
    z = f"(1+0.035*t/{d:.3f}"
    if punch_at is not None:
        z += f"+if(gte(t,{punch_at:.3f}),0.06*min(1,(t-{punch_at:.3f})/0.12),0)"
    z += ")"
    top = max(0, FG_CENTER_Y - fh // 2) if fh < H else 0
    chain = (
        # blur at quarter-res: same look, ~10x cheaper than a full-res boxblur
        f"[0:v]{pre}fps={FPS},split[s1][s2];"
        f"[s1]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
        f"boxblur=10:2,eq=brightness=-0.22:saturation=0.75,vignette=PI/4,"
        f"scale={W}:{H},setsar=1[bg];"
        f"[s2]scale={fw}:{fh}:force_original_aspect_ratio=increase,crop={fw}:{fh},"
        f"scale=w='trunc({fw}*{z}/2)*2':h=-2:eval=frame,"
        f"crop={fw}:{fh}:(iw-{fw})/2:(ih-{fh})/2,setsar=1"
        + (f",eq=brightness={-dim}" if dim else "") + "[fg];"
        f"[bg][fg]overlay=0:{top}:shortest=1" + _edge_shadow(top, fh) + "[base]"
    )
    return chain, top


def _edge_shadow(top: int, fh: int) -> str:
    """Graded dark bands just outside the clip's top/bottom edges."""
    if fh >= H:
        return ""
    out = ""
    for i, a in enumerate((0.55, 0.35, 0.18)):
        out += (f",drawbox=x=0:y={top - 6 * (i + 1)}:w={W}:h=6:color=black@{a}:t=fill"
                f",drawbox=x=0:y={top + fh + 6 * i}:w={W}:h=6:color=black@{a}:t=fill")
    return out


def _chime(work: Path) -> Path:
    """Original two-note end sting (sine partials, decaying) for the end card."""
    out = work / "chime.wav"
    if not out.exists():
        _ff(["-f", "lavfi", "-i", "sine=f=880:d=1.2:r=48000", "-f", "lavfi",
             "-i", "sine=f=1318.5:d=1.2:r=48000", "-filter_complex",
             "[1:a]adelay=110|110[b];[0:a][b]amix=inputs=2:normalize=0,"
             "afade=t=out:st=0.05:d=1.15,volume=0.22,aformat=channel_layouts=stereo",
             str(out)])
    return out


def _whoosh(work: Path) -> Path:
    out = work / "whoosh.wav"
    if not out.exists():
        _ff(["-f", "lavfi", "-i", "anoisesrc=d=0.35:c=pink:a=0.6:r=48000",
             "-af", "highpass=f=400,lowpass=f=5000,afade=t=in:d=0.08,"
                    "afade=t=out:st=0.12:d=0.23,volume=0.5", "-ac", "2", str(out)])
    return out


def _audio_chain(has_audio: bool, d: float, gain_db: float = 0.0) -> str:
    if has_audio:
        clip = (f"[0:a]aresample=48000,aformat=channel_layouts=stereo,"
                f"loudnorm=I=-16:TP=-2:LRA=11,aresample=48000,volume={gain_db}dB,"
                f"apad,atrim=0:{d:.3f},afade=t=in:d=0.03,"
                f"afade=t=out:st={max(0, d - 0.08):.3f}:d=0.08[ca];")
    else:
        clip = f"anullsrc=r=48000:cl=stereo,atrim=0:{d:.3f}[ca];"
    return clip + ("[ca][1:a]amix=inputs=2:duration=first:weights='1 0.45':normalize=0,"
                   f"apad,atrim=end_sample={_samples(d)}[a]")


def render_clip(part: dict, src: dict, plate_paths: dict, work: Path, out: Path) -> Path:
    d = _frames(part["out"] - part["in"])
    punch = round(d * 0.62, 3)
    pre, pw, ph = source_prefilter(part, src["width"], src["height"])
    vchain, _ = _video_chain(pw, ph, d, punch, pre=pre)
    bx, by = BADGE_POS
    cx, cy = CAPTION_POS
    graph = (
        vchain + ";"
        f"[base][2:v]overlay=0:{TITLE_Y}[t1];"
        # rank badge: ease-out-cubic slide in from the left edge over 0.3 s
        f"[t1][3:v]overlay=x='if(lt(t,0.3),-w+({bx}+w)*(1-pow(1-t/0.3,3)),{bx})':y={by}[t2];"
        f"[4:v]format=rgba,fade=t=in:st=0.22:d=0.18:alpha=1[cap];"
        f"[t2][cap]overlay={cx}:{cy}:shortest=1,"
        f"fade=t=in:st=0:d=0.14:color=white,{PAD}format=yuv420p[v];"
        + _audio_chain(src["has_audio"], d)
    )
    inputs = ["-ss", f"{part['in']:.3f}", "-t", f"{d + 0.2:.3f}", "-i", part["path"],
              "-i", str(_whoosh(work)),
              "-loop", "1", "-t", f"{d:.3f}", "-i", str(plate_paths["title"]),
              "-loop", "1", "-t", f"{d:.3f}", "-i", str(plate_paths[f"badge{part['rank']}"]),
              "-loop", "1", "-t", f"{d:.3f}", "-i", str(plate_paths[f"cap{part['rank']}"])]
    _ff([*inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
         *_out(d), *VENC, *AINT, str(out)])
    return out


def render_hook(part: dict, src: dict, plate_paths: dict, work: Path, d: float,
                out: Path) -> Path:
    d = _frames(d)
    pre, pw, ph = source_prefilter(part, src["width"], src["height"])
    vchain, _ = _video_chain(pw, ph, d, None, dim=0.08, pre=pre)
    graph = (vchain + ";"
             f"[base][2:v]overlay=0:{TITLE_Y}[t1];"
             f"[3:v]format=rgba,fade=t=in:st=0:d=0.12:alpha=1[hk];"
             f"[t1][hk]overlay=0:{HOOK_Y}:shortest=1,{PAD}format=yuv420p[v];"
             + _audio_chain(src["has_audio"], d, gain_db=-4))
    _ff(["-ss", f"{part['in']:.3f}", "-t", f"{d + 0.2:.3f}", "-i", part["path"],
         "-i", str(_whoosh(work)),
         "-loop", "1", "-t", f"{d:.3f}", "-i", str(plate_paths["title"]),
         "-loop", "1", "-t", f"{d:.3f}", "-i", str(plate_paths["hook"]),
         "-filter_complex", graph, "-map", "[v]", "-map", "[a]", *_out(d),
         *VENC, *AINT, str(out)])
    return out


def render_outro(last_part: Path, plate_paths: dict, work: Path, d: float,
                 out: Path) -> Path:
    d = _frames(d)
    still = work / "last_frame.png"
    _ff(["-sseof", "-0.1", "-i", str(last_part), "-frames:v", "1", "-update", "1", str(still)])
    graph = (f"[0:v]fps={FPS},scale=270:480,boxblur=6:2,scale={W}:{H},setsar=1[bg];"
             f"[2:v]format=rgba,fade=t=in:st=0:d=0.2:alpha=1[ec];"
             f"[bg][ec]overlay=0:0:shortest=1,"
             f"fade=t=out:st={d - 0.25:.3f}:d=0.25,{PAD}format=yuv420p[v];"
             f"anullsrc=r=48000:cl=stereo,atrim=0:{d:.3f}[sil];"
             f"[3:a]adelay=150|150[ch];"
             f"[sil][1:a][ch]amix=inputs=3:duration=first:normalize=0,"
             f"apad,atrim=end_sample={_samples(d)}[a]")
    _ff(["-loop", "1", "-t", f"{d:.3f}", "-i", str(still), "-i", str(_whoosh(work)),
         "-loop", "1", "-t", f"{d:.3f}", "-i", str(plate_paths["endcard"]),
         "-i", str(_chime(work)),
         "-filter_complex", graph, "-map", "[v]", "-map", "[a]", *_out(d),
         *VENC, *AINT, str(out)])
    return out


def _loudnorm_2pass(listing: Path, target: str = "I=-14:TP=-1.5:LRA=11") -> str:
    """Measure, then apply linear loudnorm — single-pass overshoots on 30 s
    content (measured -12.7 LUFS for a -14 target)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-f", "concat", "-safe", "0",
                        "-i", str(listing), "-vn", "-af",
                        f"loudnorm={target}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=600)
    try:
        m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
        return (f"loudnorm={target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                f"offset={m['target_offset']}:linear=true")
    except (ValueError, KeyError):
        return f"loudnorm={target}"


def build_plates(concept: dict, cfg: dict, work: Path) -> dict:
    tr = {k: v for k, v in concept["payload"].get("treatment", {}).items() if k != "name"}
    brand = {**cfg["brand"], **tr}
    copy = concept["payload"]["copy"]
    p = {"title": plates.title_plate(copy["title"], cfg.get("handle", ""), brand,
                                     work / "title.png"),
         "hook": plates.hook_plate(copy["hook"], brand, work / "hook.png"),
         "endcard": plates.endcard_plate(copy["outro"], "Follow for daily Top 5",
                                         brand, work / "endcard.png")}
    for r in concept["payload"]["ranks"]:
        p[f"badge{r['rank']}"] = plates.rank_badge(r["rank"], brand, work / f"badge{r['rank']}.png")
        p[f"cap{r['rank']}"] = plates.caption_plate(r["caption"], brand, work / f"cap{r['rank']}.png")
    return p


def render(concept: dict, sources: dict[int, dict], cfg: dict, out_dir: Path,
           draft: bool = False) -> dict:
    """Render an APPROVED concept. Returns a manifest describing the timeline.

    `draft=True` is the pre-approval review render: the same pipeline, but the
    deliverable is only a watermarked 540x960 `preview.mp4`. The caller deletes
    the full-resolution file after QA, so a draft can never be uploaded."""
    if not draft and (concept["status"] not in ("approved", "rendered")
                      or not concept.get("approved_by")):
        raise PermissionError(f"concept {concept['id']} is {concept['status']}; "
                              "approve it before rendering")
    t0 = time.monotonic()
    work = out_dir / f"concept_{concept['id']}"
    work.mkdir(parents=True, exist_ok=True)
    pay = concept["payload"]
    ranks = sorted(pay["ranks"], key=lambda r: -r["rank"])          # 5 → 1
    plate_paths = build_plates(concept, cfg, work)

    parts: list[tuple[str, Path, float]] = []
    top = next(r for r in ranks if r["rank"] == 1)
    hook = render_hook(top, sources[top["source_id"]], plate_paths, work,
                       pay["intro_s"], work / "p00_hook.mkv")
    parts.append(("hook", hook, _frames(pay["intro_s"])))
    for i, r in enumerate(ranks, start=1):
        clip = render_clip(r, sources[r["source_id"]], plate_paths, work,
                           work / f"p{i:02d}_rank{r['rank']}.mkv")
        parts.append((f"rank{r['rank']}", clip, _frames(r["out"] - r["in"])))
    outro = render_outro(parts[-1][1], plate_paths, work, pay["outro_s"],
                         work / "p99_outro.mkv")
    parts.append(("outro", outro, _frames(pay["outro_s"])))

    listing = work / "parts.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for _, p, _ in parts))
    final = work / "final.mp4"
    _ff(["-f", "concat", "-safe", "0", "-i", str(listing), "-c:v", "copy",
         "-af", f"{_loudnorm_2pass(listing)},aresample=48000:async=1,apad",
         "-shortest",
         "-c:a", "aac", "-profile:a", "aac_low", "-ar", "48000", "-b:a", "192k",
         "-movflags", "+faststart", str(final)])
    timeline, t = [], 0.0
    for name, _, d in parts:
        timeline.append({"part": name, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    thumb = work / "thumbnail.jpg"
    one = next(x for x in timeline if x["part"] == "rank1")
    _ff(["-ss", f"{one['start'] + (one['end'] - one['start']) * 0.7:.3f}", "-i", str(final),
         "-frames:v", "1", "-q:v", "2", str(thumb)])
    manifest = {"concept_id": concept["id"], "mp4": str(final), "thumbnail": str(thumb),
                "timeline": timeline, "render_seconds": round(time.monotonic() - t0, 1),
                "plates": {k: str(v) for k, v in plate_paths.items()},
                "layout": {"title_y": TITLE_Y, "badge": BADGE_POS, "caption": CAPTION_POS,
                           "hook_y": HOOK_Y}}
    manifest["preview_sheet"] = str(contact_sheet(final, timeline, work / "preview_sheet.png"))
    if draft:
        manifest["preview"] = str(watermark_preview(final, work / "preview.mp4"))
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def contact_sheet(mp4: Path, timeline: list[dict], out: Path) -> Path:
    """One frame per part (hook, #5…#1 at their payoff, end card), 4x2."""
    picks = []
    for p in timeline:
        frac = 0.5 if p["part"] in ("hook", "outro") else 0.75
        picks.append(p["start"] + (p["end"] - p["start"]) * frac)
    picks.insert(1, timeline[1]["start"] + 0.12)            # the flash cut into #5
    tmp = out.parent / "_sheet"
    tmp.mkdir(exist_ok=True)
    for i, t in enumerate(picks[:8]):
        _ff(["-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1", "-vf", "scale=270:480",
             str(tmp / f"f{i}.png")])
    _ff(["-i", str(tmp / "f%d.png"), "-vf", "tile=4x2:padding=6:color=0x222222",
         "-frames:v", "1", str(out)])
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    return out


def watermark_preview(mp4: Path, out: Path) -> Path:
    font = plates.FONT_DIR / "Anton-Regular.ttf"
    _ff(["-i", str(mp4), "-vf",
         f"scale=540:960,drawtext=fontfile='{font}':text='DRAFT - NOT APPROVED':"
         "fontsize=30:fontcolor=white@0.85:box=1:boxcolor=black@0.55:boxborderw=8:"
         "x=(w-tw)/2:y=h-150", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)])
    return out
