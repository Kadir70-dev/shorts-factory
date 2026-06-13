#!/usr/bin/env python3
"""
PRODUCTION WORKFLOW (v1-production, frozen architecture) — exact storytelling shorts.

Drives the FROZEN Phase 1-4 pipeline end-to-end from a single production PRESET:

  Topic → Research → Script → Scene breakdown        (Director, or a fixed --from-json spec)
        → Locked narration↔visual grounding          (VISUAL_ACCURACY_MODE=strict)
        → Same character memory + layer plan          (storyboard + character registry)
        → Voiceover + Captions                        (Kokoro TTS + whisper)
        → EXACT real footage, no random stock         (resolve_assets, allow_ai_image=OFF)
        → EXACT AI hero generation (cache-first, ≤2)  (resolve_layers — the ONLY AI source)
        → Layered cinematic composition               (FFmpeg bg▸subject▸fx composite)
        → QA (black-frame / RAM / budget / consistency)
        → Final MP4 + metadata

BUDGET GUARANTEE (no pipeline change — pure orchestration): resolve_assets runs with
allow_ai_image=False so every non-hero beat is exact REAL footage (zero AI, zero
random stock), and resolve_layers is the SOLE source of AI stills — hard-capped at
LAYERED_AI_STILL_BUDGET (2) inside the single LAYERED_MAX_HERO_SCENES (1) hero beat.

    .venv/bin/python scripts/produce.py --preset anime_storytelling \
        --from-json data/demos/anime_ghost_key.json --keep
    .venv/bin/python scripts/produce.py --preset cybersecurity --topic "..."
"""
from __future__ import annotations

import argparse
import asyncio
import os
import resource
import sys
import threading
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
PRESET_DIR = ROOT / "config" / "presets"
RENDER_TIMEOUT_S = 600.0          # production timeout guard per short


# --------------------------------------------------------------------------- #
def _load_preset(name: str) -> dict:
    path = PRESET_DIR / f"{name}.yaml"
    if not path.exists():
        avail = ", ".join(p.stem for p in PRESET_DIR.glob("*.yaml"))
        raise SystemExit(f"✗ no preset '{name}'. Available: {avail}")
    preset = yaml.safe_load(path.read_text())
    # Apply the preset env BEFORE app.config is imported (settings is lru-cached).
    for k, v in (preset.get("env") or {}).items():
        os.environ[k] = str(v)
    return preset


class RamSampler(threading.Thread):
    def __init__(self, period: float = 0.2):
        super().__init__(daemon=True)
        self.period, self._stopping, self.min_free = period, False, float("inf")

    def run(self):
        from app.pipeline import ram
        while not self._stopping:
            a = ram.available_mb()
            if a is not None:
                self.min_free = min(self.min_free, a)
            time.sleep(self.period)

    def halt(self) -> float:
        self._stopping = True
        self.join(timeout=1.0)
        return self.min_free if self.min_free != float("inf") else -1.0


def _cpu_s() -> float:
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    return ru.ru_utime + ru.ru_stime


async def _get_graph(args, preset):
    from app.schemas.scene import SceneGraph
    if args.from_json:
        graph = SceneGraph.model_validate_json(Path(args.from_json).read_text())
        print(f"   source: fixed spec {args.from_json} ({len(graph.scenes)} scenes)")
        return graph
    # Director path (Topic → Research → Script → Scene + grounding). Needs the
    # Claude director backend; falls back to a clear error suggesting --from-json.
    from app.config import load_channel
    from app.director import get_director
    from app.schemas.video_spec import Niche, VideoSpec
    channel = load_channel(preset["channel_id"])
    spec = VideoSpec(channel_id=preset["channel_id"], niche=Niche(preset["niche"]),
                     topic=args.topic, allow_ai_image=True)
    director = get_director(channel)
    graph = await director.build_scene_graph(spec)
    print(f"   source: Director · '{graph.meta.title[:50]}' ({len(graph.scenes)} scenes)")
    return graph


def _grounding_summary(graph) -> None:
    print("\n   ── point-to-point visual plan (hook-first) ──────────────────")
    for i, s in enumerate(graph.scenes):
        v = s.visual
        tag = "HOOK " if i == 0 else ("HERO " if v.layers and any(
            l.role == "subject" or l.role == "fx" for l in v.layers) else "     ")
        layers = ("+".join(l.role for l in v.layers)) if v.layers else "-"
        print(f"   {tag}{s.id} {s.duration_sec:4.1f}s [{v.type:8}] layers={layers:24} "
              f"{s.narration[:46]}")


