#!/usr/bin/env python3
"""
Phase-1 validation — CPU-only ComfyUI LCM performance + character consistency.

Generates a 3-scene ANIME cybercrime story ("Cyber hacker finds an exposed password
database") with ONE reusable character, at 512x768 / 8-step LCM / tiled VAE / anime
negative, talking to a LOCAL CPU ComfyUI. It measures, per image: wall-clock render
time, ComfyUI process RAM peak (RSS), system min-available RAM, and peak CPU load —
then a perceptual-hash CHARACTER-CONSISTENCY score across scenes. If stable, it
assembles the 3 stills into a real MP4 (Kokoro TTS + Ken Burns + captions).

This is a PURE ComfyUI test: it calls _remote_comfyui_image directly (no cloud
fallback), so a ComfyUI failure is visible, not silently masked.

    .venv/bin/python scripts/verify_phase1_lcm.py            # measure + render
    .venv/bin/python scripts/verify_phase1_lcm.py --no-render

ComfyUI must be running CPU-safe first:
    COMFYUI_DIR=/home/kadir70/ai-video/ComfyUI ./scripts/comfyui_cpu.sh
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

# --- FORCE CPU-safe LCM settings BEFORE importing app config ----------------- #
os.environ.update({
    "COMFYUI_ENABLED": "1",
    "COMFYUI_BASE_URL": os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188"),
    "COMFYUI_LCM": "1",
    "COMFYUI_LCM_LORA": "lcm-lora-sdv1-5.safetensors",
    "COMFYUI_LCM_STEPS": "8",
    "COMFYUI_LCM_CFG": "2.0",
    "COMFYUI_VAE_TILED": "1",
    "COMFYUI_VAE_TILE_SIZE": "512",
    "COMFYUI_WIDTH": "512",
    "COMFYUI_HEIGHT": "768",
    "COMFYUI_CHECKPOINT": "DreamShaper_8_pruned.safetensors",
    "COMFYUI_TIMEOUT": "900",
    # anime-safe negative (the global default bars anime/cartoon — wrong here)
    "COMFYUI_NEGATIVE": ("lowres, bad anatomy, bad hands, extra fingers, deformed, "
                         "watermark, text, signature, jpeg artifacts, photorealistic, 3d"),
    "RENDER_BACKEND": "ffmpeg",
})

BAR = "═" * 74

# --- the reusable anime character + 3 point-to-point scenes ------------------ #
CHARACTER = ("kade, a young anime hacker, short messy black hair, teal hooded "
             "jacket, sharp glowing green eyes, fingerless gloves, light freckles")
STYLE = ("anime key visual, cel shaded, 2d anime style, cinematic dramatic "
         "lighting, cyberpunk, rim light, highly detailed, masterpiece")
CHAR_SEED = 77                       # FIXED across scenes → character consistency

REF = ("upper-body character reference portrait, neutral dark background, "
       "looking at camera, calm")
SCENES = [
    ("s1", "Kade scans the dark net and finds a server left wide open.",
     "sitting at a dark desk lit by glowing monitors, one screen reading "
     "'ACCESS GRANTED', an exposed server diagram", "zoom_in"),
    ("s2", "Inside sits a database of millions of passwords in plain text.",
     "extreme close-up, teal-lit shocked face, a monitor filled with rows of "
     "plaintext usernames and passwords reflected in his eyes", "ken_burns"),
    ("s3", "One click could expose them all — and he knows it.",
     "hand hovering over a mechanical keyboard, tense expression, a neon city "
     "skyline through a rain-streaked window at night", "zoom_out"),
]


def _prompt(action: str) -> str:
    return f"{CHARACTER}, {action}, {STYLE}"


# --- resource sampler (/proc, no psutil) ------------------------------------ #
class Sampler(threading.Thread):
    def __init__(self, pid: int | None, interval: float = 0.5):
        super().__init__(daemon=True)
        # NB: do NOT name this `_stop` — that shadows threading.Thread._stop().
        self.pid, self.interval, self._halt = pid, interval, False
        self.min_avail_mb = 10 ** 9
        self.max_load = 0.0
        self.max_rss_mb = 0.0

    @staticmethod
    def _avail_mb() -> float:
        for ln in open("/proc/meminfo"):
            if ln.startswith("MemAvailable"):
                return int(ln.split()[1]) / 1024
        return 0.0

    @staticmethod
    def _total_mb() -> float:
        for ln in open("/proc/meminfo"):
            if ln.startswith("MemTotal"):
                return int(ln.split()[1]) / 1024
        return 0.0

    @staticmethod
    def _load() -> float:
        return float(open("/proc/loadavg").read().split()[0])

    def _rss_mb(self) -> float:
        try:
            for ln in open(f"/proc/{self.pid}/status"):
                if ln.startswith("VmRSS"):
                    return int(ln.split()[1]) / 1024
        except Exception:
            return 0.0
        return 0.0

    def run(self):
        while not self._halt:
            self.min_avail_mb = min(self.min_avail_mb, self._avail_mb())
            self.max_load = max(self.max_load, self._load())
            if self.pid:
                self.max_rss_mb = max(self.max_rss_mb, self._rss_mb())
            time.sleep(self.interval)

    def stop(self):
        self._halt = True
        self.join(timeout=2)


def _comfy_pid() -> int | None:
    for pat in ("main.py --cpu", "port 8188", "ai-video/ComfyUI"):
        try:
            out = subprocess.check_output(["pgrep", "-f", pat], text=True).split()
            if out:
                return int(out[0])
        except Exception:
            continue
    return None


def _cache_path(prompt: str, seed: int):
    """Recompute the content-addressed cache path a ComfyUI still WOULD land at —
    lets --from-cache reuse a prior generation without regenerating (slow on CPU)."""
    from app.config import settings
    from app.pipeline.providers import _img_cache
    s = settings()
    variant = (f"lcm{s.comfyui_lcm_steps}@{s.comfyui_lcm_cfg}" if s.comfyui_lcm
               else f"std{s.comfyui_steps}@{s.comfyui_cfg}")
    base = s.comfyui_base_url.rstrip("/")
    key = (f"comfyui:{base}:{s.comfyui_checkpoint}:{variant}:"
           f"{s.comfyui_width}x{s.comfyui_height}:{seed}:{prompt}")
    return _img_cache(key, "png")


def _ahash(path: str, n: int = 16) -> np.ndarray:
    """Perceptual average-hash via ffmpeg→numpy (no PIL): nxn grayscale > mean."""
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", path, "-vf",
         f"scale={n}:{n},format=gray", "-f", "rawvideo", "-"])
    a = np.frombuffer(raw, dtype=np.uint8).astype(float)
    return a > a.mean()


def _sim(a: np.ndarray, b: np.ndarray) -> float:
    return 100.0 * (1.0 - float(np.mean(a != b)))


def _probe() -> bool:
    import httpx
    url = os.environ["COMFYUI_BASE_URL"].rstrip("/") + "/system_stats"
    try:
        r = httpx.get(url, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


async def main_async(args) -> int:
    from app.config import settings
    from app.pipeline.providers import _remote_comfyui_image, _comfy_graph

    s = settings()
    print(f"{BAR}\nPHASE-1 · CPU ComfyUI LCM validation\n{BAR}")
    print(f"   checkpoint={s.comfyui_checkpoint} · lcm={s.comfyui_lcm} "
          f"lora={s.comfyui_lcm_lora}")
    print(f"   {s.comfyui_width}x{s.comfyui_height} · {s.comfyui_lcm_steps} steps · "
          f"cfg {s.comfyui_lcm_cfg} · tiled_vae={s.comfyui_vae_tiled} "
          f"(tile {s.comfyui_vae_tile_size})")
    # prove the graph is the LCM graph
    g = _comfy_graph("x", 0)
    print(f"   graph nodes: {sorted(g)} · LoRA node 10 present: {'10' in g} · "
          f"decode={g['8']['class_type']}")

    pid = None
    if not args.from_cache:
        if not _probe():
            print(f"\n   ✗ ComfyUI NOT reachable at {os.environ['COMFYUI_BASE_URL']}.")
            print("     Start it CPU-safe first:")
            print("       COMFYUI_DIR=/home/kadir70/ai-video/ComfyUI "
                  "./scripts/comfyui_cpu.sh")
            return 2
        pid = _comfy_pid()
        print(f"   ComfyUI reachable · pid={pid}\n")
    else:
        print("   from-cache: reusing prior stills (ComfyUI not required)\n")

    # --- generate the character ref + 3 scenes, measuring each --------------- #
    jobs = [("ref", REF, "none")] + [(sid, act, mo) for sid, _, act, mo in SCENES]
    results = []
    total_mb = Sampler._total_mb()
    print(f"   system RAM: {total_mb:.0f} MB total · {Sampler._avail_mb():.0f} MB "
          f"available at start" + ("  · MODE: from-cache" if args.from_cache else ""))
    for i, (sid, action, _motion) in enumerate(jobs):
        prompt = _prompt(action)
        cached = _cache_path(prompt, CHAR_SEED)
        if args.from_cache:
            # reuse a prior generation; never regenerate (CPU SD is ~10 min/image)
            if cached.exists():
                dt, ok, err, path, used = 0.0, True, "", str(cached), 0.0
                min_avail = Sampler._avail_mb()
            else:
                print(f"   - {sid:4} not in cache — run once WITHOUT --from-cache to "
                      "generate it")
                continue
        else:
            smp = Sampler(pid)
            smp.start()
            t0 = time.perf_counter()
            try:
                path = await _remote_comfyui_image(prompt, seed=CHAR_SEED)
                ok, err = True, ""
            except Exception as e:  # noqa: BLE001
                path, ok, err = "", False, f"{type(e).__name__}: {str(e)[:120]}"
            finally:
                smp.stop()                       # guaranteed cleanup (no join hang)
            dt = time.perf_counter() - t0
            min_avail = smp.min_avail_mb
            used = total_mb - min_avail
        cold = " (COLD: incl. model load)" if i == 0 and not args.from_cache else ""
        tag = "✓" if ok else "✗"
        load = 0.0 if args.from_cache else smp.max_load
        when = "cached" if args.from_cache else f"{dt:6.1f}s{cold}"
        print(f"   {tag} {sid:4} {when} · peakRAM~{used:5.0f}MB used · "
              f"avail≥{min_avail:5.0f}MB · load≤{load:.2f}"
              + (f"  ERR {err}" if not ok else f"  → {Path(path).name}"))
        results.append({"sid": sid, "t": dt, "ok": ok, "path": path,
                        "used": used, "avail": min_avail, "load": load, "err": err})
        if not ok:
            print("\n   ✗ generation failed — aborting (pure ComfyUI test, no fallback).")
            return 1
    if not results:
        print("\n   ✗ nothing cached yet — generate first (drop --from-cache).")
        return 2

    # --- character consistency (perceptual hash vs the reference) ----------- #
    print(f"\n   ── character consistency (aHash similarity vs reference) ──")
    ref_h = _ahash(results[0]["path"])
    sims = []
    for r in results[1:]:
        sim = _sim(ref_h, _ahash(r["path"]))
        sims.append(sim)
        print(f"     {r['sid']} vs ref: {sim:5.1f}%")
    # pairwise scene-to-scene
    scene_hashes = [_ahash(r["path"]) for r in results[1:]]
    pair = [ _sim(scene_hashes[i], scene_hashes[i + 1])
             for i in range(len(scene_hashes) - 1) ]
    consistency = float(np.mean(sims + pair)) if (sims or pair) else 0.0

    # --- report card -------------------------------------------------------- #
    gen = [r for r in results if r["sid"] != "ref"]
    steady = [r["t"] for r in gen[1:]] or [r["t"] for r in gen] or [results[0]["t"]]
    peak_used = max(r["used"] for r in results)
    min_avail = min(r["avail"] for r in results)
    max_load = max(r["load"] for r in results)
    print(f"\n{BAR}\n   PHASE-1 REPORT CARD\n{BAR}")
    print(f"   scenes generated  : {len(gen)} (+1 char ref) · 0 crashes / 0 OOM")
    if not args.from_cache:
        print(f"   cold image (ref)  : {results[0]['t']:.1f}s (incl. model load)")
        print(f"   steady-state/img  : {np.mean(steady):.1f}s avg "
              f"(min {min(steady):.1f}s · max {max(steady):.1f}s)")
        print(f"   peak RAM used     : ~{peak_used:.0f} MB")
        print(f"   RAM min available : {min_avail:.0f} MB  "
              f"({'OK — no overflow' if min_avail > 400 else 'LOW — near swap!'})")
        print(f"   CPU peak load     : {max_load:.2f} (of {os.cpu_count()} cores)")
    else:
        print(f"   render time       : from-cache (reused; see live-run logs for s)")
    print(f"   char consistency  : {consistency:.1f}% "
          f"({'good' if consistency >= 70 else 'moderate — needs Phase-2 char memory'})")
    stable = (all(r["ok"] for r in results) and min_avail > 300)
    print(f"\n   {'✅ PHASE-1 STABLE — clear to proceed to Phase 2' if stable else '⚠ INSTABILITY — see above'}")

    if args.no_render:
        return 0 if stable else 1
    await _assemble_short(gen)
    return 0 if stable else 1


async def _assemble_short(gen: list[dict]) -> None:
    """Stitch the 3 generated stills into a real MP4 (TTS + Ken Burns + captions),
    bypassing asset re-resolution (the stills are already grounded)."""
    from app.config import load_channel
    from app.pipeline import captions, music, postprocess, render, sfx, tts
    from app.schemas.scene import Overlay, Scene, SceneGraph, SceneMeta, Visual
    from app.schemas.video_spec import Niche, VideoSpec

    print(f"\n{BAR}\n   ASSEMBLING DEMO SHORT (3 scenes)\n{BAR}")
    by_sid = {r["sid"]: r for r in gen}
    scenes = []
    for sid, narr, _action, motion in SCENES:
        if sid not in by_sid:
            continue                              # scene not generated yet — skip
        scenes.append(Scene(
            id=sid, narration=narr, duration_sec=4.5,
            visual=Visual(type="ai_image", strategy="ai_image",
                          scene_visual_type="dramatic", motion=motion,
                          asset_path=by_sid[sid]["path"],
                          visual_intent=narr,
                          decision_reason="Phase-1 CPU-LCM anime still (point-to-point)"),
            overlays=[Overlay(type="headline", text=narr.split(" ")[0].upper(),
                              y=0.16, emphasis="alert")] if sid == "s1" else []))
    graph = SceneGraph(meta=SceneMeta(
        video_id="vid_phase1_lcm", channel_id="k70_cyber", niche="cybersecurity",
        title="Cyber Hacker Finds an Exposed Password Database",
        hook="He found it wide open.", thumbnail_text="EXPOSED"), scenes=scenes)
    channel = load_channel("k70_cyber")
    spec = VideoSpec(channel_id="k70_cyber", niche=Niche.cybersecurity,
                     topic=graph.meta.title, allow_ai_image=True)

    def stage(label, t0):
        print(f"   [{label:9}] {time.perf_counter()-t0:5.1f}s")
    t = time.perf_counter(); graph = await tts.synthesize(graph, spec, channel); stage("tts", t)
    t = time.perf_counter(); graph = await captions.transcribe(graph); stage("captions", t)
    t = time.perf_counter(); graph = await music.add_music(graph, channel); stage("music", t)
    t = time.perf_counter(); graph = await sfx.add_sound_design(graph); stage("sfx", t)
    t = time.perf_counter(); raw = await render.render_remotion(graph); stage("render", t)
    t = time.perf_counter(); final = await postprocess.finalize(graph, raw, channel); stage("post", t)
    mp4 = final["mp4"]
    sz = Path(mp4).stat().st_size / 1e6 if Path(mp4).exists() else 0
    print(f"   ✅ MP4: {mp4}  ({sz:.1f} MB · ~{graph.total_duration_sec:.0f}s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-render", action="store_true", help="measure only, skip MP4")
    ap.add_argument("--from-cache", action="store_true",
                    help="reuse cached stills; never regenerate (CPU SD is ~10min/img)")
    args = ap.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
