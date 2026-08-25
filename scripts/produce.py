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
import json
import asyncio
import os
try:
    import resource
except ImportError:  # Windows: no POSIX resource module
    resource = None
import sys
import threading
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
PRESET_DIR = ROOT / "config" / "presets"
# Production timeout guard. A flat 600s was right while every job was a 20-45s
# Short, but it is a function of how much video there is to draw: a 12-minute
# documentary needs ~2.1x its own runtime to render on a 4-core host, so the
# flat guard aborted it before the first chapter finished. Budget per second of
# finished video, with the old value as the floor so Shorts behave exactly as
# before.
RENDER_TIMEOUT_FLOOR_S = 600.0
RENDER_TIMEOUT_PER_VIDEO_S = 6.0


def render_timeout(graph) -> float:
    return max(RENDER_TIMEOUT_FLOOR_S,
               graph.total_duration_sec * RENDER_TIMEOUT_PER_VIDEO_S)


# --- production-checkpoint glue (OpenMontage-audit gap #2) ------------------ #
# Module-level (not closures inside `run()`) so they're unit-testable without
# spinning up a full production run. No top-level `app.schemas` import here —
# `run()` deliberately imports the app package only AFTER the preset's env
# vars are applied (see `_load_preset`'s comment), and these helpers must
# honor the same ordering, hence the local import in `_load_graph`.
def _dump_graph(g, p: Path) -> None:
    p.write_text(g.model_dump_json(), encoding="utf-8")


def _load_graph(p: Path):
    from app.schemas.scene import SceneGraph
    # Measured TTS audio can legitimately clock a very short line at e.g.
    # 0.747s — a hair under Scene.duration_sec's `ge=0.8` floor. That was
    # always harmless in memory (plain attribute assignment doesn't re-
    # validate), but a checkpoint round-trip reconstructs the model from
    # JSON via model_validate_json, which DOES re-validate — so resuming a
    # job could crash on a value the live pipeline had been carrying all
    # along without issue. Clamp to the schema's own floor before validating
    # rather than loosen the floor itself (a real pacing constraint, not a
    # serialization artifact) or skip validation entirely (which would also
    # skip catching genuinely malformed checkpoint data).
    data = json.loads(p.read_text(encoding="utf-8"))
    for scene in data.get("scenes", []):
        if isinstance(scene.get("duration_sec"), (int, float)) and scene["duration_sec"] < 0.8:
            scene["duration_sec"] = 0.8
    return SceneGraph.model_validate(data)


def _stage_op(fn, *a, **kw):
    """Wrap a stage function (sync or async) into the zero-arg async callable
    `resumable_stage` expects, without duplicating this glue at every call
    site in `run()`."""
    async def _op():
        result = fn(*a, **kw)
        if asyncio.iscoroutine(result):
            result = await result
        return result
    return _op


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
    if resource is None:
        return 0.0
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    return ru.ru_utime + ru.ru_stime


