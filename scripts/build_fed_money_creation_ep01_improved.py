#!/usr/bin/env python3
"""K70 Fed Money Creation -- SURGICAL IMPROVEMENT PASS.

Reuses the ENTIRE existing production (data/jobs/k70_fed_money_creation_ep01/)
as-is: same narration audio (locked, not resynthesized), same durations,
same music mix. Only 9 voxel shots (banned per this pass) get replaced with
non-voxel visuals matching their exact narration, plus 6 vector shots get
their overflowing labels shortened. Every other shot is copied byte-for-byte
from the existing *_final.mp4 (already duration-locked to narration).

    .venv-win/Scripts/python.exe scripts/build_fed_money_creation_ep01_improved.py
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
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import build_fed_money_creation_ep01 as orig  # reuse render_blender, frames_to_clip, fetch_real_footage, KIND_SCRIPT

OLD_JOB_DIR = ROOT / "data/jobs/k70_fed_money_creation_ep01"
JOB_DIR = ROOT / "data/jobs/k70_fed_money_creation_ep01_improved"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

# CRITICAL: orig.render_blender()/fetch_real_footage() write to the
# module-level SHOTS_DIR they were imported with (the ORIGINAL job's
# shots/ folder). Redirect it so replacement shots render into THIS
# job's directory instead -- otherwise this would silently overwrite
# the original, untouched production (e.g. clobber the old H3 voxel
# frames with new motion-graphics frames under the same tag).
orig.SHOTS_DIR = SHOTS_DIR

W, H, FPS = 1920, 1080, 24
XFADE_DUR = 0.5

# ==================================================================== #
# REPLACEMENTS for the 9 banned voxel shots -- each matched directly to
# its exact narration (see shot_changes.json for the full match record).
# ==================================================================== #

def eng(samples=28):
    return {"engine": "BLENDER_EEVEE_NEXT", "samples": samples, "width": W, "height": H}


VOXEL_REPLACEMENTS = {
    "H3": dict(kind="motion", n_frames=16,
        spec=dict(growth_stage=dict(milestones=[{"label": "?", "value_norm": 1.0, "f_grow": 24}]),
                 camera_keyframes=[{"frame": 0, "location": [0.0, -2.6, 1.0], "look_at": [0, 0.6, 0.4]},
                                  {"frame": 30, "location": [0.6, -1.4, 1.3], "look_at": [0.2, 0.6, 0.9]}],
                 lens=50, fstop=2.2, n_frames=16, frame_range=[0, 30], render=eng(28))),
    "S3": dict(kind="real_footage", terms=["computer screen banking app numbers data close up"]),
    "S5": dict(kind="real_footage", terms=["checking bank balance smartphone app hands"]),
    "S10": dict(kind="real_footage", terms=["bank exterior building entrance columns"]),
    "S18": dict(kind="real_footage", terms=["city street pedestrians walking crossing"]),
    "S19": dict(kind="motion", n_frames=16,
        spec=dict(growth_stage=dict(milestones=[{"label": "Loan Request", "value_norm": 0.9, "f_grow": 24}]),
                 camera_keyframes=[{"frame": 0, "location": [0.0, -2.6, 1.0], "look_at": [0, 0.6, 0.4]},
                                  {"frame": 30, "location": [0.7, -1.4, 1.3], "look_at": [0.3, 0.6, 0.9]}],
                 lens=50, fstop=2.2, n_frames=16, frame_range=[0, 30], render=eng(28))),
    "S21": dict(kind="motion", n_frames=14,
        spec=dict(growth_stage=dict(milestones=[{"label": "Money Engine", "value_norm": 1.0, "f_grow": 20}]),
                 camera_keyframes=[{"frame": 0, "location": [0.0, -2.4, 0.9], "look_at": [0, 0.4, 0.4]},
                                  {"frame": 26, "location": [0.6, -1.2, 1.2], "look_at": [0.2, 0.4, 0.8]}],
                 lens=50, fstop=2.2, n_frames=14, frame_range=[0, 26], render=eng(28))),
    "S38": dict(kind="real_footage", terms=["federal reserve building marble facade columns"]),
    "S40": dict(kind="real_footage", terms=["city skyline golden hour calm buildings"]),
}

# label-only fixes for overflowing vector shots -- everything else in
# their spec (camera, colors, timing) is untouched.
VECTOR_LABEL_FIXES = {
    "S13": {"RESERVE ACCOUNT": "RESERVES"},
    "S22": {"COMMERCIAL BANKS": "BANKS"},
    "S23": {"INTEREST RATES": "RATES"},
    "S26": {"BOND YIELDS": "YIELDS", "BOND PRICES": "PRICES"},
    "S30": {"RESERVES HELD": "RESERVES", "LOANS MADE": "LOANS"},
    "S37": {"COST OF BORROWING": "BORROWING"},
}


def build_improved_plan():
    plan = orig.build_segment_plan()
    changes = []
    for seg in plan:
        sid = seg["id"]
        if sid in VOXEL_REPLACEMENTS:
            old_kind = seg["kind"]
            repl = VOXEL_REPLACEMENTS[sid]
            changes.append({
                "shot_id": sid, "action": "REPLACE",
                "voiceover": seg["narration"], "meaning": seg["purpose"],
                "old_mode": old_kind, "new_mode": repl["kind"],
                "why": f"Voxel banned this pass; replaced with {repl['kind']} matching the exact narration.",
            })
            seg["kind"] = repl["kind"]
            seg.pop("spec", None)
            seg.pop("terms", None)
            if "spec" in repl:
                seg["spec"] = repl["spec"]
                seg["n_frames"] = repl["n_frames"]
            if "terms" in repl:
                seg["terms"] = repl["terms"]
        elif sid in VECTOR_LABEL_FIXES:
            fixes = VECTOR_LABEL_FIXES[sid]
            for bar in seg["spec"]["bars"]:
                if bar["label"] in fixes:
                    old_label = bar["label"]
                    bar["label"] = fixes[old_label]
            changes.append({
                "shot_id": sid, "action": "FIX",
                "voiceover": seg["narration"], "meaning": seg["purpose"],
                "old_mode": seg["kind"], "new_mode": seg["kind"],
                "why": f"Shortened overflowing label(s) {list(fixes.keys())} -> {list(fixes.values())}.",
            })
        else:
            changes.append({
                "shot_id": sid, "action": "KEEP",
                "voiceover": seg["narration"], "meaning": seg["purpose"],
                "old_mode": seg["kind"], "new_mode": seg["kind"],
                "why": "Already matches narration, no defect found.",
            })
    return plan, changes


def render_replacement(seg):
    """Render a replaced/fixed shot at its LOCKED duration (narration
    timing is frozen -- reuse the exact duration already baked into the
    existing audio mix, don't recompute it)."""
    tag = seg["id"]
    duration = seg["duration"]
    kind = seg["kind"]
    if kind == "real_footage":
        clip, _ = asyncio.run(orig.fetch_real_footage(seg["terms"], duration, tag))
        return clip
    script = orig.KIND_SCRIPT[kind]
    spec = json.loads(json.dumps(seg["spec"]))
    frames_dir = orig.render_blender(script, spec, tag)
    return orig.frames_to_clip(frames_dir, SHOTS_DIR / f"{tag}.mp4", spec["n_frames"], duration)


def main():
    t0 = time.time()
    print("K70 Fed Money Creation -- IMPROVEMENT PASS")
    plan, changes = build_improved_plan()

    clips = {}
    for seg in plan:
        sid = seg["id"]
        change = next(c for c in changes if c["shot_id"] == sid)
        if change["action"] == "KEEP":
            # Copy the existing duration-locked, narration-synced clip directly.
            src = OLD_JOB_DIR / "shots" / f"{sid}_final.mp4"
            dst = SHOTS_DIR / f"{sid}_final.mp4"
            shutil.copyfile(src, dst)
            clips[sid] = dst
            print(f"  [{sid}] KEEP -> copied existing clip")
        else:
            print(f"  [{sid}] {change['action']} ({change['old_mode']} -> {change['new_mode']})")
            raw_clip = render_replacement(seg)
            dst = SHOTS_DIR / f"{sid}_final.mp4"
            # Normalize to the LOCKED duration/fps, same as the original pipeline's tpad step.
            measured = orig.measure_duration(Path(raw_clip))
            pad = max(0.0, seg["duration"] - measured)
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(raw_clip), "-vf",
                 f"tpad=stop_mode=clone:stop_duration={pad:.2f}",
                 "-t", str(seg["duration"]), "-r", str(FPS), "-pix_fmt", "yuv420p", "-an", str(dst)],
                capture_output=True, text=True, check=True,
            )
            clips[sid] = dst

    # ---- Assemble video with xfade crossfades (same pattern as the original) ---- #
    order = [s["id"] for s in plan]
    durations = [s["duration"] for s in plan]
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
    final_video_duration = running_total
    print(f"  [assemble] video_only duration ~{final_video_duration:.2f}s")

    # ---- Audio: REUSE the existing mix untouched -- narration timing is locked ---- #
    final_audio = OLD_JOB_DIR / "audio_mix.mp3"
    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_only), "-i", str(final_audio),
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

    # ---- Contact sheet ---- #
    from PIL import Image
    n_thumbs = 12
    thumbs = []
    for i in range(n_thumbs):
        tt = final_video_duration * (i + 0.5) / n_thumbs
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

    # ---- shot_changes.json ---- #
    (JOB_DIR / "shot_changes.json").write_text(json.dumps(changes, indent=2), encoding="utf-8")

    total_time = round(time.time() - t0, 1)
    dur_actual = orig.measure_duration(final_mp4)
    print(f"\nFINAL: {final_mp4} ({dur_actual}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"SHOT CHANGES: {JOB_DIR / 'shot_changes.json'}")
    print(f"Total improvement time: {total_time}s")


if __name__ == "__main__":
    main()
