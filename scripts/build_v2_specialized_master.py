#!/usr/bin/env python3
"""K70 Visual Engine V2 -- SPECIALIZED 9-mode master (assembly-only).

Does NOT render anything new. Reuses:
  - 6 already-rendered shots from data/jobs/k70_v2_master_60s/shots/
    (voxel_open, real_footage, isometric, clay, motion_graphics, voxel_return)
  - 4 already-rendered SPECIALIZED-TOOL clips, one per gold benchmark job:
      vector       <- k70_v2_gold_vector_synfig/final.mp4   (real Synfig 1.5.5)
      collage      <- k70_v2_gold_collage_natron/final.mp4  (real Natron 2.5.0)
      sketch       <- k70_v2_gold_sketch_pencil2d/final.mp4 (real Pencil2D 0.7.2)
      illustrated_25d <- k70_v2_gold_25d/final.mp4           (real Krita 5.3.3 + Blender)
  - the already-synthesized narration lines from k70_v2_master_60s/audio/
  - the same music bed
  - NEW: foley/transition sfx from data/assets/sfx/ (not present in the prior master)

Two of the specialized clips don't match their beat's target duration and are
handled by trim/extend (no re-render, no engine touched):
  - sketch (pencil2d): native 2.0s -> extended to 6.0s via freeze-frame hold
  - illustrated_25d (krita+blender): native 10.0s -> trimmed to 6.0s (first 6s)

    .venv-win/Scripts/python.exe scripts/build_v2_specialized_master.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "data" / "jobs"
MASTER = JOBS / "k70_v2_master_60s"
SFX = ROOT / "data" / "assets" / "sfx"
MUSIC_BED = ROOT / "data" / "assets" / "music" / "beds" / "premium_a.wav"

JOB_DIR = JOBS / "k70_v2_specialized_master"
SHOTS_DIR = JOB_DIR / "shots"
AUDIO_DIR = JOB_DIR / "audio"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 24
XFADE_DUR = 0.5


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"cmd failed: {cmd}\nSTDOUT:{p.stdout[-2000:]}\nSTDERR:{p.stderr[-2000:]}")
    return p


PLAN = [
    dict(id="voxel_open", style="VOXEL_CINEMATIC", duration=10.0,
         purpose="Open the story like a movie: establish John and his world.",
         narration="Building your first one hundred thousand dollars can feel painfully slow.",
         reason="Story/character action -> Voxel is the hero storytelling mode per the brief.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 voxel_human rig",
         specialized_tool=False, source="k70_v2_master_60s/shots/voxel_open.mp4",
         src=MASTER / "shots" / "voxel_open.mp4", op="copy"),
    dict(id="real_footage", style="REAL_FOOTAGE", duration=6.0,
         purpose="Ground the story in the real world John actually lives in.",
         narration="Because before your money can grow, life gets paid first.",
         reason="Real-world evidence beat; motivated by a walking-city match-cut from the voxel street shot.",
         renderer="stock real-world footage (app.pipeline.broll)",
         specialized_tool=False, source="k70_v2_master_60s/shots/real_footage.mp4",
         src=MASTER / "shots" / "real_footage.mp4", op="copy"),
    dict(id="vector", style="PREMIUM_2D_VECTOR", duration=7.0,
         purpose="Explain where John's income actually goes.",
         narration="Income arrives. Rent, food, transport and bills take their share. What's left is small.",
         reason="Simple financial explanation -> Premium 2D Vector, per the brief's default mapping.",
         renderer="Synfig Studio 1.5.5 (real synfig.exe CLI, github.com/synfig/synfig)",
         specialized_tool=True, source="k70_v2_gold_vector_synfig/final.mp4",
         src=JOBS / "k70_v2_gold_vector_synfig" / "final.mp4", op="trim",
         note="native 7.041667s trimmed to 7.0s -- no re-render."),
    dict(id="isometric", style="ISOMETRIC_MINIATURE", duration=7.0,
         purpose="Zoom out from John's wallet to the whole economic system.",
         narration="Zoom out. John is one part of a bigger system -- money moving between employer, landlord, and bank.",
         reason="System/economy/money-flow beat -> Isometric Miniature, per the brief's default mapping.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 isometric economy system",
         specialized_tool=False, source="k70_v2_master_60s/shots/isometric.mp4",
         src=MASTER / "shots" / "isometric.mp4", op="copy"),
    dict(id="sketch", style="HAND_DRAWN_SKETCH", duration=6.0,
         purpose="Make the compounding math concrete and memorable.",
         narration="Ten thousand at eight percent is eight hundred a year. A hundred thousand -- eight thousand.",
         reason="Formula/complex concept -> Hand-drawn sketch, per the brief's default mapping.",
         renderer="Pencil2D 0.7.2 (real pencil2d.exe CLI export)",
         specialized_tool=True, source="k70_v2_gold_sketch_pencil2d/final.mp4",
         src=JOBS / "k70_v2_gold_sketch_pencil2d" / "final.mp4", op="extend",
         note="native asset is only 2.0s (4 drawn frames); held on the last frame "
              "(freeze-extend, no new drawing/re-render) to fill the 6.0s beat."),
    dict(id="clay", style="CLAY_MINIATURE", duration=6.0,
         purpose="Give compounding a physical, tactile feeling.",
         narration="Small savings barely move. But as the pile grows, each new addition gets bigger.",
         reason="Physical metaphor -> Clay/Miniature, per the brief's default mapping; the sketch's drawn "
               "dollar figure becomes this pile's first block (motivated transition, not a generic cut).",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 clay-material system",
         specialized_tool=False, source="k70_v2_master_60s/shots/clay.mp4",
         src=MASTER / "shots" / "clay.mp4", op="copy"),
    dict(id="collage", style="PAPER_COLLAGE", duration=6.0,
         purpose="Place John's story in a larger historical/editorial financial context.",
         narration="This isn't new. Markets, banks and paychecks have shaped families for generations.",
         reason="History/news/archival context -> Paper Collage, per the brief's default mapping.",
         renderer="Natron 2.5.0 (real NatronRenderer.exe, ReadOIIO->Transform->Merge->WriteOIIO graph)",
         specialized_tool=True, source="k70_v2_gold_collage_natron/final.mp4",
         src=JOBS / "k70_v2_gold_collage_natron" / "final.mp4", op="trim",
         note="native duration already exactly 6.0s -- normalized only (no re-render)."),
    dict(id="illustrated_25d", style="ILLUSTRATED_2_5D", duration=6.0,
         purpose="Return to John emotionally before the climax.",
         narration="For John, this was never just about numbers -- it's the house, the future.",
         reason="Emotional/abstract beat -> 2.5D Illustrated, per the brief's default mapping.",
         renderer="Krita 5.3.3 painted atmosphere layer composited into Blender 4.2.4 EEVEE_NEXT 2.5D scene",
         specialized_tool=True, source="k70_v2_gold_25d/final.mp4",
         src=JOBS / "k70_v2_gold_25d" / "final.mp4", op="trim",
         note="native 10.0s trimmed to first 6.0s to fit the beat -- no re-render."),
    dict(id="motion_graphics", style="3D_MOTION_GRAPHICS", duration=4.0,
         purpose="Deliver the climax: the milestone that changes everything.",
         narration="Ten. Twenty five. Fifty. Seventy five. One hundred thousand.",
         reason="Hard numbers made spatial/dimensional for maximum climax weight, not a flat text card.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 3D motion graphics system",
         specialized_tool=False, source="k70_v2_master_60s/shots/motion_graphics.mp4",
         src=MASTER / "shots" / "motion_graphics.mp4", op="copy"),
    dict(id="voxel_return", style="VOXEL_CINEMATIC", duration=4.0,
         purpose="Close the story where it opened -- same John, same world.",
         narration="The first hundred thousand is the hardest part.",
         reason="Return to the hero storytelling mode so every intermediate style reads as an explanation "
               "INSIDE John's story, not a separate video.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 voxel_human rig",
         specialized_tool=False, source="k70_v2_master_60s/shots/voxel_return.mp4",
         src=MASTER / "shots" / "voxel_return.mp4", op="copy"),
]


def normalize_clip(spec: dict) -> Path:
    out = SHOTS_DIR / f"{spec['id']}.mp4"
    src = spec["src"]
    dur = spec["duration"]
    if spec["op"] == "copy":
        shutil.copyfile(src, out)
    elif spec["op"] == "trim":
        run(["ffmpeg", "-y", "-i", str(src), "-t", str(dur), "-r", str(FPS),
             "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", "-an", str(out)])
    elif spec["op"] == "extend":
        run(["ffmpeg", "-y", "-i", str(src),
             "-vf", f"scale={W}:{H},tpad=stop_mode=clone:stop_duration={dur}",
             "-t", str(dur), "-r", str(FPS), "-pix_fmt", "yuv420p", "-an", str(out)])
    else:
        raise ValueError(spec["op"])
    print(f"  [{spec['id']}] {spec['op']} <- {src} -> {out}")
    return out


def main():
    t0 = time.time()
    print("K70 V2 SPECIALIZED MASTER -- assembly-only (no engines rebuilt)")

    clips = {s["id"]: normalize_clip(s) for s in PLAN}
    order = [s["id"] for s in PLAN]
    durations = [s["duration"] for s in PLAN]

    # ---- reuse narration audio verbatim (same beats/content/order) ---- #
    narration_paths = []
    for i in range(len(PLAN)):
        src = MASTER / "audio" / f"line_{i:02d}.wav"
        dst = AUDIO_DIR / f"line_{i:02d}.wav"
        shutil.copyfile(src, dst)
        narration_paths.append(dst)

    # ---- video: xfade chain ---- #
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
    run(["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex, "-map", "[vout]",
         "-pix_fmt", "yuv420p", "-r", str(FPS), str(video_only)])
    final_video_duration = running_total
    print(f"  [assemble] video_only duration ~{final_video_duration:.2f}s")

    # ---- narration + music offsets ---- #
    narr_offsets = []
    cum = 0.0
    for i, d_ in enumerate(durations):
        narr_offsets.append(cum)
        cum += d_ - (XFADE_DUR if i < len(durations) - 1 else 0)

    # ---- foley plan (new vs. the prior master, which had none) ---- #
    foley_events = []
    for i in range(1, len(order)):
        foley_events.append((SFX / "whoosh.wav", narr_offsets[i], 0.5, "transition whoosh"))
    motion_graphics_start = narr_offsets[order.index("motion_graphics")]
    foley_events.append((SFX / "riser.wav", max(0.0, motion_graphics_start - 1.0), 0.35, "climax riser"))
    foley_events.append((SFX / "bell.wav", motion_graphics_start + 1.5, 0.6, "$100K milestone accent"))
    voxel_return_start = narr_offsets[order.index("voxel_return")]
    foley_events.append((SFX / "pop.wav", voxel_return_start + 0.3, 0.4, "soft return accent"))

    # ---- audio mix: narration + music + foley ---- #
    audio_inputs = []
    audio_filter = []
    amix_labels = []
    idx = 0
    for i, p in enumerate(narration_paths):
        audio_inputs += ["-i", str(p)]
        lbl = f"n{idx}"
        delay_ms = int(max(0, narr_offsets[i]) * 1000)
        audio_filter.append(f"[{idx}:a]adelay=delays={delay_ms}:all=1,volume=1.6[{lbl}]")
        amix_labels.append(f"[{lbl}]")
        idx += 1
    for path, offset, vol, _label in foley_events:
        audio_inputs += ["-i", str(path)]
        lbl = f"f{idx}"
        delay_ms = int(max(0, offset) * 1000)
        audio_filter.append(f"[{idx}:a]adelay=delays={delay_ms}:all=1,volume={vol}[{lbl}]")
        amix_labels.append(f"[{lbl}]")
        idx += 1
    music_idx = idx
    audio_inputs += ["-stream_loop", "-1", "-i", str(MUSIC_BED)]
    audio_filter.append(f"[{music_idx}:a]atrim=0:{final_video_duration:.3f},volume=0.16[music]")
    amix_labels.append("[music]")
    audio_filter.append(f"{''.join(amix_labels)}amix=inputs={len(amix_labels)}:duration=longest:normalize=0[aout]")
    final_audio = JOB_DIR / "audio_mix.mp3"
    run(["ffmpeg", "-y", *audio_inputs, "-filter_complex", ";".join(audio_filter),
         "-map", "[aout]", "-t", f"{final_video_duration:.3f}", str(final_audio)])

    # ---- mux ---- #
    final_mp4 = JOB_DIR / "final.mp4"
    run(["ffmpeg", "-y", "-i", str(video_only), "-i", str(final_audio),
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_mp4)])

    # ---- contact sheet ---- #
    n_thumbs = 9
    thumbs = []
    for i in range(n_thumbs):
        t = final_video_duration * (i + 0.5) / n_thumbs
        tp = JOB_DIR / f"thumb_{i}.jpg"
        run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(final_mp4), "-vframes", "1", str(tp)])
        thumbs.append(Image.open(tp))
    cols, rows = 3, 3
    tw, th = 480, 270
    sheet = Image.new("RGB", (tw * cols, th * rows), (20, 20, 20))
    for i, im in enumerate(thumbs):
        sheet.paste(im.resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
    sheet.save(JOB_DIR / "contact_sheet.jpg", quality=92)

    # ---- comparison sheet: one representative frame per mode ---- #
    comp_thumbs = []
    for s in PLAN:
        clip = clips[s["id"]]
        tp = JOB_DIR / f"comp_{s['id']}.jpg"
        mid_t = s["duration"] / 2.0
        run(["ffmpeg", "-y", "-ss", f"{mid_t:.2f}", "-i", str(clip), "-vframes", "1", str(tp)])
        comp_thumbs.append(Image.open(tp))
    comp_cols = 5
    comp_rows = -(-len(comp_thumbs) // comp_cols)  # ceil div, fits all 10 modes (was hardcoded 3x3=9 -> dropped voxel_return)
    comp_sheet = Image.new("RGB", (tw * comp_cols, (th + 30) * comp_rows), (15, 15, 18))
    for i, im in enumerate(comp_thumbs):
        row, col = i // comp_cols, i % comp_cols
        comp_sheet.paste(im.resize((tw, th)), (col * tw, row * (th + 30)))
    comp_sheet.save(JOB_DIR / "comparison_sheet.jpg", quality=92)

    # ---- visual_director_decisions.json ---- #
    decisions = []
    for i, s in enumerate(PLAN):
        decisions.append({
            "beat": i + 1, "id": s["id"], "visual_mode": s["style"],
            "duration_sec": s["duration"], "semantic_purpose": s["purpose"],
            "selection_reason": s["reason"], "narration": s["narration"],
            "renderer": s["renderer"], "specialized_tool": s["specialized_tool"],
            "source_clip": s["source"], "assembly_note": s.get("note", "reused verbatim from k70_v2_master_60s"),
            "transition_from_previous": "hard cut (opening beat)" if i == 0 else f"{XFADE_DUR}s crossfade + whoosh foley",
        })
    (JOB_DIR / "visual_director_decisions.json").write_text(json.dumps(decisions, indent=2), encoding="utf-8")

    # ---- metadata.json ---- #
    total_build_time = round(time.time() - t0, 1)
    dur_actual = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(final_mp4)],
                                capture_output=True, text=True).stdout.strip()
    metadata = {
        "title": "Why The First $100,000 Feels Impossible -- K70 V2 SPECIALIZED Master",
        "resolution": f"{W}x{H}", "fps": FPS,
        "duration_sec": float(dur_actual) if dur_actual else None,
        "segments": [{"id": s["id"], "style": s["style"], "duration_sec": s["duration"],
                      "renderer": s["renderer"], "specialized_tool": s["specialized_tool"],
                      "source_clip": s["source"]} for s in PLAN],
        "modes_rendered": sorted(set(s["style"] for s in PLAN)),
        "specialized_tools_used": ["Synfig Studio 1.5.5", "Natron 2.5.0", "Pencil2D 0.7.2",
                                    "Krita 5.3.3 (+ Blender 4.2.4 EEVEE_NEXT compositing)"],
        "music_bed": str(MUSIC_BED),
        "foley_assets": sorted(set(str(p.name) for p, *_ in foley_events)),
        "narration_engine": "app.voice.manager.VoiceManager",
        "narration_source": "reused verbatim from data/jobs/k70_v2_master_60s/audio/ (same script, same beat order)",
        "assembly_method": "ffmpeg xfade concat of pre-rendered clips -- no rendering engine invoked in this build",
        "total_build_time_sec": total_build_time,
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur_actual}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"COMPARISON SHEET: {JOB_DIR / 'comparison_sheet.jpg'}")
    print(f"DECISIONS: {JOB_DIR / 'visual_director_decisions.json'}")
    print(f"METADATA: {JOB_DIR / 'metadata.json'}")
    print(f"Total build time: {total_build_time}s")


if __name__ == "__main__":
    main()
