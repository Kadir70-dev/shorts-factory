#!/usr/bin/env python3
"""K70 -- "How the Federal Reserve Actually Creates Money -- And Where It
Really Goes". Real 5-6 minute premium finance-explainer production,
1920x1080/24fps, built entirely from the EXISTING, proven K70 V2 stack
(see scripts/build_v2_master_60s.py, the direct precedent this follows:
per-style Blender subprocess render -> frames_to_clip -> independent
narration synthesis -> hand-built ffmpeg xfade/adelay/amix assembly).
No SceneGraph/VideoSpec/produce.py involvement -- confirmed via repo
audit that no V2 gold-style clip has ever been wired into that pipeline;
reusing THIS proven path is the lower-risk option.

The K70 VFX Director (tools/k70_scene_engine/vfx/, production-ready,
verified this session) is applied selectively on top of a subset of
rendered frame sequences before encoding, matching the requested
architecture: K70 Visual Scene -> K70 VFX Director -> FFmpeg -> Final Shot.

    .venv-win/Scripts/python.exe scripts/build_fed_money_creation_ep01.py [--preview]
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools/k70_scene_engine/vfx"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from vfx_director import apply_vfx  # noqa: E402

BLENDER = ROOT / "tools/k70_scene_engine/.blender_portable/blender-4.2.4-windows-x64/blender.exe"
BDIR = ROOT / "tools/k70_scene_engine/blender"
MUSIC_BED = ROOT / "data/assets/music/beds/documentary_a.wav"

JOB_DIR = ROOT / "data" / "jobs" / "k70_fed_money_creation_ep01"
SHOTS_DIR = JOB_DIR / "shots"
AUDIO_DIR = JOB_DIR / "audio"
VFX_DIR = JOB_DIR / "vfx"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
VFX_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 24
XFADE_DUR = 0.5

FALLBACK_LOG = []


def eng(samples=28):
    return {"engine": "BLENDER_EEVEE_NEXT", "samples": samples, "width": W, "height": H}


def render_blender(script_name, spec, tag, timeout=900):
    out_dir = SHOTS_DIR / tag
    spec["render"]["output_dir"] = str(out_dir)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(BDIR / script_name), "--", args_path],
        capture_output=True, text=True, timeout=timeout,
    )
    Path(args_path).unlink(missing_ok=True)
    if "_RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"segment {tag} failed:\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-2000:]}")
    print(f"  [{tag}] rendered -> {out_dir}")
    return out_dir


def frames_to_clip(frames_dir, out_mp4, n_frames, duration_sec, frame_glob="frame_%03d.png"):
    fps = n_frames / duration_sec
    tmp = out_mp4.with_suffix(".raw.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / frame_glob),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", str(tmp)],
        capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(tmp), "-t", str(duration_sec), "-r", str(FPS),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", "-an", str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    tmp.unlink(missing_ok=True)
    return out_mp4


async def fetch_real_footage(terms, duration_sec, tag):
    from app.pipeline import broll
    out = SHOTS_DIR / f"{tag}.mp4"
    path = await broll._video(terms, duration_sec, 0, query_text="", rank_key=f"k70_fed_ep01:{tag}")
    if path is None:
        path = await broll._image(terms, 0, query_text="", rank_key=f"k70_fed_ep01:{tag}_img")
        if path is None:
            raise RuntimeError(f"no real footage/image resolved for {tag} ({terms})")
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", str(path), "-t", str(duration_sec),
             "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                    f"zoompan=z='min(zoom+0.0015,1.08)':d=125:s={W}x{H}",
             "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)],
            capture_output=True, text=True, check=True,
        )
        return out, False
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-t", str(duration_sec),
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", str(out)],
        capture_output=True, text=True, check=True,
    )
    return out, True


def apply_vfx_to_frames(frames_dir, tag, n_frames, duration_sec, vfx):
    """K70 Visual Scene -> K70 VFX Director -> clip."""
    vfx_input = VFX_DIR / f"{tag}_input"
    vfx_input.mkdir(parents=True, exist_ok=True)
    frames = sorted(frames_dir.glob("frame_*.png"))
    for i, src in enumerate(frames):
        dst = vfx_input / f"frame_{i:04d}.png"
        if not dst.exists():
            shutil.copyfile(src, dst)
    result = apply_vfx(vfx_input, VFX_DIR / tag, preset=vfx["preset"], intensity=vfx.get("intensity", 0.65),
                       scene_type=vfx.get("scene_type", "city"), quality=vfx.get("quality", "MEDIUM"),
                       frame_count=len(frames), fps=max(1, round(len(frames) / duration_sec)),
                       width=W, height=H)
    out_mp4 = SHOTS_DIR / f"{tag}.mp4"
    fps = len(frames) / duration_sec
    tmp = out_mp4.with_suffix(".raw.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-i", result["final_path"], "-r", str(fps), str(tmp)],
        capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(tmp), "-t", str(duration_sec), "-r", str(FPS),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", "-an", str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    tmp.unlink(missing_ok=True)
    return out_mp4


async def synthesize_narration(lines):
    from app.voice.manager import VoiceManager
    voice = VoiceManager()
    try:
        voice.require_voice()
    except Exception as e:
        print(f"  [voice] unavailable, skipping narration: {e}")
        return [None] * len(lines)
    out_paths = []
    for i, ln in enumerate(lines):
        out = AUDIO_DIR / f"line_{i:02d}.wav"
        if out.exists() and out.stat().st_size > 0:
            out_paths.append(out)
            print(f"  [voice] line_{i:02d} already synthesized -> {out.name} (skipping)")
            continue
        try:
            await voice.synthesize(ln["narration"], out)
            out_paths.append(out)
            print(f"  [voice] line_{i:02d}: {ln['narration'][:50]!r} -> {out.name}")
        except Exception as e:
            print(f"  [voice] line_{i:02d} FAILED: {e}")
            out_paths.append(None)
    return out_paths


def measure_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                        capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


# ==================================================================== #
# SEGMENT PLAN
# ==================================================================== #

def build_segment_plan():
    segs = []

    def add(id_, kind, duration, narration, purpose, reason, **kw):
        d = dict(id=id_, kind=kind, duration=duration, narration=narration, purpose=purpose, reason=reason)
        d.update(kw)
        segs.append(d)

    # ---------------- HOOK ---------------- #
    add("H1", "real_footage", 7.0,
        "Every few years, someone says the Federal Reserve just prints trillions of dollars out of thin air.",
        "Cold open: establish gravity/scale of the institution.",
        "Real institutional exterior -> stock footage.",
        terms=["federal reserve building washington dc exterior columns"])

    add("H2", "sketch", 6.0,
        "It's a good story. It's also wrong.",
        "State and immediately puncture the myth.",
        "Quick conceptual negation -> hand-drawn sketch.",
        n_frames=14,
        spec=dict(lines=[{"text": "$$$ PRINTED?", "y": 0.3, "size": 0.4, "f_start": 2, "f_end": 20},
                        {"text": "NOT QUITE", "y": -0.3, "size": 0.4, "f_start": 24, "f_end": 44}],
                 ortho_scale=9.0, n_frames=14, frame_range=[0, 48], render=eng(32)))

    add("H3", "voxel", 7.0,
        "What the Fed actually does is stranger, more powerful, and much harder to picture -- "
        "because most of it never touches a printing press at all.",
        "Tease the real, quieter answer -- opens the John bookend.",
        "Character-anchored curiosity beat -> Voxel.",
        n_frames=16, vfx=dict(preset="dramatic_reveal", intensity=0.5, quality="LOW"),
        spec=dict(scene_type="apartment",
                 characters=[{"role": "john", "location": [0, -1.0, 0], "rotation_z_deg": 10,
                             "animation": {"type": "idle", "params": {"length": 30}}}],
                 camera_keyframes=[{"frame": 0, "location": [-2.2, -3.0, 1.5], "look_at": [0, -0.5, 1.0]},
                                  {"frame": 30, "location": [-1.6, -2.2, 1.4], "look_at": [0, -0.3, 1.0]}],
                 dof=True, fstop=2.5, lens=35, n_frames=16, frame_range=[0, 30], render=eng()))

    # ---------------- BEAT 1: physical vs digital money ---------------- #
    add("S1", "real_footage", 6.0,
        "Start with the cash in your wallet.",
        "Physical cash, tactile.", "Real currency -> stock footage.",
        terms=["dollar bills cash close up currency"])

    add("S2", "motion", 8.0,
        "Physical currency -- the paper bills with presidents on them -- makes up a small slice "
        "of the money in the economy.",
        "Cash (tiny) vs digital money (vast) contrast.",
        "Magnitude contrast -> 3D motion graphic milestones (reused schema).",
        n_frames=16,
        spec=dict(growth_stage=dict(milestones=[
                    {"label": "Physical Cash", "value_norm": 0.08, "f_grow": 8},
                    {"label": "Digital Money", "value_norm": 1.0, "f_grow": 28},
                ]),
                camera_keyframes=[{"frame": 0, "location": [0.0, -2.6, 1.0], "look_at": [0, 0.6, 0.4]},
                                 {"frame": 32, "location": [0.7, -1.4, 1.3], "look_at": [0.3, 0.6, 0.9]}],
                lens=50, fstop=2.2, n_frames=16, frame_range=[0, 32], render=eng(28)))

    add("S3", "voxel", 8.0,
        "The rest, the overwhelming majority, exists only as numbers in computer systems.",
        "Everyday digital-money moment (John, phone).",
        "Character-grounded digital-money beat -> Voxel.",
        n_frames=16,
        spec=dict(scene_type="street",
                 characters=[{"role": "john", "location": [0, -1.5, 0], "rotation_z_deg": 0,
                             "animation": {"type": "idle", "params": {"length": 32}}}],
                 camera_keyframes=[{"frame": 0, "location": [-2.0, -3.4, 1.4], "look_at": [0, -1.0, 0.9]},
                                  {"frame": 32, "location": [-1.2, -2.4, 1.3], "look_at": [0, -1.0, 0.9]}],
                 dof=True, fstop=2.2, lens=40, n_frames=16, frame_range=[0, 32], render=eng()))

    add("S4", "isometric", 7.0,
        "Your paycheck, your savings, your rent payment -- it's all entries in a database, "
        "moving from one account to another.",
        "Wide city money-flow network.",
        "System-flow beat -> Isometric Miniature.",
        n_frames=16,
        spec=dict(entities=[
                    {"name": "employer", "kind": "employer", "location": [-1.6, 1.2, 0]},
                    {"name": "worker", "kind": "worker", "location": [-1.6, -0.6, 0]},
                    {"name": "bank", "kind": "bank", "location": [0.2, 0.4, 0]},
                    {"name": "landlord", "kind": "business", "location": [1.6, -0.4, 0]},
                ],
                roads=[[-1.6, 0.6, -1.6, -0.2], [-1.0, 1.0, -0.2, 0.4], [0.6, 0.2, 1.0, -0.2]],
                flows=[
                    {"from": [-1.6, 1.5, 0.3], "to": [-1.6, -0.3, 0.15], "f_start": 4, "f_end": 20,
                     "color": [0.75, 0.6, 0.2]},
                    {"from": [-1.6, -0.3, 0.15], "to": [0.2, 0.7, 0.3], "f_start": 22, "f_end": 36,
                     "color": [0.2, 0.55, 0.28]},
                    {"from": [-1.6, -0.3, 0.15], "to": [1.6, -0.1, 0.3], "f_start": 22, "f_end": 40,
                     "color": [0.65, 0.25, 0.22]},
                ],
                lighting_preset="exterior_day", hdri_strength=1.0,
                yaw_deg=40, ortho_scale=6.2, look_at=[0, 0.2, 0.2], orbit_deg=14,
                n_frames=16, frame_range=[0, 40], render=eng(24)))

    # ---------------- BEAT 2: commercial-bank deposits ---------------- #
    add("S5", "voxel", 8.0,
        "When you check your balance at your bank, you're not looking at a pile of cash with your name on it.",
        "John inside a bank, checking phone balance.",
        "Character-in-bank beat -> Voxel.",
        n_frames=16,
        spec=dict(scene_type="bank", show_bank_facade=True,
                 characters=[{"role": "john", "location": [0, -1.2, 0], "rotation_z_deg": 0,
                             "animation": {"type": "idle", "params": {"length": 32}}}],
                 camera_keyframes=[{"frame": 0, "location": [-2.4, -3.0, 1.5], "look_at": [0, -0.6, 1.0]},
                                  {"frame": 32, "location": [-1.6, -2.2, 1.35], "look_at": [0, -0.6, 1.0]}],
                 dof=True, fstop=2.5, lens=35, n_frames=16, frame_range=[0, 32], render=eng()))

    add("S6", "sketch", 9.0,
        "You're looking at a liability -- a promise the bank owes you.",
        "Hand-drawn promise/IOU concept.",
        "Abstract financial concept -> hand-drawn sketch.",
        n_frames=16,
        spec=dict(lines=[{"text": "YOUR BALANCE", "y": 0.55, "size": 0.35, "f_start": 2, "f_end": 22},
                        {"text": "= A PROMISE", "y": -0.1, "size": 0.4, "f_start": 26, "f_end": 46},
                        {"text": "(NOT CASH)", "y": -0.65, "size": 0.3, "f_start": 48, "f_end": 60}],
                 ortho_scale=9.0, n_frames=16, frame_range=[0, 62], render=eng(32)))

    add("S7", "vector", 7.0,
        "That promise is what economists call a deposit, and deposits like these make up almost "
        "all of the money people actually spend, day to day.",
        "Deposits dwarf physical cash/coins.",
        "Simple financial comparison -> Premium 2D Vector bars.",
        n_frames=16,
        spec=dict(gesture_start=6, gesture_length=30, push_in=True, ortho_scale=4.6,
                 bars=[{"label": "DEPOSITS", "h": 0.95, "color": [0.20, 0.55, 0.30]},
                      {"label": "CASH", "h": 0.10, "color": [0.75, 0.55, 0.28]},
                      {"label": "COINS", "h": 0.05, "color": [0.6, 0.6, 0.62]}],
                 n_frames=16, frame_range=[0, 40], render=eng(32)))

    # ---------------- BEAT 3: bank reserves ---------------- #
    add("S8", "isometric", 8.0,
        "But banks themselves also have accounts -- not at each other, but at the Federal Reserve.",
        "Two commercial banks + a Federal Reserve tier.",
        "System-hierarchy beat -> Isometric Miniature.",
        n_frames=16,
        spec=dict(entities=[
                    {"name": "bank_a", "kind": "bank", "location": [-1.4, -0.6, 0]},
                    {"name": "bank_b", "kind": "bank", "location": [1.4, -0.6, 0]},
                    {"name": "federal_reserve", "kind": "bank", "location": [0.0, 1.4, 0]},
                ],
                roads=[[-1.4, 0.0, -0.4, 1.0], [1.4, 0.0, 0.4, 1.0]],
                flows=[{"from": [-1.4, -0.2, 0.3], "to": [-0.1, 1.2, 0.3], "f_start": 6, "f_end": 24,
                       "color": [0.6, 0.5, 0.2]},
                      {"from": [1.4, -0.2, 0.3], "to": [0.1, 1.2, 0.3], "f_start": 10, "f_end": 28,
                       "color": [0.6, 0.5, 0.2]}],
                lighting_preset="exterior_day", hdri_strength=1.0,
                yaw_deg=35, ortho_scale=5.8, look_at=[0, 0.4, 0.3], orbit_deg=12,
                n_frames=16, frame_range=[0, 32], render=eng(24)))

    add("S9", "isometric", 9.0,
        "These are called reserves. Banks use them to settle payments with one another, the "
        "way you'd use a checking account to settle up with a friend.",
        "Reserves settling between banks via the Fed tier.",
        "System-flow beat -> Isometric Miniature (variant).",
        n_frames=16,
        spec=dict(entities=[
                    {"name": "bank_a", "kind": "bank", "location": [-1.4, -0.6, 0]},
                    {"name": "bank_b", "kind": "bank", "location": [1.4, -0.6, 0]},
                    {"name": "federal_reserve", "kind": "bank", "location": [0.0, 1.4, 0]},
                ],
                roads=[[-1.4, 0.0, -0.4, 1.0], [1.4, 0.0, 0.4, 1.0]],
                flows=[{"from": [-0.1, 1.2, 0.3], "to": [1.4, -0.2, 0.3], "f_start": 6, "f_end": 24,
                       "color": [0.55, 0.42, 0.8]},
                      {"from": [0.1, 1.2, 0.3], "to": [-1.4, -0.2, 0.3], "f_start": 26, "f_end": 42,
                       "color": [0.55, 0.42, 0.8]}],
                lighting_preset="exterior_day", hdri_strength=1.0,
                yaw_deg=35, ortho_scale=5.8, look_at=[0, 0.4, 0.3], orbit_deg=-12,
                n_frames=16, frame_range=[0, 44], render=eng(24)))

    add("S10", "voxel", 7.0,
        "Reserves never leave the banking system. Ordinary people never touch them directly.",
        "Wide bank exterior, John small/distant.",
        "Grounding contrast beat -> Voxel wide.",
        n_frames=14,
        spec=dict(scene_type="bank", show_bank_facade=True,
                 characters=[{"role": "john", "location": [-2.5, -3.5, 0], "rotation_z_deg": 30,
                             "animation": {"type": "idle", "params": {"length": 28}}}],
                 camera_keyframes=[{"frame": 0, "location": [4.0, -6.0, 2.2], "look_at": [-0.5, -1.0, 1.0]},
                                  {"frame": 28, "location": [3.2, -5.0, 2.0], "look_at": [-0.5, -1.0, 1.0]}],
                 dof=True, fstop=3.2, lens=28, n_frames=14, frame_range=[0, 28], render=eng()))

    # ---------------- BEAT 4: what the Fed can create ---------------- #
    add("S11", "real_footage", 7.0,
        "Here's the part most people get wrong.",
        "Fed building, authoritative angle.",
        "Institutional gravity -> stock footage.",
        terms=["federal reserve seal marble columns washington"])

    add("S12", "motion", 9.0,
        "What the Fed creates is reserves, and physical currency. Creating reserves isn't "
        "printing anything. It's a keystroke.",
        "A single new-reserves milestone appearing.",
        "The key 'aha' moment -> 3D motion graphic, deserves VFX punch.",
        n_frames=16, vfx=dict(preset="dramatic_reveal", intensity=0.6, quality="MEDIUM"),
        spec=dict(growth_stage=dict(milestones=[{"label": "New Reserves", "value_norm": 1.0, "f_grow": 16}]),
                 camera_keyframes=[{"frame": 0, "location": [0.0, -2.4, 0.9], "look_at": [0, 0.4, 0.4]},
                                  {"frame": 30, "location": [0.6, -1.2, 1.2], "look_at": [0.2, 0.4, 0.8]}],
                 lens=50, fstop=2.2, n_frames=16, frame_range=[0, 30], render=eng(28)))

    add("S13", "vector", 8.0,
        "The Fed simply credits a number in a bank's account at the Fed. That's the entire mechanic.",
        "Physical cash vs bank reserves scale contrast.",
        "Magnitude comparison -> Premium 2D Vector.",
        n_frames=16,
        spec=dict(gesture_start=6, gesture_length=32, push_in=True, ortho_scale=4.6,
                 bars=[{"label": "PHYSICAL CASH", "h": 0.12, "color": [0.75, 0.55, 0.28]},
                      {"label": "BANK RESERVES", "h": 0.95, "color": [0.25, 0.45, 0.75]}],
                 n_frames=16, frame_range=[0, 40], render=eng(32)))

    # ---------------- BEAT 5: Fed buys Treasury securities ---------------- #
    add("S14", "collage", 8.0,
        "Say the Fed buys a government bond from a bank.",
        "Bond/document + money paper-cut tableau.",
        "Paperwork/financial-document imagery -> Paper Collage.",
        n_frames=14,
        spec=dict(stage=dict(f_bills=8, f_doc=20, f_house=999),
                 camera_keyframes=[{"frame": 0, "location": [0.5, -2.4, 1.5], "look_at": [0.2, 1.4, 1.0]},
                                  {"frame": 40, "location": [0.2, -1.8, 1.3], "look_at": [0.2, 1.3, 0.95]}],
                 lens=45, fstop=2.2, n_frames=14, frame_range=[0, 40], render=eng(28)))

    add("S15", "isometric", 9.0,
        "The Fed doesn't pay with cash from a vault. It credits that bank's reserve account with "
        "brand-new reserves.",
        "Bidirectional exchange: bond one way, reserves the other.",
        "Exchange mechanic -> Isometric Miniature dual flow.",
        n_frames=16,
        spec=dict(entities=[
                    {"name": "bank", "kind": "bank", "location": [-1.2, -0.4, 0]},
                    {"name": "federal_reserve", "kind": "bank", "location": [1.2, -0.4, 0]},
                ],
                roads=[[-1.2, 0.2, 1.2, 0.2]],
                flows=[{"from": [-0.9, -0.1, 0.3], "to": [0.9, -0.1, 0.3], "f_start": 4, "f_end": 22,
                       "color": [0.75, 0.6, 0.2]},
                      {"from": [0.9, -0.4, 0.3], "to": [-0.9, -0.4, 0.3], "f_start": 24, "f_end": 42,
                       "color": [0.55, 0.42, 0.8]}],
                lighting_preset="exterior_day", hdri_strength=1.0,
                yaw_deg=30, ortho_scale=5.2, look_at=[0, -0.2, 0.3], orbit_deg=10,
                n_frames=16, frame_range=[0, 44], render=eng(24)))

    add("S16", "vector", 7.0,
        "The bank hands over a bond; in exchange, its account at the Fed goes up. Nothing "
        "physical moves. A number changes.",
        "Reserve account number ticking up.",
        "Single-value beat -> Premium 2D Vector.",
        n_frames=14,
        spec=dict(gesture_start=4, gesture_length=26, push_in=True, ortho_scale=4.6,
                 bars=[{"label": "RESERVE ACCOUNT", "h": 0.9, "color": [0.25, 0.45, 0.75]}],
                 n_frames=14, frame_range=[0, 32], render=eng(32)))

    # ---------------- BEAT 6: reserves through the banking system ---------------- #
    add("S17", "isometric", 9.0,
        "Those reserves now sit inside the banking system, moving between banks as they settle "
        "transactions with each other.",
        "Full multi-bank network, flows crossing.",
        "Network/plumbing beat -> Isometric Miniature, widest network yet.",
        n_frames=16,
        spec=dict(entities=[
                    {"name": "bank_a", "kind": "bank", "location": [-1.8, 0.8, 0]},
                    {"name": "bank_b", "kind": "bank", "location": [1.8, 0.8, 0]},
                    {"name": "bank_c", "kind": "bank", "location": [0.0, -1.2, 0]},
                    {"name": "federal_reserve", "kind": "bank", "location": [0.0, 1.6, 0]},
                ],
                roads=[[-1.8, 0.2, 0.0, -0.6], [1.8, 0.2, 0.0, -0.6], [0.0, 1.0, 0.0, -0.6]],
                flows=[{"from": [-1.5, 0.6, 0.3], "to": [0.0, 1.4, 0.3], "f_start": 4, "f_end": 20,
                       "color": [0.6, 0.5, 0.2]},
                      {"from": [0.0, 1.4, 0.3], "to": [1.5, 0.6, 0.3], "f_start": 22, "f_end": 38,
                       "color": [0.6, 0.5, 0.2]},
                      {"from": [0.0, -1.0, 0.3], "to": [0.0, 1.2, 0.3], "f_start": 22, "f_end": 40,
                       "color": [0.55, 0.42, 0.8]}],
                lighting_preset="exterior_day", hdri_strength=1.0,
                yaw_deg=42, ortho_scale=6.6, look_at=[0, 0.4, 0.3], orbit_deg=18,
                n_frames=16, frame_range=[0, 42], render=eng(24)))

    add("S18", "voxel", 7.0,
        "They're the plumbing of the financial system -- essential, but mostly invisible, and "
        "mostly not what ends up in your pocket.",
        "Street-level pull-back, ordinary life unaware.",
        "Grounding beat -> Voxel street.",
        n_frames=14,
        spec=dict(scene_type="street",
                 characters=[{"role": "john", "location": [0, -1.8, 0], "rotation_z_deg": 15,
                             "animation": {"type": "walk", "params": {"length": 28, "n_cycles": 2,
                                                                     "stride_deg": 24, "forward_dist": 2.0}}}],
                 camera_keyframes=[{"frame": 0, "location": [-3.0, -4.5, 1.8], "look_at": [0, -1.0, 0.9]},
                                  {"frame": 28, "location": [-2.2, -3.2, 1.6], "look_at": [0, -1.0, 0.9]}],
                 dof=True, fstop=2.8, lens=35, n_frames=14, frame_range=[0, 28], render=eng()))

    # ---------------- BEAT 7: bank lending creates deposits ---------------- #
    add("S19", "voxel", 8.0,
        "So how does new money actually reach households and businesses? Mostly through lending.",
        "John reviewing loan paperwork inside a bank.",
        "Character-in-bank beat -> Voxel (no NPC interaction, per fallback policy).",
        n_frames=16,
        spec=dict(scene_type="bank", show_bank_facade=True,
                 characters=[{"role": "john", "location": [0, -0.8, 0], "rotation_z_deg": 0,
                             "animation": {"type": "idle", "params": {"length": 32}}}],
                 camera_keyframes=[{"frame": 0, "location": [-1.8, -2.6, 1.4], "look_at": [0, -0.4, 0.95]},
                                  {"frame": 32, "location": [-1.2, -1.9, 1.3], "look_at": [0, -0.4, 0.95]}],
                 dof=True, fstop=2.2, lens=40, n_frames=16, frame_range=[0, 32], render=eng()))

    add("S20", "motion", 9.0,
        "When a commercial bank approves your loan, it doesn't hand you reserves from a shelf. "
        "It creates a brand-new deposit in your account, on the spot. The loan and the deposit "
        "are created together, at the same moment.",
        "Loan and deposit growing simultaneously.",
        "Simultaneous-creation beat -> 3D motion graphic, the video's core insight.",
        n_frames=16,
        spec=dict(growth_stage=dict(milestones=[{"label": "Loan", "value_norm": 0.9, "f_grow": 18},
                                                {"label": "Deposit", "value_norm": 0.9, "f_grow": 18}]),
                 camera_keyframes=[{"frame": 0, "location": [0.0, -2.6, 1.0], "look_at": [0, 0.6, 0.4]},
                                  {"frame": 32, "location": [0.8, -1.4, 1.3], "look_at": [0.3, 0.6, 0.9]}],
                 lens=50, fstop=2.2, n_frames=16, frame_range=[0, 32], render=eng(28)))

    add("S21", "voxel", 7.0,
        "That is the real engine of everyday money creation.",
        "John using the new funds (storefront/street).",
        "Character-payoff beat -> Voxel.",
        n_frames=14,
        spec=dict(scene_type="street",
                 characters=[{"role": "john", "location": [0, -1.2, 0], "rotation_z_deg": -10,
                             "animation": {"type": "point", "params": {"length": 26}}}],
                 camera_keyframes=[{"frame": 0, "location": [-2.2, -3.0, 1.4], "look_at": [0, -0.4, 0.95]},
                                  {"frame": 26, "location": [-1.6, -2.3, 1.3], "look_at": [0, -0.4, 0.95]}],
                 dof=True, fstop=2.4, lens=35, n_frames=14, frame_range=[0, 26], render=eng()))

    add("S22", "vector", 6.0,
        "It's commercial banks, not the Fed, pulling the lever.",
        "Bold single-bar emphasis.",
        "Punchline beat -> Premium 2D Vector.",
        n_frames=14,
        spec=dict(gesture_start=4, gesture_length=24, push_in=True, ortho_scale=4.6,
                 bars=[{"label": "COMMERCIAL BANKS", "h": 0.95, "color": [0.20, 0.55, 0.30]}],
                 n_frames=14, frame_range=[0, 30], render=eng(32)))

    # ---------------- BEAT 8: quantitative easing ---------------- #
    add("S23", "vector", 8.0,
        "Sometimes the Fed wants to do more than adjust short-term interest rates. When rates "
        "are already near zero--",
        "Rates bar near the floor.",
        "Setup beat -> Premium 2D Vector.",
        n_frames=14,
        spec=dict(gesture_start=4, gesture_length=24, push_in=True, ortho_scale=4.6,
                 bars=[{"label": "INTEREST RATES", "h": 0.08, "color": [0.6, 0.6, 0.62]}],
                 n_frames=14, frame_range=[0, 30], render=eng(32)))

    add("S24", "clay", 9.0,
        "--it turns to quantitative easing: buying enormous quantities of longer-term bonds and "
        "mortgage-backed securities.",
        "Massive growing pile -- scale of QE.",
        "Physical-scale metaphor -> Clay/Miniature, growing pile at large n_blocks.",
        n_frames=16, vfx=dict(preset="dramatic_reveal", intensity=0.55, quality="MEDIUM"),
        spec=dict(growth_stage=dict(f_each=6, n_blocks=9),
                 camera_keyframes=[{"frame": 0, "location": [1.6, -1.6, 1.0], "look_at": [0, 0, 0.3]},
                                  {"frame": 60, "location": [1.1, -1.1, 1.15], "look_at": [0, 0, 0.5]}],
                 lens=60, fstop=2.0, n_frames=16, frame_range=[0, 60], render=eng(28)))

    add("S25", "isometric", 8.0,
        "Same mechanic as before, just at massive scale: trillions of dollars in new reserves, "
        "credited into the banking system.",
        "Many flows converging into the Fed/bank hub.",
        "Scale-of-QE beat -> Isometric Miniature, dense converging flows.",
        n_frames=16,
        spec=dict(entities=[
                    {"name": "federal_reserve", "kind": "bank", "location": [0.0, 1.2, 0]},
                    {"name": "bank_a", "kind": "bank", "location": [-1.6, -0.6, 0]},
                    {"name": "bank_b", "kind": "bank", "location": [1.6, -0.6, 0]},
                    {"name": "bank_c", "kind": "bank", "location": [0.0, -1.6, 0]},
                ],
                roads=[[-1.6, 0.0, 0.0, 0.8], [1.6, 0.0, 0.0, 0.8], [0.0, -1.0, 0.0, 0.8]],
                flows=[{"from": [-1.6, -0.2, 0.3], "to": [0.0, 1.0, 0.3], "f_start": 4, "f_end": 24,
                       "color": [0.6, 0.5, 0.2]},
                      {"from": [1.6, -0.2, 0.3], "to": [0.0, 1.0, 0.3], "f_start": 6, "f_end": 26,
                       "color": [0.6, 0.5, 0.2]},
                      {"from": [0.0, -1.2, 0.3], "to": [0.0, 1.0, 0.3], "f_start": 8, "f_end": 28,
                       "color": [0.6, 0.5, 0.2]}],
                lighting_preset="exterior_day", hdri_strength=1.0,
                yaw_deg=38, ortho_scale=6.2, look_at=[0, 0.2, 0.3], orbit_deg=16,
                n_frames=16, frame_range=[0, 30], render=eng(24)))

    # ---------------- BEAT 9: QE moves financial conditions and asset prices ---------------- #
    add("S26", "vector", 8.0,
        "When the Fed buys huge quantities of bonds, it pushes bond prices up and long-term "
        "yields down.",
        "Bond yields falling.",
        "Directional data beat -> Premium 2D Vector.",
        n_frames=14,
        spec=dict(gesture_start=4, gesture_length=24, push_in=True, ortho_scale=4.6,
                 bars=[{"label": "BOND YIELDS", "h": 0.15, "color": [0.65, 0.25, 0.22]},
                      {"label": "BOND PRICES", "h": 0.9, "color": [0.20, 0.55, 0.30]}],
                 n_frames=14, frame_range=[0, 30], render=eng(32)))

    add("S27", "isometric", 9.0,
        "Investors who sold those bonds look for the next-best place to put their money: stocks, "
        "corporate debt, real estate.",
        "Flows branching into investor/business/house nodes.",
        "Capital-reallocation beat -> Isometric Miniature.",
        n_frames=16,
        spec=dict(entities=[
                    {"name": "bank", "kind": "bank", "location": [0.0, 1.2, 0]},
                    {"name": "investor", "kind": "investor", "location": [-1.6, -0.6, 0]},
                    {"name": "business", "kind": "business", "location": [1.6, -0.6, 0]},
                    {"name": "house", "kind": "house", "location": [0.0, -1.8, 0]},
                ],
                roads=[[-1.6, 0.0, 0.0, 0.8], [1.6, 0.0, 0.0, 0.8], [0.0, -1.2, 0.0, 0.8]],
                flows=[{"from": [0.0, 1.0, 0.3], "to": [-1.6, -0.2, 0.3], "f_start": 4, "f_end": 22,
                       "color": [0.55, 0.42, 0.8]},
                      {"from": [0.0, 1.0, 0.3], "to": [1.6, -0.2, 0.3], "f_start": 6, "f_end": 24,
                       "color": [0.55, 0.42, 0.8]},
                      {"from": [0.0, 1.0, 0.3], "to": [0.0, -1.4, 0.3], "f_start": 8, "f_end": 26,
                       "color": [0.55, 0.42, 0.8]}],
                lighting_preset="exterior_day", hdri_strength=1.0,
                yaw_deg=36, ortho_scale=6.2, look_at=[0, 0.0, 0.3], orbit_deg=-14,
                n_frames=16, frame_range=[0, 28], render=eng(24)))

    add("S28", "real_footage", 8.0,
        "That's why quantitative easing tends to lift asset prices and lower the cost of "
        "borrowing across the economy.",
        "City skyline / financial district, prices rising mood.",
        "Asset-price beat -> stock footage, with wealth_growth VFX for a positive lift.",
        vfx=dict(preset="wealth_growth", intensity=0.6, quality="MEDIUM"),
        terms=["city skyline financial district stock market buildings"])

    add("S29", "illustrated_25d", 6.0,
        "Even for people who never think about the Fed at all.",
        "John, ordinary-life reflective moment.",
        "Character breather beat -> 2.5D Illustrated (stylistic variety, mid-video).",
        n_frames=14,
        spec=dict(gesture_start=6, gesture_length=30,
                 camera_keyframes=[{"frame": 0, "location": [0.2, -3.2, 1.3], "look_at": [0, 1.4, 1.0]},
                                  {"frame": 36, "location": [0.0, -2.7, 1.15], "look_at": [0, 1.2, 0.9]}],
                 lens=42, fstop=2.0, n_frames=14, frame_range=[0, 36], render=eng(28)))

    # ---------------- BEAT 10: not automatic consumer spending ---------------- #
    add("S30", "vector", 8.0,
        "New reserves don't automatically become spending. They sit on bank balance sheets.",
        "Reserves held (tall) vs loans made (short).",
        "Contrast beat -> Premium 2D Vector.",
        n_frames=14,
        spec=dict(gesture_start=4, gesture_length=24, push_in=True, ortho_scale=4.6,
                 bars=[{"label": "RESERVES HELD", "h": 0.9, "color": [0.25, 0.45, 0.75]},
                      {"label": "LOANS MADE", "h": 0.25, "color": [0.6, 0.6, 0.62]}],
                 n_frames=14, frame_range=[0, 30], render=eng(32)))

    add("S31", "isometric", 8.0,
        "Banks only turn them into loans if there's real demand to borrow, and real confidence to lend.",
        "A gated/stalled flow between bank and business.",
        "Conditional-flow beat -> Isometric Miniature, deliberately stalled motion.",
        n_frames=16,
        spec=dict(entities=[
                    {"name": "bank", "kind": "bank", "location": [-0.8, 0.4, 0]},
                    {"name": "business", "kind": "business", "location": [1.2, -0.6, 0]},
                ],
                roads=[[-0.8, -0.2, 1.2, -0.2]],
                flows=[{"from": [-0.6, 0.1, 0.3], "to": [0.0, -0.1, 0.3], "f_start": 6, "f_end": 16,
                       "color": [0.6, 0.6, 0.3]}],
                lighting_preset="exterior_day", hdri_strength=1.0,
                yaw_deg=32, ortho_scale=5.0, look_at=[0.0, -0.1, 0.3], orbit_deg=8,
                n_frames=16, frame_range=[0, 34], render=eng(24)))

    add("S32", "real_footage", 6.0,
        "A trillion dollars in reserves can sit there quietly for years, doing far less to prices "
        "at the checkout counter than people assume.",
        "Quiet grocery checkout counter.",
        "Restrained grounding beat -> stock footage, deliberately no VFX.",
        terms=["grocery store checkout counter customer paying"])

    # ---------------- BEAT 11: inflation nuance ---------------- #
    add("S33", "real_footage", 8.0,
        "After the 2008 crisis, the Fed created trillions in reserves through QE -- and inflation "
        "stayed low for a decade.",
        "Calm 2009-2019 office/city footage.",
        "Historical calm-period beat -> stock footage, restrained VFX.",
        vfx=dict(preset="clean_cinematic", intensity=0.4, quality="LOW"),
        terms=["office workers city calm 2010s business district"])

    add("S34", "real_footage", 9.0,
        "After 2020, a similar wave of stimulus met a very different economy: supply chains "
        "breaking down, demand surging back all at once. Inflation followed.",
        "Shipping/port congestion, supply-chain stress.",
        "Contrast crisis-period beat -> stock footage, market_crash VFX for stress mood.",
        vfx=dict(preset="market_crash", intensity=0.5, quality="MEDIUM"),
        terms=["shipping containers port congestion supply chain cargo"])

    add("S35", "vector", 6.0,
        "Same tool, different outcome -- because inflation depends on the whole economy, not the "
        "size of the Fed's balance sheet alone.",
        "2009-2019 vs 2021-2022 inflation comparison.",
        "Direct data comparison -> Premium 2D Vector.",
        n_frames=14,
        spec=dict(gesture_start=4, gesture_length=24, push_in=True, ortho_scale=4.6,
                 bars=[{"label": "2009-2019", "h": 0.12, "color": [0.20, 0.55, 0.30]},
                      {"label": "2021-2022", "h": 0.85, "color": [0.65, 0.25, 0.22]}],
                 n_frames=14, frame_range=[0, 30], render=eng(32)))

    # ---------------- BEAT 12: quantitative tightening ---------------- #
    add("S36", "isometric", 8.0,
        "The Fed can run this in reverse. Quantitative tightening lets its bond holdings mature "
        "without fully replacing them, quietly draining reserves back out of the system.",
        "Reserves draining back out (reversed flow).",
        "QT mirror-image beat -> Isometric Miniature, VFX night_city for a cooling mood.",
        n_frames=16, vfx=dict(preset="night_city", intensity=0.5, quality="MEDIUM"),
        spec=dict(entities=[
                    {"name": "bank", "kind": "bank", "location": [-1.2, -0.4, 0]},
                    {"name": "federal_reserve", "kind": "bank", "location": [1.2, -0.4, 0]},
                ],
                roads=[[-1.2, 0.2, 1.2, 0.2]],
                flows=[{"from": [-0.9, -0.1, 0.3], "to": [0.9, -0.1, 0.3], "f_start": 4, "f_end": 24,
                       "color": [0.55, 0.42, 0.8]}],
                lighting_preset="exterior_day", hdri_strength=0.8,
                yaw_deg=30, ortho_scale=5.2, look_at=[0, -0.2, 0.3], orbit_deg=-10,
                n_frames=16, frame_range=[0, 28], render=eng(24)))

    add("S37", "vector", 7.0,
        "Financial conditions tighten. Borrowing gets more expensive. It's QE's mirror image.",
        "Cost of borrowing rising.",
        "Closing-data beat -> Premium 2D Vector.",
        n_frames=14,
        spec=dict(gesture_start=4, gesture_length=24, push_in=True, ortho_scale=4.6,
                 bars=[{"label": "COST OF BORROWING", "h": 0.8, "color": [0.65, 0.25, 0.22]}],
                 n_frames=14, frame_range=[0, 30], render=eng(32)))

    # ---------------- BEAT 13: final summary ---------------- #
    add("S38", "voxel", 7.0,
        "So the Fed doesn't print unlimited money.",
        "John, calm confident return -- bookend.",
        "Character bookend close begins -> Voxel.",
        n_frames=14,
        spec=dict(scene_type="street",
                 characters=[{"role": "john", "location": [0, -1.2, 0], "rotation_z_deg": 0,
                             "animation": {"type": "idle", "params": {"length": 28}}}],
                 camera_keyframes=[{"frame": 0, "location": [-2.0, -3.0, 1.4], "look_at": [0, -0.3, 0.95]},
                                  {"frame": 28, "location": [-1.4, -2.2, 1.3], "look_at": [0, -0.3, 0.95]}],
                 dof=True, fstop=2.4, lens=40, n_frames=14, frame_range=[0, 28], render=eng()))

    add("S39", "isometric", 10.0,
        "It creates reserves -- a special, invisible form of money that lives only inside the "
        "banking system -- and uses them to buy assets and steer financial conditions. The money "
        "you actually spend is created mostly by commercial banks, one loan at a time, inside "
        "rules the Fed sets.",
        "Full-system hero shot: Fed + banks + city + all flows together.",
        "The one HERO-tier shot -- full system view earns the cost.",
        n_frames=20, vfx=dict(preset="economic_recovery", intensity=0.65, quality="HERO"),
        spec=dict(entities=[
                    {"name": "federal_reserve", "kind": "bank", "location": [0.0, 1.6, 0]},
                    {"name": "bank_a", "kind": "bank", "location": [-1.8, -0.2, 0]},
                    {"name": "bank_b", "kind": "bank", "location": [1.8, -0.2, 0]},
                    {"name": "business", "kind": "business", "location": [-0.9, -1.8, 0]},
                    {"name": "house", "kind": "house", "location": [0.9, -1.8, 0]},
                ],
                roads=[[-1.8, 0.2, 0.0, 1.0], [1.8, 0.2, 0.0, 1.0], [-1.8, -0.8, -0.9, -1.4],
                      [1.8, -0.8, 0.9, -1.4]],
                flows=[{"from": [-1.5, 0.0, 0.3], "to": [0.0, 1.4, 0.3], "f_start": 4, "f_end": 22,
                       "color": [0.6, 0.5, 0.2]},
                      {"from": [0.0, 1.4, 0.3], "to": [1.5, 0.0, 0.3], "f_start": 24, "f_end": 40,
                       "color": [0.6, 0.5, 0.2]},
                      {"from": [-1.5, -0.4, 0.3], "to": [-0.9, -1.6, 0.3], "f_start": 10, "f_end": 30,
                       "color": [0.2, 0.55, 0.28]},
                      {"from": [1.5, -0.4, 0.3], "to": [0.9, -1.6, 0.3], "f_start": 14, "f_end": 34,
                       "color": [0.2, 0.55, 0.28]}],
                lighting_preset="exterior_day", hdri_strength=1.05,
                yaw_deg=42, ortho_scale=7.4, look_at=[0, 0.1, 0.3], orbit_deg=22,
                n_frames=20, frame_range=[0, 42], render=eng(30)))

    add("S40", "voxel", 8.0,
        "Understanding that difference is the difference between fearing the Fed, and actually "
        "understanding it.",
        "Final calm shot of John, end-card close.",
        "Character bookend close -> Voxel.",
        n_frames=16, end_card="NOW YOU UNDERSTAND THE FED",
        spec=dict(scene_type="apartment",
                 characters=[{"role": "john", "location": [0, -1.0, 0], "rotation_z_deg": 5,
                             "animation": {"type": "idle", "params": {"length": 32}}}],
                 camera_keyframes=[{"frame": 0, "location": [-1.8, -2.6, 1.4], "look_at": [0, -0.4, 0.95]},
                                  {"frame": 32, "location": [-1.3, -2.0, 1.3], "look_at": [0, -0.4, 0.95]}],
                 dof=True, fstop=2.5, lens=35, n_frames=16, frame_range=[0, 32], render=eng()))

    return segs


KIND_SCRIPT = {
    "voxel": "_voxel_human_script.py",
    "vector": "_vector_2d_script.py",
    "isometric": "_isometric_miniature_script.py",
    "sketch": "_sketch_script.py",
    "clay": "_clay_miniature_script.py",
    "collage": "_paper_collage_script.py",
    "illustrated_25d": "_illustrated_25d_script.py",
    "motion": "_motion_graphics_3d_script.py",
}

# Representative subset spanning every style family + every VFX-treated
# shot (including the one HERO shot) -- the Phase-8 preview gate. Chosen
# so a pass/fail here is genuinely informative about the whole plan, not
# just a lucky easy shot.
PREVIEW_SHOT_IDS = ["H2", "H3", "S4", "S7", "S14", "S20", "S24", "S28", "S29", "S39"]


def _preview_spec(spec):
    """Render a few frames PAST the shot's nominal frame_range end (the
    fully-resolved composition, not mid-draw-in) at reduced samples --
    fast enough for a real preview-gate pass, still shows the actual
    composition/style/VFX look for judgment.

    Sampling frames INSIDE the original range (e.g. its last 3 frames)
    was tried first and is wrong for reveal-style content: confirmed via
    a real isolated test that the sketch style's Grease Pencil Build
    modifier is not fully settled 1-3 frames past its own frame_end --
    text rendered visibly mid-reveal ("$$$ |", "NOT Q") at frame_range[1],
    while rendering ~50 frames further out showed the complete, correctly
    laid out text ("$$$ PRINTED?", "NOT QUITE"). Camera keyframes and
    other per-shot animations hold their last value past their own final
    keyframe, so sampling well past the nominal end is safe for every
    style, not just sketch."""
    spec = json.loads(json.dumps(spec))  # deep copy
    fr = spec.get("frame_range", [0, spec.get("n_frames", 10)])
    settle_point = fr[1] + 50
    start = max(0, settle_point - 2)
    end = settle_point
    spec["frame_range"] = [start, end]
    spec["n_frames"] = end - start + 1
    if "render" in spec:
        spec["render"]["samples"] = min(spec["render"].get("samples", 28), 16)
    return spec


def render_segment(seg, preview=False):
    tag = seg["id"]
    duration = seg["duration"]
    kind = seg["kind"]

    # Resume-safety: if this shot's clip already exists (e.g. the build was
    # interrupted and relaunched), skip re-rendering it entirely rather
    # than discarding real progress. Preview mode always re-renders fresh
    # since it's meant to validate current code, not reuse old output.
    existing = SHOTS_DIR / f"{tag}.mp4"
    if not preview and existing.exists() and existing.stat().st_size > 0:
        print(f"  [{tag}] already rendered -> {existing} (skipping)")
        return existing

    if kind == "real_footage":
        clip, is_video = asyncio.run(fetch_real_footage(seg["terms"], duration, tag))
        seg["is_real_video"] = is_video
        if "vfx" in seg:
            # Real footage has no frame_XXXX.png sequence yet -- extract
            # one for the VFX Director, matching its expected input shape.
            frames_dir = SHOTS_DIR / f"{tag}_frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            n_frames = max(4, int(duration * 8))  # 8fps is plenty for a VFX pass on a mostly-static stock clip
            subprocess.run(["ffmpeg", "-y", "-i", str(clip), "-vf", f"fps={n_frames / duration}",
                           str(frames_dir / "frame_%04d.png")], capture_output=True, text=True, check=True)
            vfx = dict(seg["vfx"])
            if preview:
                vfx["quality"] = "LOW"
            return apply_vfx_to_frames(frames_dir, tag, n_frames, duration, vfx)
        return clip

    script = KIND_SCRIPT[kind]
    spec = json.loads(json.dumps(seg["spec"]))  # deep copy so preview mutation never touches the real plan
    if preview:
        spec = _preview_spec(spec)
    frames_dir = render_blender(script, spec, tag)
    n_frames = spec["n_frames"]

    if "vfx" in seg:
        vfx = dict(seg["vfx"])
        if preview:
            vfx["quality"] = "LOW"
        return apply_vfx_to_frames(frames_dir, tag, n_frames, duration, vfx)
    return frames_to_clip(frames_dir, SHOTS_DIR / f"{tag}.mp4", n_frames, duration)


def render_segment_with_fallback(seg, preview=False):
    try:
        return render_segment(seg, preview=preview)
    except Exception as e:
        print(f"  [{seg['id']}] PRIMARY RENDER FAILED ({seg['kind']}): {e}")
        FALLBACK_LOG.append({"id": seg["id"], "primary_kind": seg["kind"], "error": str(e)[:500],
                            "fallback": "real_footage generic finance b-roll"})
        fallback_terms = ["finance business abstract background city"]
        clip, is_video = asyncio.run(fetch_real_footage(fallback_terms, seg["duration"], f"{seg['id']}_fallback"))
        seg["is_real_video"] = is_video
        seg["fallback_used"] = True
        return clip


def main():
    preview = "--preview" in sys.argv
    t0 = time.time()
    print(f"K70 Fed Money Creation EP01 -- {'PREVIEW GATE' if preview else 'FULL PRODUCTION'}")
    plan = build_segment_plan()
    if preview:
        plan = [s for s in plan if s["id"] in PREVIEW_SHOT_IDS]
        print(f"  previewing {len(plan)} representative shots: {[s['id'] for s in plan]}")

    clips = {}
    for seg in plan:
        print(f"\n=== {seg['id']} ({seg['kind']}) ===")
        clips[seg["id"]] = render_segment_with_fallback(seg, preview=preview)
        seg["clip"] = str(clips[seg["id"]])

    if preview:
        # ---- Preview contact sheet: last frame of every previewed clip ---- #
        from PIL import Image, ImageDraw
        thumbs = []
        for seg in plan:
            tp = JOB_DIR / f"preview_{seg['id']}.jpg"
            subprocess.run(["ffmpeg", "-y", "-sseof", "-0.2", "-i", str(clips[seg["id"]]), "-vframes", "1",
                          str(tp)], capture_output=True, text=True)
            thumbs.append((seg["id"], seg["kind"], Image.open(tp)))
        cols = 5
        rows = (len(thumbs) + cols - 1) // cols
        tw, th = 384, 216
        sheet = Image.new("RGB", (tw * cols, (th + 24) * rows), (15, 15, 18))
        draw = ImageDraw.Draw(sheet)
        for i, (sid, kind, im) in enumerate(thumbs):
            r, c = i // cols, i % cols
            sheet.paste(im.resize((tw, th)), (c * tw, r * (th + 24) + 24))
            draw.text((c * tw + 6, r * (th + 24) + 4), f"{sid} ({kind})", fill=(255, 255, 255))
        sheet.save(JOB_DIR / "preview_contact_sheet.jpg", quality=92)
        print(f"\nPREVIEW CONTACT SHEET: {JOB_DIR / 'preview_contact_sheet.jpg'}")
        print(f"Preview time: {round(time.time() - t0, 1)}s")
        print(f"Fallbacks triggered: {len(FALLBACK_LOG)}")
        if FALLBACK_LOG:
            print(json.dumps(FALLBACK_LOG, indent=2))
        return

    # ---- FULL PRODUCTION: narration ---- #
    narration_paths = asyncio.run(synthesize_narration(plan))
    for s, p in zip(plan, narration_paths):
        s["narration_audio"] = str(p) if p else None

    # ---- Adjust durations to real measured narration length (avoid cutting narration) ---- #
    for s in plan:
        if s["narration_audio"]:
            measured = measure_duration(Path(s["narration_audio"]))
            if measured + 0.6 > s["duration"]:
                print(f"  [{s['id']}] extending duration {s['duration']:.1f}s -> {measured + 0.6:.1f}s "
                     f"to fit narration ({measured:.1f}s)")
                s["duration"] = round(measured + 0.6, 2)

    # Re-encode each clip to its (possibly extended) final duration.
    durations = [s["duration"] for s in plan]
    order = [s["id"] for s in plan]
    for s in plan:
        src = Path(s["clip"])
        final_clip = SHOTS_DIR / f"{s['id']}_final.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-vf",
             f"tpad=stop_mode=clone:stop_duration={max(0.0, s['duration'] - measure_duration(src)):.2f}",
             "-t", str(s["duration"]), "-r", str(FPS), "-pix_fmt", "yuv420p", "-an", str(final_clip)],
            capture_output=True, text=True, check=True,
        )
        clips[s["id"]] = final_clip

    # ---- Assemble video with xfade crossfades ---- #
    offsets = []
    cum = 0.0
    for i, d_ in enumerate(durations):
        cum += d_
        if i < len(durations) - 1:
            offsets.append(cum - XFADE_DUR * (i + 1))
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

    # ---- Audio: narration placed at segment starts + looped music bed + SFX ---- #
    narr_offsets = []
    cum = 0.0
    for i, d_ in enumerate(durations):
        narr_offsets.append(cum)
        cum += d_ - (XFADE_DUR if i < len(durations) - 1 else 0)
    audio_inputs = []
    audio_filter = []
    valid_idx = 0
    amix_labels = []
    for i, (s, off) in enumerate(zip(plan, narr_offsets)):
        if s["narration_audio"]:
            audio_inputs += ["-i", s["narration_audio"]]
            lbl = f"a{valid_idx}"
            delay_ms = int(max(0, off) * 1000)
            audio_filter.append(f"[{valid_idx}:a]adelay=delays={delay_ms}:all=1,volume=1.6[{lbl}]")
            amix_labels.append(f"[{lbl}]")
            valid_idx += 1
    music_input_idx = valid_idx
    audio_inputs += ["-stream_loop", "-1", "-i", str(MUSIC_BED)]
    audio_filter.append(f"[{music_input_idx}:a]atrim=0:{final_video_duration:.3f},volume=0.14[music]")
    amix_labels.append("[music]")
    audio_filter.append(f"{''.join(amix_labels)}amix=inputs={len(amix_labels)}:duration=longest:normalize=0[aout]")
    final_audio = JOB_DIR / "audio_mix.mp3"
    subprocess.run(
        ["ffmpeg", "-y", *audio_inputs, "-filter_complex", ";".join(audio_filter),
         "-map", "[aout]", "-t", f"{final_video_duration:.3f}", str(final_audio)],
        capture_output=True, text=True, check=True,
    )

    # ---- Mux ---- #
    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_only), "-i", str(final_audio),
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

    # ---- Thumbnail ---- #
    subprocess.run(["ffmpeg", "-y", "-ss", "2.0", "-i", str(final_mp4), "-vframes", "1",
                   "-vf", f"scale={1280}:{720}", str(JOB_DIR / "thumbnail_1280x720.jpg")],
                  capture_output=True, text=True)

    # ---- Contact sheet ---- #
    from PIL import Image
    n_thumbs = 12
    thumbs = []
    for i in range(n_thumbs):
        t = final_video_duration * (i + 0.5) / n_thumbs
        tp = JOB_DIR / f"thumb_{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(final_mp4), "-vframes", "1", str(tp)],
                      capture_output=True, text=True)
        thumbs.append(Image.open(tp))
    cols, rows = 4, 3
    tw, th = 480, 270
    sheet = Image.new("RGB", (tw * cols, th * rows), (20, 20, 20))
    for i, im in enumerate(thumbs):
        sheet.paste(im.resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
    sheet.save(JOB_DIR / "contact_sheet.jpg", quality=92)

    # ---- scene_manifest.json ---- #
    manifest = []
    for i, s in enumerate(plan):
        manifest.append({
            "shot_id": s["id"], "order": i + 1, "duration_sec": s["duration"],
            "narration": s["narration"], "purpose": s["purpose"], "k70_mode": s["kind"],
            "reason": s["reason"], "vfx": s.get("vfx"), "fallback_used": s.get("fallback_used", False),
        })
    (JOB_DIR / "scene_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # ---- mode_usage.json ---- #
    mode_usage = {}
    for s in plan:
        mode_usage[s["kind"]] = mode_usage.get(s["kind"], 0) + 1
    (JOB_DIR / "mode_usage.json").write_text(json.dumps({
        "counts": mode_usage, "total_shots": len(plan),
        "vfx_shots": sum(1 for s in plan if "vfx" in s),
        "vfx_quality_counts": {
            q: sum(1 for s in plan if s.get("vfx", {}).get("quality") == q) for q in ["LOW", "MEDIUM", "HERO"]
        },
        "fallbacks": FALLBACK_LOG,
    }, indent=2), encoding="utf-8")

    # ---- performance_report.json ---- #
    total_time = round(time.time() - t0, 1)
    dur_actual = measure_duration(final_mp4)
    file_size = final_mp4.stat().st_size
    (JOB_DIR / "performance_report.json").write_text(json.dumps({
        "total_shots": len(plan), "final_duration_sec": dur_actual, "resolution": f"{W}x{H}", "fps": FPS,
        "file_size_bytes": file_size, "total_production_time_sec": total_time,
        "fallback_count": len(FALLBACK_LOG),
    }, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur_actual}s, {file_size / 1e6:.1f}MB)")
    print(f"THUMBNAIL: {JOB_DIR / 'thumbnail_1280x720.jpg'}")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"MANIFEST: {JOB_DIR / 'scene_manifest.json'}")
    print(f"Total build time: {total_time}s")
    print(f"Fallbacks triggered: {len(FALLBACK_LOG)}")


if __name__ == "__main__":
    main()