async def _get_graph(args, preset):
    from app.schemas.scene import SceneGraph
    if args.from_json:
        graph = SceneGraph.model_validate_json(
            Path(args.from_json).read_text(encoding="utf-8"))
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
    from app.brand import load_theme
    from app.config import load_channel, log_provider_validation, settings
    from app.director import structures
    from app.pipeline import broll, captions, compliance, music, providers, qa, \
        ram, render_ffmpeg, sfx, storyboard, tts, variety, visual_budget
    from app.pipeline.production_optimizer import CheckpointStore, resumable_stage
    from app.schemas.scene import SceneGraph
    from app.schemas.video_spec import Niche, VideoSpec
    from app.voice import load_profile

    BAR = "═" * 70
    print(f"{BAR}\n● PRODUCE · preset={preset['name']} · v1-production (frozen)\n{BAR}")
    log_provider_validation()
    # Which asset sources this run can actually reach. Decided once, up front, so
    # an unconfigured provider costs nothing instead of one timeout per beat.
    print("   " + providers.availability_report().replace("\n", "\n   "))
    print(f"   grounding={'strict' if settings().strict_visuals else 'normal'} · "
          f"layered={settings().layered_render} · qa={settings().qa_enabled} · "
          f"backend={settings().render_backend} · ai_budget={settings().layered_ai_still_budget}")

    prof = load_profile()
    if prof.exists and prof.cascade():
        print(f"   voice: {prof.identity} (cloned) · "
              f"cascade={' → '.join(prof.cascade())}")
    else:
        print("   voice: ⚠ STOCK — no cloned voice configured "
              "(see docs/VOICE_CLONING.md)")

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

    # PRODUCTION CHECKPOINTING (OpenMontage-audit gap #2). Each expensive stage
    # below is wrapped in `resumable_stage`, which skips straight to the stage's
    # already-recorded SceneGraph snapshot when it validates (artifact present
    # AND its sha256 matches what was recorded at completion) instead of
    # re-running the stage. On a fresh job every stage simply runs once, exactly
    # as before — this only changes behavior on a SECOND invocation for the SAME
    # video_id (a resume after a crash/kill/timeout). It sits ALONGSIDE the
    # existing content-addressed caches (TTS, provider search/download, scene
    # clips, `broll.py`'s new per-scene asset_progress.json), not instead of
    # them — those make a redone call cheap, this avoids redoing the call.
    ckpt = CheckpointStore(graph.meta.video_id)

    # A prior run for this exact video_id already finished AND its output is
    # still on disk (implies --keep was used — a non-kept run deletes final.mp4
    # at the end, which correctly invalidates this shortcut: there is nothing
    # to resume TO). Report it and stop — this is what "don't repeat
    # finalizable completed work" means at the whole-pipeline level.
    if ckpt.valid("pipeline"):
        prior = json.loads((out_dir / "qa_report.json").read_text(encoding="utf-8")) \
            if (out_dir / "qa_report.json").exists() else {}
        print(f"   ✓ {graph.meta.video_id} already completed and kept — "
              f"{out_mp4} ({out_mp4.stat().st_size/1e6:.1f}MB). "
              f"Delete final.mp4 or the job dir to force a re-render.")
        return 0 if prior.get("passed", True) else 1

    def stage(label, t0):
        print(f"   [{label:13}] {time.perf_counter()-t0:5.1f}s")

    sampler = RamSampler(); sampler.start()
    cpu0 = _cpu_s(); t_all = time.perf_counter(); timed_out = False
    final_budget = None   # set below; stays None if an earlier stage raised first
    failures: list[str] = []
    # Sized from the AUTHORED durations. They are replaced by measured TTS below,
    # which only ever shortens them here, so this is a safe upper bound.
    render_budget_s = render_timeout(graph)

    try:
        # VARIETY PLAN — drawn before anything renders so the visual engine, the
        # music picker and the renderer all read the same decisions.
        theme = load_theme(graph.brand_id or "k70")
        choice = structures.choose(
            graph.meta.video_id, graph.meta.channel_id, graph.meta.niche,
            forced=graph.meta.structure_id or preset.get("story_structure", ""),
            record=not graph.meta.structure_id)
        graph.meta.structure_id = choice.id
        # FROZEN per job. Re-rendering must not re-roll the dice: a different
        # grade/cuts/camera/zoom changes the render context and forces every
        # scene clip to be rebuilt even when nothing about the scene changed.
        plan_path = (settings().data_dir / "jobs" / graph.meta.video_id
                     / "variety.json")
        plan = variety.thaw(plan_path)
        frozen = plan is not None
        if plan is None:
            plan = variety.plan(graph.meta.video_id, graph.meta.channel_id,
                                theme, choice)
            variety.freeze(plan_path, plan)
        variety.apply(graph, plan)
        print(f"   structure: {choice.structure.name} ({len(graph.scenes)} scenes)")
        print(f"   variety  : {plan.summary()}"
              f"{'  [frozen]' if frozen else ''}")

        # character memory + per-scene LAYER PLAN (nominates the single hero beat).
        t = time.perf_counter()
        graph = await resumable_stage(
            ckpt, "storyboard",
            _stage_op(storyboard.storyboard, graph, character_name=spec.character_name,
                     character_desc=spec.character_desc, style=spec.character_style),
            dump=_dump_graph, load=_load_graph)
        stage("storyboard", t)

        if args.no_voice:
            # VISUAL PREVIEW. This renders NO narration at all — it does not
            # substitute a different voice, which the identity lock forbids and
            # which would be a far worse outcome than silence. Scene durations
            # stay at the authored estimates instead of being overwritten by
            # measured audio, so the cut is timed but not locked; re-running
            # without this flag once the clone exists retimes everything to the
            # real voiceover.
            print("   [voiceover    ] SKIPPED — --no-voice preview "
                  "(silent cut; no substitute narrator)")
            failures.append("PREVIEW ONLY: no narration — cloned voice not built yet")
        else:
            t = time.perf_counter()
            graph = await resumable_stage(
                ckpt, "voiceover", _stage_op(tts.synthesize, graph, spec, channel),
                dump=_dump_graph, load=_load_graph)
            stage("voiceover", t)
        try:
            t = time.perf_counter()
            graph = await resumable_stage(
                ckpt, "captions", _stage_op(captions.transcribe, graph, theme=theme),
                dump=_dump_graph, load=_load_graph)
            stage("captions", t)
        except Exception as e:
            failures.append(f"captions skipped ({type(e).__name__})")

        # EXACT real footage only (no AI, no random stock — strict grounding).
        # VISUAL BUDGET is folded into the SAME checkpointed stage as asset
        # resolution (not its own): the budget only means anything as the input
        # to the resolver that reads it, so checkpointing it separately would
        # let a resume load a stale budget against a re-resolved graph.
        async def _assets_op():
            budget = visual_budget.allocate(graph)
            g = visual_budget.apply(graph, budget)
            print("   " + budget.format().replace("\n", "\n   "))
            g = await broll.resolve_assets(g, spec_real)
            return g

        t = time.perf_counter()
        graph = await resumable_stage(ckpt, "assets", _assets_op,
                                      dump=_dump_graph, load=_load_graph)
        stage("exact-footage", t)
        # EXACT AI hero generation — the ONLY AI source, cache-first, ≤2 stills.
        t = time.perf_counter()
        graph = await resumable_stage(
            ckpt, "hero_gen", _stage_op(broll.resolve_layers, graph, spec),
            dump=_dump_graph, load=_load_graph)
        stage("hero-gen", t)

        try:
            t = time.perf_counter()
            graph = await resumable_stage(
                ckpt, "music",
                _stage_op(music.add_music, graph, channel, family=plan.music_family),
                dump=_dump_graph, load=_load_graph)
            stage("music", t)
            t = time.perf_counter()
            graph = await resumable_stage(
                ckpt, "sfx", _stage_op(sfx.add_sound_design, graph),
                dump=_dump_graph, load=_load_graph)
            stage("sfx", t)
        except Exception as e:
            failures.append(f"audio-bed partial ({type(e).__name__})")

        # Monetisation safety: rewrites, disclaimer, AI-disclosure flags.
        # compliance.apply's REPORT (violations/checklist) isn't itself part of
        # the graph, so it is not resumable-cacheable the same way — cheap and
        # deterministic given the graph, so it just re-runs every time, resumed
        # or not (consistent with the render stage's own design, see below).
        t = time.perf_counter()
        creport = compliance.apply(graph, strict=False)
        stage("compliance", t)
        print("   " + creport.format().replace("\n", "\n   "))
        if creport.violations:
            failures.append(f"{len(creport.violations)} compliance violation(s)")

        _grounding_summary(graph)
        out_dir.joinpath("scene_graph.json").write_text(
            graph.model_dump_json(indent=2), encoding="utf-8")

        # Delivered visual-breakdown report, rebuilt from what ACTUALLY resolved
        # rather than from the plan — a beat that fell back to another source must
        # be counted where it landed, not where it was allocated.
        final_budget = visual_budget.measure(graph)
        stale = visual_budget.audit_unused(graph)
        out_dir.joinpath("visual_breakdown.json").write_text(json.dumps(
            {**final_budget.as_dict(), "unused_generated_assets": stale},
            indent=2), encoding="utf-8")
        print("\n   ── delivered visual breakdown ─────────────────────────────")
        print("   " + final_budget.format().replace("\n", "\n   "))
        print(f"   unused generated assets: {len(stale)}"
              + (f" — {', '.join(stale)}" if stale else " ✓"))
        if stale:
            failures.append(f"{len(stale)} generated asset(s) never composited")

        # LAYERED COMPOSITION + captions burn + audio mux (timeout-guarded).
        # NOT wrapped in `resumable_stage` like the stages above: render_ffmpeg
        # already has its own, more precise scene-level cache (manifest.json —
        # fingerprint + sha256 + ffprobe per clip, untouched by this change), so
        # a re-invocation after a crash is already cheap ("N reused, 0
        # rendered"). Adding a coarse stage-level checkpoint on TOP of it would
        # gain nothing over what the scene cache already gives — worse, a naive
        # one risks staying "valid" after `out_mp4` is deleted (the default
        # --keep-absent cleanup below), which would skip re-rendering with
        # nothing to hand to QA. The whole-pipeline shortcut at the top of this
        # function already covers "the entire job, including render, already
        # finished and was kept" without that risk.
        t = time.perf_counter()
        await asyncio.wait_for(render_ffmpeg.render(graph, out_mp4),
                               timeout=render_budget_s)
        stage("render", t)
    except asyncio.TimeoutError:
        timed_out = True
        failures.append(f"render exceeded {render_budget_s:.0f}s timeout guard")
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
                     consistency=consistency, timed_out=timed_out,
                     budget_report=final_budget)
    # PERSIST the audit. The packaging step (finalize_short.py) used to re-run
    # this entire analysis on the loudnormed file — ten more full decodes of the
    # same frames. Packaging stream-copies the video, so every video check here
    # already describes the delivered bitstream exactly; writing the report lets
    # packaging reuse it and re-probe only what loudnorm can actually change.
    # These are also the ONLY trustworthy RAM/wall-time metrics: they come from
    # the process that did the rendering.
    out_dir.joinpath("qa_report.json").write_text(
        rep.model_dump_json(indent=2), encoding="utf-8")
    out_dir.joinpath("qa_report.txt").write_text(
        qa.format_report(rep), encoding="utf-8")

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
    checklist = compliance.publish_checklist(graph)
    if checklist:
        print("\n   ⚠ BEFORE PUBLISHING:")
        for line in checklist:
            print("     " + line)

    print(f"\n   📄 spec : {out_dir/'scene_graph.json'}")
    if out_mp4.exists():
        print(f"   🎬 MP4  : {out_mp4}  ({out_mp4.stat().st_size/1e6:.1f}MB · "
              f"{rep.metrics.get('duration_s','?')}s)")

    ok = rep.passed and not failures
    # Record the whole-pipeline checkpoint BEFORE the --keep cleanup below, so
    # its validity genuinely reflects "did this run finish" independent of
    # whether the file was kept — the top-of-run shortcut additionally
    # requires out_mp4.exists() itself, so a non-kept run correctly finds
    # nothing to resume to on the next invocation.
    if ok and out_mp4.exists():
        ckpt.record("pipeline", "completed", artifact=str(out_mp4))
    if not args.keep and out_mp4.exists():
        out_mp4.unlink()
    print(f"\n{'✓ PRODUCTION OK' if ok else '✗ PRODUCTION ISSUES (see above)'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", required=True, help="config/presets/<name>.yaml")
    ap.add_argument("--topic", help="topic for the Director (omit with --from-json)")
    ap.add_argument("--from-json", help="render a fixed SceneGraph spec (skip Director)")
    ap.add_argument("--keep", action="store_true", help="keep the final MP4")
    ap.add_argument("--no-voice", action="store_true",
                    help="visual preview: render the cut with NO narration. Does "
                         "not substitute another voice — use before the cloned "
                         "voice exists, then re-run without it to lock timing.")
    args = ap.parse_args()
    if not args.topic and not args.from_json:
        ap.error("give --topic or --from-json")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