# --------------------------------------------------------------------------- #
async def run(args) -> int:
    preset = _load_preset(args.preset)
    from app.config import load_channel, log_provider_validation, settings
    from app.pipeline import broll, captions, music, qa, ram, \
        render_ffmpeg, sfx, storyboard, tts
    from app.schemas.video_spec import Niche, VideoSpec

    BAR = "═" * 70
    print(f"{BAR}\n● PRODUCE · preset={preset['name']} · v1-production (frozen)\n{BAR}")
    log_provider_validation()
    print(f"   grounding={'strict' if settings().strict_visuals else 'normal'} · "
          f"layered={settings().layered_render} · qa={settings().qa_enabled} · "
          f"backend={settings().render_backend} · ai_budget={settings().layered_ai_still_budget}")

    if not (ROOT / "data/assets/fx/scanlines.png").exists():
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "scripts/make_fx_assets.py")])

    graph = await _get_graph(args, preset)
    channel = load_channel(graph.meta.channel_id)
    ch = preset.get("character") or {}

    # Two specs: the AI-source one (layers may generate) and the REAL-only one used
    # for the footage pass so non-hero beats never spend an AI still / random stock.
    spec = VideoSpec(channel_id=graph.meta.channel_id, niche=Niche(graph.meta.niche),
                     topic=graph.meta.title, allow_ai_image=True,
                     character_name=ch.get("name", ""),
                     character_desc=ch.get("desc", ""),
                     character_style=ch.get("style", ""))
    spec_real = spec.model_copy(update={"allow_ai_image": False,
                                        "allow_ai_video": False})

    out_dir = settings().data_dir / "jobs" / graph.meta.video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / "final.mp4"

    def stage(label, t0):
        print(f"   [{label:13}] {time.perf_counter()-t0:5.1f}s")

    sampler = RamSampler(); sampler.start()
    cpu0 = _cpu_s(); t_all = time.perf_counter(); timed_out = False
    failures: list[str] = []

    try:
        # character memory + per-scene LAYER PLAN (nominates the single hero beat).
        t = time.perf_counter()
        graph = storyboard.storyboard(graph, character_name=spec.character_name,
                                      character_desc=spec.character_desc,
                                      style=spec.character_style)
        stage("storyboard", t)

        t = time.perf_counter(); graph = await tts.synthesize(graph, spec, channel)
        stage("voiceover", t)
        try:
            t = time.perf_counter(); graph = await captions.transcribe(graph)
            stage("captions", t)
        except Exception as e:
            failures.append(f"captions skipped ({type(e).__name__})")

        # EXACT real footage only (no AI, no random stock — strict grounding).
        t = time.perf_counter(); graph = await broll.resolve_assets(graph, spec_real)
        stage("exact-footage", t)
        # EXACT AI hero generation — the ONLY AI source, cache-first, ≤2 stills.
        t = time.perf_counter(); graph = await broll.resolve_layers(graph, spec)
        stage("hero-gen", t)

        try:
            t = time.perf_counter(); graph = await music.add_music(graph, channel)
            stage("music", t)
            t = time.perf_counter(); graph = await sfx.add_sound_design(graph)
            stage("sfx", t)
        except Exception as e:
            failures.append(f"audio-bed partial ({type(e).__name__})")

        _grounding_summary(graph)
        out_dir.joinpath("scene_graph.json").write_text(graph.model_dump_json(indent=2))

        # LAYERED COMPOSITION + captions burn + audio mux (timeout-guarded).
        t = time.perf_counter()
        await asyncio.wait_for(render_ffmpeg.render(graph, out_mp4),
                               timeout=RENDER_TIMEOUT_S)
        stage("render", t)
    except asyncio.TimeoutError:
        timed_out = True
        failures.append(f"render exceeded {RENDER_TIMEOUT_S:.0f}s timeout guard")
    except Exception as e:  # noqa: BLE001 — production guard: record, don't crash
        failures.append(f"{type(e).__name__}: {str(e)[:140]}")
        import traceback; traceback.print_exc()

    render_s = time.perf_counter() - t_all
    cpu_s = _cpu_s() - cpu0
    min_free = sampler.halt()
    peak_rss = ram.child_peak_mb()

    # consistency — reuse/re-resolve of the locked character (when one is defined).
    consistency = None
    if spec.character_name:
        hero = next((s for s in graph.scenes
                     if any(l.role == "subject" for l in s.visual.layers)), None)
        subj = next((l for l in (hero.visual.layers if hero else [])
                     if l.role == "subject" and l.asset_path), None)
        if subj:
            try:
                from app.pipeline import character as charmod
                from app.pipeline.providers import ai_image_generate
                ref = charmod.get_or_create(graph.meta.video_id, spec.character_name,
                                            spec.character_desc)
                rr = await ai_image_generate(subj.prompt, graph.meta.video_id,
                                             "s_consistency", seed=ref.seed)
                consistency = qa.consistency_pct(subj.asset_path, rr)
            except Exception:
                consistency = None

    rep = qa.analyze(graph, str(out_mp4), render_seconds=render_s,
                     ram_peak_mb=peak_rss, min_free_mb=min_free,
                     consistency=consistency, timed_out=timed_out)
    ai_stills = len({l.asset_path for s in graph.scenes for l in s.visual.layers
                     if l.kind == "ai_image" and l.asset_path})

    # --- report --------------------------------------------------------------- #
    print(f"\n{BAR}\n● QA + METRICS\n{BAR}")
    print(qa.format_report(rep))
    print(f"\n   render {render_s:.0f}s · CPU {cpu_s:.0f}s · ffmpeg peak ~{peak_rss:.0f}MB · "
          f"min free {(min_free if min_free>=0 else 0):.0f}MB")
    print(f"   AI stills used {ai_stills}/{settings().layered_ai_still_budget} (cache-first) · "
          f"consistency {f'{consistency:.0f}%' if consistency is not None else 'n/a'}")
    if failures:
        print("\n   FAILURE POINTS:")
        for f in failures:
            print("     -", f)
    print(f"\n   📄 spec : {out_dir/'scene_graph.json'}")
    if out_mp4.exists():
        print(f"   🎬 MP4  : {out_mp4}  ({out_mp4.stat().st_size/1e6:.1f}MB · "
              f"{rep.metrics.get('duration_s','?')}s)")
    if not args.keep and out_mp4.exists():
        out_mp4.unlink()

    ok = rep.passed and not failures
    print(f"\n{'✓ PRODUCTION OK' if ok else '✗ PRODUCTION ISSUES (see above)'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", required=True, help="config/presets/<name>.yaml")
    ap.add_argument("--topic", help="topic for the Director (omit with --from-json)")
    ap.add_argument("--from-json", help="render a fixed SceneGraph spec (skip Director)")
    ap.add_argument("--keep", action="store_true", help="keep the final MP4")
    args = ap.parse_args()
    if not args.topic and not args.from_json:
        ap.error("give --topic or --from-json")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
