#!/usr/bin/env python3
"""K70 Fed Money Creation -- STRICT REAL FOOTAGE + 3D MOTION/CHART reset.

Only 4 shot types allowed: REAL_FOOTAGE, 3D_MOTION, ANIMATED_CHART, HYBRID.
Narration audio/timing LOCKED and reused untouched (learned from the last
pass's sync bug -- durations here are the exact narration-extended values
from the original scene_manifest.json, not re-guessed).

Reuses:
- 19 shots already compliant from the voxel-removal pass (13 real_footage
  + 6 motion) -- copied byte-for-byte, not re-rendered.
- eu.gmic/Blender motion_graphics_3d_script.py's proven growth_stage
  schema for both former-isometric "system flow" beats (as sequential,
  causally-ordered milestones -- the stack has no spatial flow-arrow
  primitive, so causality is expressed through TIMING, not movement;
  disclosed honestly, not hidden) and former-clay/sketch beats.
- _vector_2d_script.py's bar schema for former-vector shots, recategorized
  as ANIMATED_CHART, with a wider ortho_scale (7.0) to fix the overflow
  properly this time (root-caused: text width, not card width, was the
  actual overflow driver).
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import build_fed_money_creation_ep01 as orig

PREV_JOB_DIR = ROOT / "data/jobs/k70_fed_money_creation_ep01_improved"
ORIG_JOB_DIR = ROOT / "data/jobs/k70_fed_money_creation_ep01"
JOB_DIR = ROOT / "data/jobs/k70_fed_money_creation_ep01_v3"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)
orig.SHOTS_DIR = SHOTS_DIR  # redirect module-level writes into THIS job dir

W, H, FPS = 1920, 1080, 24
XFADE_DUR = 0.5


def eng(samples=28):
    return {"engine": "BLENDER_EEVEE_NEXT", "samples": samples, "width": W, "height": H}


def motion_spec(milestones, n_frames, cam_end_frame=None):
    fe = cam_end_frame or (n_frames * 2 - 2)
    return dict(
        growth_stage=dict(milestones=milestones),
        camera_keyframes=[{"frame": 0, "location": [0.0, -2.6, 1.0], "look_at": [0, 0.6, 0.4]},
                          {"frame": fe, "location": [0.6, -1.4, 1.3], "look_at": [0.2, 0.6, 0.9]}],
        lens=50, fstop=2.2, n_frames=n_frames, frame_range=[0, fe], render=eng(28),
    )


def chart_spec(bars, n_frames, ortho_scale=7.0, gesture_start=6, gesture_length=None):
    fe = n_frames * 2 + 6
    gl = gesture_length or (fe - 6)
    return dict(gesture_start=gesture_start, gesture_length=gl, push_in=True, ortho_scale=ortho_scale,
               bars=bars, n_frames=n_frames, frame_range=[0, fe], render=eng(32),
               # ANIMATED_CHART shots are pure data visualization -- no host
               # character. The "john" character this script draws by default
               # sits at world-center, exactly where bar labels are, and was
               # found hiding them (e.g. S16's "RESERVE ACCT" almost entirely
               # covered) in a QA pass on the first full render.
               show_character=False)


# ==================================================================== #
# 24 shots reclassified. Kind is always one of: real_footage, motion
# (3D_MOTION), vector (ANIMATED_CHART -- same renderer as before, just
# a different narrative role), or real_footage+overlay text for the one
# HYBRID shot (S39).
# ==================================================================== #

RECLASSIFY = {
    # ---- former isometric -> 3D_MOTION (sequential causal milestones) ---- #
    "S4": dict(kind="motion", n_frames=16, spec=motion_spec(
        [{"label": "Paycheck", "value_norm": 0.5, "f_grow": 12}, {"label": "Account Entry", "value_norm": 1.0, "f_grow": 26}], 16)),
    "S8": dict(kind="motion", n_frames=16, spec=motion_spec(
        [{"label": "Bank Account", "value_norm": 0.6, "f_grow": 12}, {"label": "Fed Account", "value_norm": 1.0, "f_grow": 26}], 16)),
    "S9": dict(kind="motion", n_frames=16, spec=motion_spec(
        [{"label": "Bank A Reserves", "value_norm": 0.9, "f_grow": 12}, {"label": "Bank B Reserves", "value_norm": 0.9, "f_grow": 26}], 16)),
    "S15": dict(kind="motion", n_frames=16, spec=motion_spec(
        [{"label": "Treasury Security", "value_norm": 0.7, "f_grow": 10}, {"label": "Reserves Created", "value_norm": 1.0, "f_grow": 26}], 16)),
    "S17": dict(kind="motion", n_frames=16, spec=motion_spec(
        [{"label": "Reserves", "value_norm": 0.8, "f_grow": 10}, {"label": "Interbank Settlement", "value_norm": 1.0, "f_grow": 26}], 16)),
    "S25": dict(kind="motion", n_frames=16, spec=motion_spec(
        [{"label": "Reserves (Massive Scale)", "value_norm": 1.0, "f_grow": 26}], 16)),
    "S27": dict(kind="motion", n_frames=16, spec=motion_spec(
        [{"label": "Bond Sale", "value_norm": 0.6, "f_grow": 10}, {"label": "Stocks / Real Estate", "value_norm": 1.0, "f_grow": 26}], 16)),
    "S31": dict(kind="motion", n_frames=16, spec=motion_spec(
        [{"label": "Reserves", "value_norm": 0.9, "f_grow": 10}, {"label": "Loan (If Demand)", "value_norm": 0.35, "f_grow": 26}], 16)),
    "S36": dict(kind="motion", n_frames=16, spec=motion_spec(
        [{"label": "Reserves Draining", "value_norm": 0.25, "f_grow": 26}], 16)),
    "S39": dict(kind="real_footage", terms=["city skyline financial district aerial buildings"],
               overlay_words=["RESERVES", "ASSETS", "LOANS"]),  # HYBRID: real footage + text overlay

    # ---- former vector -> ANIMATED_CHART (same renderer, wider margin) ---- #
    "S7": dict(kind="vector", spec=chart_spec(
        [{"label": "DEPOSITS", "h": 0.95, "color": [0.20, 0.55, 0.30]}, {"label": "CASH", "h": 0.10, "color": [0.75, 0.55, 0.28]},
         {"label": "COINS", "h": 0.05, "color": [0.6, 0.6, 0.62]}], 16)),
    "S13": dict(kind="vector", spec=chart_spec(
        [{"label": "CASH", "h": 0.12, "color": [0.75, 0.55, 0.28]}, {"label": "RESERVES", "h": 0.95, "color": [0.25, 0.45, 0.75]}], 16)),
    "S16": dict(kind="vector", spec=chart_spec(
        [{"label": "RESERVE ACCT", "h": 0.9, "color": [0.25, 0.45, 0.75]}], 14)),
    "S22": dict(kind="vector", spec=chart_spec(
        [{"label": "BANKS", "h": 0.95, "color": [0.20, 0.55, 0.30]}], 14)),
    "S23": dict(kind="vector", spec=chart_spec(
        [{"label": "RATES", "h": 0.08, "color": [0.6, 0.6, 0.62]}], 14)),
    "S26": dict(kind="vector", spec=chart_spec(
        [{"label": "YIELDS", "h": 0.15, "color": [0.65, 0.25, 0.22]}, {"label": "PRICES", "h": 0.9, "color": [0.20, 0.55, 0.30]}], 14)),
    "S30": dict(kind="vector", spec=chart_spec(
        [{"label": "RESERVES", "h": 0.9, "color": [0.25, 0.45, 0.75]}, {"label": "LOANS", "h": 0.25, "color": [0.6, 0.6, 0.62]}], 14)),
    "S35": dict(kind="vector", spec=chart_spec(
        [{"label": "2009-19", "h": 0.12, "color": [0.20, 0.55, 0.30]}, {"label": "2021-22", "h": 0.85, "color": [0.65, 0.25, 0.22]}], 14)),
    "S37": dict(kind="vector", spec=chart_spec(
        [{"label": "BORROWING", "h": 0.8, "color": [0.65, 0.25, 0.22]}], 14)),

    # ---- former sketch/collage/clay/2.5D ---- #
    "H2": dict(kind="vector", spec=chart_spec(
        [{"label": "MYTH", "h": 0.9, "color": [0.6, 0.3, 0.28]}, {"label": "REALITY", "h": 0.5, "color": [0.20, 0.55, 0.30]}], 14)),
    "S6": dict(kind="vector", spec=chart_spec(
        [{"label": "BALANCE", "h": 0.9, "color": [0.25, 0.45, 0.75]}, {"label": "PROMISE", "h": 0.9, "color": [0.6, 0.6, 0.62]}], 16)),
    "S14": dict(kind="real_footage", terms=["government bond certificate document financial paperwork"]),
    "S24": dict(kind="motion", n_frames=16, spec=motion_spec(
        [{"label": "Reserves (QE Scale)", "value_norm": 1.0, "f_grow": 26}], 16)),
    "S29": dict(kind="real_footage", terms=["everyday people shopping city street life"]),
}


def build_v3_plan():
    plan = orig.build_segment_plan()
    prev_changes = {c["shot_id"]: c for c in json.load(open(PREV_JOB_DIR / "shot_changes.json", encoding="utf-8"))}
    changes = []
    for seg in plan:
        sid = seg["id"]
        # The 9 voxel shots were already replaced (real_footage/motion) in
        # the prior pass -- reflect their TRUE current kind, not the stale
        # original-plan label, for accurate reporting/copying below.
        if sid in prev_changes and prev_changes[sid]["action"] == "REPLACE":
            seg["kind"] = "real_footage" if prev_changes[sid]["new_mode"] == "real_footage" else "motion"
        if sid in RECLASSIFY:
            r = RECLASSIFY[sid]
            old_kind_label = {"voxel": "VOXEL(banned)", "isometric": "ISOMETRIC(banned)", "vector": "VECTOR(banned)",
                             "sketch": "SKETCH(banned)", "collage": "COLLAGE(banned)", "clay": "CLAY(banned)",
                             "illustrated_25d": "2.5D(banned)"}.get(seg["kind"], seg["kind"])
            shot_type = "HYBRID_ANALYSIS" if "overlay_words" in r else (
                "ANIMATED_CHART" if r["kind"] == "vector" else
                ("3D_MOTION" if r["kind"] == "motion" else "REAL_FOOTAGE"))
            changes.append({
                "shot_id": sid, "shot_type": shot_type, "old_mode": old_kind_label,
                "voiceover_text": seg["narration"], "story_meaning": seg["purpose"],
                "why_it_matches_voiceover": r.get("why", "Direct visual match to the exact narration phrase."),
            })
            seg.pop("spec", None)
            seg.pop("terms", None)
            seg["kind"] = r["kind"]
            if "spec" in r:
                seg["spec"] = r["spec"]
                seg["n_frames"] = r.get("n_frames", r["spec"]["n_frames"])
            if "terms" in r:
                seg["terms"] = r["terms"]
            if "overlay_words" in r:
                seg["overlay_words"] = r["overlay_words"]
        else:
            shot_type = "REAL_FOOTAGE" if seg["kind"] == "real_footage" else "3D_MOTION"
            changes.append({
                "shot_id": sid, "shot_type": shot_type, "old_mode": seg["kind"],
                "voiceover_text": seg["narration"], "story_meaning": seg["purpose"],
                "why_it_matches_voiceover": "Already compliant (real footage or 3D motion) from the prior pass.",
            })
    return plan, changes


def render_shot(seg):
    tag = seg["id"]
    duration = seg["duration"]
    kind = seg["kind"]
    if kind == "real_footage":
        clip, _ = asyncio.run(orig.fetch_real_footage(seg["terms"], duration, tag))
        if "overlay_words" in seg:
            # ffmpeg's drawtext filter segfaults in this environment (broken
            # fontconfig -- crashes even with an explicit fontfile, confirmed
            # by direct repro). Render each word as a transparent PNG via PIL
            # (the same font files the rest of the brand text system uses)
            # and composite with `overlay`, which never touches fontconfig.
            from PIL import Image, ImageDraw, ImageFont
            words = seg["overlay_words"]
            n = len(words)
            seg_dur = duration / n
            font_path = ROOT / "config/brand/fonts/ArchivoBlack-Regular.ttf"
            font = ImageFont.truetype(str(font_path), 64)
            overlay_paths = []
            for i, w in enumerate(words):
                img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                bbox = draw.textbbox((0, 0), w, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                x, y = (W - tw) // 2, H - 180
                pad = 14
                draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad],
                               fill=(0, 0, 0, 89))  # black @ 0.35 alpha
                draw.text((x - bbox[0], y - bbox[1]), w, font=font, fill=(255, 255, 255, 255))
                png_path = SHOTS_DIR / f"{tag}_overlay_{i}.png"
                img.save(png_path)
                overlay_paths.append((png_path, i * seg_dur, (i + 1) * seg_dur))
            out = SHOTS_DIR / f"{tag}_overlay.mp4"
            inputs = ["-i", str(clip)]
            for png_path, _, _ in overlay_paths:
                inputs += ["-i", str(png_path)]
            filter_parts = []
            prev = "0:v"
            for i, (_, start, end) in enumerate(overlay_paths):
                out_label = f"ov{i}" if i < n - 1 else "vout"
                filter_parts.append(
                    f"[{prev}][{i + 1}:v]overlay=0:0:enable='between(t,{start:.2f},{end:.2f})'[{out_label}]")
                prev = out_label
            subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filter_parts),
                           "-map", "[vout]", "-map", "0:a?", "-c:a", "copy", str(out)],
                          capture_output=True, text=True, check=True)
            return out
        return clip
    script = orig.KIND_SCRIPT[kind]
    spec = json.loads(json.dumps(seg["spec"]))
    frames_dir = orig.render_blender(script, spec, tag)
    return orig.frames_to_clip(frames_dir, SHOTS_DIR / f"{tag}.mp4", spec["n_frames"], duration)


def main():
    t0 = time.time()
    print("K70 Fed Money Creation -- v3 STRICT REAL FOOTAGE + 3D ANALYSIS")
    plan, changes = build_v3_plan()
    manifest = json.load(open(ORIG_JOB_DIR / "scene_manifest.json", encoding="utf-8"))
    correct_dur = {s["shot_id"]: s["duration_sec"] for s in manifest}

    clips = {}
    for seg in plan:
        sid = seg["id"]
        seg["duration"] = correct_dur[sid]  # LOCKED narration-extended duration, learned from last pass's bug
        dst = SHOTS_DIR / f"{sid}_final.mp4"
        if dst.exists() and dst.stat().st_size:
            # Resume-safe: a prior interrupted run already produced this exact
            # final clip (same RECLASSIFY spec, same locked duration) -- reuse
            # it rather than re-copying or re-rendering completed work.
            clips[sid] = dst
            print(f"  [{sid}] SKIP (already rendered this pass)")
        elif sid not in RECLASSIFY:
            src = PREV_JOB_DIR / "shots" / f"{sid}_final.mp4"
            shutil.copyfile(src, dst)
            clips[sid] = dst
            print(f"  [{sid}] KEEP (already compliant) -> copied")
        else:
            print(f"  [{sid}] RENDER ({seg['kind']})")
            raw_clip = render_shot(seg)
            dst = SHOTS_DIR / f"{sid}_final.mp4"
            measured = orig.measure_duration(Path(raw_clip))
            pad = max(0.0, seg["duration"] - measured)
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(raw_clip), "-vf",
                 f"tpad=stop_mode=clone:stop_duration={pad:.2f}",
                 "-t", str(seg["duration"]), "-r", str(FPS), "-pix_fmt", "yuv420p", "-an", str(dst)],
                capture_output=True, text=True, check=True,
            )
            clips[sid] = dst

    order = [s["id"] for s in plan]
    durations = [correct_dur[sid] for sid in order]
    inputs = []
    for sid in order:
        inputs += ["-i", str(clips[sid])]
    filter_parts = []
    prev_label = "0:v"
    running_total = durations[0]
    for i in range(1, len(order)):
        out_label = f"v{i}" if i < len(order) - 1 else "vout"
        offset = running_total - XFADE_DUR
        filter_parts.append(
            f"[{prev_label}][{i}:v]xfade=transition=fade:duration={XFADE_DUR}:offset={offset:.3f}[{out_label}]")
        running_total = running_total + durations[i] - XFADE_DUR
        prev_label = out_label
    filter_complex = ";".join(filter_parts)
    video_only = JOB_DIR / "video_only.mp4"
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex, "-map", "[vout]",
         "-pix_fmt", "yuv420p", "-r", str(FPS), str(video_only)],
        capture_output=True, text=True, check=True,
    )
    print(f"  [assemble] video_only duration ~{running_total:.2f}s")

    final_audio = ORIG_JOB_DIR / "audio_mix.mp3"
    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_only), "-i", str(final_audio),
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

    from PIL import Image
    n_thumbs = 12
    thumbs = []
    for i in range(n_thumbs):
        tt = running_total * (i + 0.5) / n_thumbs
        tp = JOB_DIR / f"thumb_{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-ss", f"{tt:.2f}", "-i", str(final_mp4), "-vframes", "1", str(tp)],
                      capture_output=True, text=True)
        thumbs.append(Image.open(tp))
    cols, rows = 4, 3
    tw, th = 480, 270
    sheet = Image.new("RGB", (tw * cols, th * rows), (20, 20, 20))
    for i, im in enumerate(thumbs):
        sheet.paste(im.resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
    sheet.save(JOB_DIR / "contact_sheet.jpg", quality=92)

    for c in changes:
        c["start_time"] = None  # filled below
    cum = 0.0
    for i, sid in enumerate(order):
        c = next(x for x in changes if x["shot_id"] == sid)
        c["start_time"] = round(cum, 2)
        c["end_time"] = round(cum + durations[i], 2)
        cum += durations[i] - (XFADE_DUR if i < len(order) - 1 else 0)
    (JOB_DIR / "voiceover_manifest.json").write_text(json.dumps(changes, indent=2), encoding="utf-8")

    dur_actual = orig.measure_duration(final_mp4)
    total_time = round(time.time() - t0, 1)
    print(f"\nFINAL: {final_mp4} ({dur_actual}s)")
    print(f"Total time: {total_time}s")


if __name__ == "__main__":
    main()
