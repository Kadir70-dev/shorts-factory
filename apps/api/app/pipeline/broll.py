"""
Asset router — the REAL b-roll / footage engine, driven by the Smart Scene
Decision Engine (Phase 5.6: free Google AI Studio images, AI-images-only).

For each scene the decision engine (`scene_director.decide`) first picks ONE
primary visual STRATEGY — real / ai_image / motion_gfx / hybrid — enforcing the
mix target (real ~70%, ai_image ~20%, motion_gfx ~10%; never AI video). This
resolver then turns that strategy into a concrete file on disk, ALWAYS with a
real-footage safety net so a scene never ships empty and a missing GOOGLE_API_KEY
or a generation failure degrades to footage — never breaks.

Per-strategy resolution (each falls through downward on miss):

  motion_gfx → manim chart ─────────────────────────────┐
  ai_image   → Google AI Studio still → ────────────────┤
  hybrid     → Google AI Studio still (+ overlays) → ────┤
  real       → ─────────────────────────────────────────┤
                                                         ▼
            Pexels video → Pixabay video → Pexels/Pixabay photo (Ken Burns)
                                                         ▼
                              animated gradient (never a black frame)

So everyday-realism / explainer beats (grocery/gas/streets/voting lines/crowds)
stay REAL footage, while history recreations, symbolic politics, scandals,
elections, dark history and impossible-to-film moments get a cinematic Google AI
image — realism preferred, AI used selectively, never the whole short.

Smart matching: the Director-authored `broll_keywords` / `scene_visual_type`
drive footage search; AI prompts are built from `visual_intent` / `query`.
Adjacent scenes get *different* candidates for the same query (the `pick` index)
so footage never repeats, while staying deterministic.
"""
from __future__ import annotations

import asyncio
import json

from pathlib import Path

from ..brand import theme_for
from ..brand.theme import BrandTheme
from ..config import settings
from ..schemas.scene import Layer, Scene, SceneGraph
from ..schemas.video_spec import VideoSpec
from . import character as char
from . import clip_rank
from . import dataviz
from . import motiongfx
from . import paperima_engine
from . import ram
from . import scene_director as sd
from . import asset_engine
from . import fashion_viz_bridge
from . import ai_broll
from . import finance_motion
from . import threejs_engine
from .providers import (
    ai_image_generate, ai_video_generate, build_video_prompt,
    clamp_i2v_seconds, clamp_insert_seconds, manim_render, pexels_image,
    pexels_video, picsart_image_to_video, pixabay_image, pixabay_video,
    multi_source_candidates, download_asset_candidate,
    pexels_video_candidates, pixabay_video_candidates,
    pexels_image_candidates, pixabay_image_candidates,
    download_rank_candidate,
)

# Extra search cues appended to the Director's keywords, by editorial role.
# Deliberately SPECIFIC + USA/emotion-flavoured — generic "business stock" reads
# as fake; "wall street fear" / "worried american consumers" reads as news.
_INTENT_TERMS: dict[str, list[str]] = {
    "dramatic": ["wall street fear", "us inflation news", "tense newsroom"],
    "data_viz": ["wall street trading floor", "us stock market crash",
                 "american economy charts"],
    "subtle": ["american flag slow motion", "us city skyline dusk",
               "quiet american street"],
    "abstract": ["financial data motion background", "stock ticker close up"],
    "real_footage": [],
}

# Niche flavour so a generic query still resolves to SPECIFIC, on-topic, USA
# footage instead of stocky corporate filler.
_NICHE_TERMS: dict[str, list[str]] = {
    "usa_finance": ["american grocery shopping", "us gas station prices",
                    "grocery checkout inflation", "worried american consumers",
                    "family cutting spending", "cost of living usa",
                    "wall street fear"],
    "usa_politics": ["us capitol washington dc", "white house exterior",
                     "american congress hearing", "us press conference"],
    "usa_election": ["american voters polling station", "us campaign rally",
                     "election night usa", "american flag waving"],
    "usa_facts": ["american suburb neighborhood", "us city street life",
                  "american diner restaurant", "us highway road trip",
                  "american flag small town", "everyday life usa"],
    "usa_history": ["old archival america", "vintage american photographs",
                    "historic black and white footage", "old newspaper headlines",
                    "antique american documents", "dramatic historical reenactment"],
    "usa_business": ["wall street trading floor", "american tech office",
                     "silicon valley campus", "ceo boardroom meeting",
                     "us factory production line", "data center servers"],
    # Cybersecurity = realistic, cinematic, on-topic supporting footage. NO hoodie
    # hacker / matrix clichés (see _CLICHE_TERMS) — real SOCs, servers, code on a
    # monitor, security analysts, breach-response teams.
    "cybersecurity": ["security operations center monitors", "data center server room",
                      "cybersecurity analyst working", "code on computer screen dark",
                      "server racks blinking lights", "person typing on laptop office",
                      "network operations center team", "email inbox on screen"],
    # FASHION vertical — real garments, real hands, real factories and shop
    # floors. Never fashion-influencer haul stock, never AI-runway pastiche.
    "fashion_luxury": ["atelier seamstress hands sewing", "leather craftsman workshop",
                       "fabric texture macro close up", "haute couture dress detail",
                       "luxury boutique interior", "runway fashion show model walking"],
    "fashion_business": ["clothing store rails shopping", "retail shop floor customers",
                         "garment factory production line", "warehouse boxes conveyor",
                         "fashion designer sketching studio", "clothes hanging on rail store"],
    "fashion_supply_chain": ["container ship port cranes", "textile warehouse rolls of fabric",
                             "cargo containers stacked terminal", "logistics truck loading dock",
                             "garment factory workers sewing", "freight airplane cargo loading"],
    "fashion_manufacturing": ["industrial sewing machine operator", "garment cutting table fabric",
                              "textile factory machinery running", "clothing quality inspection",
                              "pattern cutting workshop", "steam press garment finishing"],
    "textile_industry": ["cotton field harvest", "spinning mill yarn machinery",
                         "fabric dyeing vats textile", "loom weaving cloth close up",
                         "rolls of fabric warehouse", "wool fibre processing"],
    "streetwear": ["city street style pedestrians", "sneaker store queue line",
                   "skate park youth culture", "graffiti urban wall street",
                   "clothing screen printing workshop", "streetwear shop interior"],
    "sneaker_culture": ["sneakers close up detail", "shoe factory sole assembly",
                        "sneaker store shelves display", "person lacing shoes close up",
                        "basketball court shoes playing", "shoe box unboxing hands"],
    "fashion_trends": ["fashion week street style", "runway show audience front row",
                       "clothing rail boutique browsing", "fashion editorial photoshoot studio",
                       "young people city street fashion", "shop window mannequin display"],
    "fashion_history": ["vintage fashion archival footage", "old black and white fashion photographs",
                        "antique sewing machine", "historic department store archive",
                        "vintage clothing museum garments", "old newspaper fashion advertisement"],
}

# Image motion per role — keeps a still alive and matches the beat's energy.
_INTENT_MOTION: dict[str, str] = {
    "dramatic": "zoom_in",
    "data_viz": "zoom_in",
    "subtle": "ken_burns",
    "abstract": "pan_lr",
    "real_footage": "ken_burns",
}


def _theme(graph: SceneGraph) -> BrandTheme:
    return theme_for(graph, "asset_composition")


def _local_asset(video_id: str, scene_id: str, name: str) -> Path:
    """Where a locally-RENDERED visual (chart, kinetic type, branded plate) goes.
    Kept beside the job rather than in the shared media cache: these are unique to
    one video's numbers and wording, so caching them across shorts would be wrong."""
    d = settings().data_dir / "jobs" / video_id / "visuals"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{scene_id}_{name}"


async def _branded_plate(scene: Scene, graph: SceneGraph) -> str | None:
    """TIER 4 — the floor. A beat with nothing specific to show gets a branded
    plate rather than an unrelated stock clip, so even the weakest beat still
    looks like this channel instead of like everyone else's B-roll."""
    try:
        out = _local_asset(graph.meta.video_id, scene.id, "plate.mp4")
        return str(await motiongfx.plate(
            _theme(graph), out, graph.width, graph.height, graph.fps,
            max(2.5, scene.duration_sec), seed=abs(hash(scene.id)) % 9973))
    except Exception as e:                       # noqa: BLE001
        print(f"[visual] {scene.id}: branded plate failed ({type(e).__name__})",
              flush=True)
        return None


def _display_headline(scene: Scene) -> str:
    """The line a VIEWER may read on a kinetic-type card.

    Display copy only. `visual.visual_intent` is a note aimed at the asset
    resolver — "Marine One lifting off the South Lawn, 1971 — the vanishing" —
    and it used to sit in this fallback chain, so any footage beat that failed
    to resolve published that production note on screen as its headline. An
    authored `headline` overlay is display copy by definition; narration is the
    line the viewer is already hearing, so it is always safe to set in type.
    """
    return next((o.text for o in scene.overlays if o.type == "headline"),
                "") or scene.narration


# camera_movement values whose EXISTING ffmpeg treatment is a documented,
# self-acknowledged approximation of PHYSICAL paper motion —
# papercraft/animate.py's own docstring: "true 3D page-curl isn't
# expressible in a plain ffmpeg filter graph..." (page_turn) and "a single
# flat page has no depth layers to separate..." (parallax). These two are
# the only beats this integration spends a Paperima render on; every other
# camera_movement is an honest camera pan/zoom over a static page, already
# well served by the existing zoompan path, and is left on it untouched.
# This is the "only when the document needs physical motion" boundary the
# Paperima integration is scoped to.
_PAPERIMA_WORTHY: dict[str, "paperima_engine.AnimationType"] = {
    "page_turn": "dynamic", "parallax": "wobble",
}


async def _try_paperima(scene: Scene, graph: SceneGraph, camera_movement: str) -> None:
    """Optional finishing pass over the Scribus page `_render_papercraft`
    just produced (see module docstring + pipeline/paperima_engine.py).
    Never required: on any failure, or when Paperima isn't installed, the
    scene is left exactly as `_render_papercraft` set it — the pre-existing
    camera_vf zoompan path (render_ffmpeg.py) animates that unchanged, so
    this function has nothing to clean up on the failure path."""
    animation_type = _PAPERIMA_WORTHY.get(camera_movement)
    if animation_type is None or not paperima_engine.available():
        return
    try:
        prov = await paperima_engine.render(
            scene.id, scene.visual.asset_path, animation_type,
            duration_sec=max(2.0, scene.duration_sec), fps=graph.fps,
            width=graph.width, height=graph.height)
    except Exception as e:                        # noqa: BLE001 — degrade, never break
        print(f"[dispatch] {scene.id}: paperima failed ({type(e).__name__}) "
              "→ papercraft camera move stays", flush=True)
        return
    graph.paperima_provenance.append(prov)
    if prov.status in ("rendered", "cache_hit") and prov.render_path:
        scene.visual.asset_path = prov.render_path
        scene.visual.type = "paperima"
        scene.visual.motion = "none"
        scene.visual.decision_reason += f" → paperima:{animation_type} ({prov.status})"
    else:
        print(f"[dispatch] {scene.id}: paperima {prov.status} "
              f"({prov.error[:80]}) → papercraft camera move stays", flush=True)


async def _render_papercraft(scene: Scene, graph: SceneGraph) -> bool:
    """Fact-heavy beats already allocated to 'official', 'charts', or
    'motion_gfx' get a real laid-out document instead of a chart/archival-photo
    search or plain kinetic type, when the beat's own content says a document
    is the better fit (see papercraft/beat_detect.py). 'motion_gfx' is the
    "plain text on a background" tier — the paper-card treatment is its
    premium replacement for dates, quotes, figures, and other document-shaped
    beats, while beats with no such shape stay kinetic type (`is_eligible`
    gates that). Opt-in and additive: OFF preserves every existing
    chart/official/kinetic selection byte-for-byte; ON only ever substitutes
    WITHIN a channel that was already allocated, so the budget report's
    percentages never move."""
    if not settings().papercraft_engine_enabled:
        return False
    if scene.visual.budget_channel not in ("official", "charts", "motion_gfx"):
        return False
    from . import papercraft
    from .papercraft import beat_detect
    if not beat_detect.is_eligible(scene):
        return False
    try:
        doc_type = beat_detect.classify(scene, graph)
        spec = beat_detect.build_spec(scene, graph, doc_type)
        out = _local_asset(graph.meta.video_id, scene.id, "papercraft.png")
        result = await papercraft.render(spec, out)
        scene.visual.asset_path = str(result.png)
        scene.visual.type = "papercraft"
        scene.visual.motion = "none"          # camera_movement drives motion instead
        scene.visual.camera_movement = spec.camera_movement
        scene.visual.decision_reason = (
            f"papercraft:{doc_type} ({'cache hit' if result.cache_hit else 'rendered'})")
        await _try_paperima(scene, graph, spec.camera_movement)
        return True
    except papercraft.ScribusUnavailable as e:
        print(f"[dispatch] {scene.id}: papercraft unavailable ({e}) → chart/kinetic",
              flush=True)
        return False
    except Exception as e:                        # noqa: BLE001
        print(f"[dispatch] {scene.id}: papercraft failed ({type(e).__name__}: "
              f"{str(e)[:120]}) → chart/kinetic", flush=True)
        return False


async def _render_self(scene: Scene, graph: SceneGraph) -> bool:
    """Render this beat with no external dependency: a laid-out document when
    the content is fact-heavy and the engine is enabled, else a chart if it
    has real numbers, otherwise kinetic type. All three are local, so this
    tier cannot fail for want of a provider, a network call or a worker —
    which is what makes a blank frame unnecessary."""
    if await _render_papercraft(scene, graph):
        return True
    viz = scene.data or dataviz.from_scene(scene)
    if viz and viz.valid():
        try:
            out = _local_asset(graph.meta.video_id, scene.id, "chart.mp4")
            scene.visual.asset_path = str(await dataviz.render(
                viz, _theme(graph), out, graph.width, graph.height, graph.fps,
                max(2.5, scene.duration_sec)))
            scene.visual.type, scene.visual.motion = "dataviz", "none"
            scene.data = viz
            return True
        except Exception as e:                   # noqa: BLE001
            print(f"[dispatch] {scene.id}: chart failed ({type(e).__name__}) "
                  "→ kinetic card", flush=True)
    try:
        headline = _display_headline(scene)
        source = next((o.text for o in scene.overlays if o.type == "source"), "")
        out = _local_asset(graph.meta.video_id, scene.id, "gfx.mp4")
        scene.visual.asset_path = str(await motiongfx.kinetic(
            _theme(graph), out, graph.width, graph.height, graph.fps,
            max(2.5, scene.duration_sec), headline=headline, source=source,
            seed=abs(hash(scene.id)) % 9973))
        scene.visual.type, scene.visual.motion = "motion_gfx", "none"
        return True
    except Exception as e:                       # noqa: BLE001
        print(f"[dispatch] {scene.id}: kinetic failed ({type(e).__name__})",
              flush=True)
        return False


# --------------------------------------------------------------------------- #
# Beat-level resume (OpenMontage-audit gap #2). `resolve_assets` dispatches
# every scene concurrently via `asyncio.gather` — if the process dies partway
# (crash, OOM kill, timeout), scenes that had already finished (an asset was
# already downloaded/rendered and assigned) still need to be redone on the
# next run, because nothing recorded WHICH scenes were already done. This is
# a THIN layer under `_dispatch_scene`/`_resolve`: after a scene resolves, its
# resulting `visual.{asset_path,type,motion}` is snapshotted to a per-job JSON
# file; before a scene is dispatched, that snapshot is checked first — a hit
# whose asset file still exists on disk is applied directly and the (possibly
# expensive: Pexels/Pixabay search, an AI still, a Paper Craft/Three.js
# render) dispatch call is skipped entirely.
#
# This sits ALONGSIDE the existing content-addressed caches (provider search
# cache, `_download`'s sha1-named files, each engine's own render cache) —
# it does not replace them. Those caches make a REDONE call cheap; this layer
# avoids making the call at all.
_VISUAL_SNAPSHOT_FIELDS = ("asset_path", "type", "motion")


def _progress_path(video_id: str) -> Path:
    return settings().data_dir / "jobs" / video_id / "asset_progress.json"


def _load_progress(video_id: str) -> dict[str, dict]:
    try:
        data = json.loads(_progress_path(video_id).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_progress_entry(video_id: str, scene_id: str, snapshot: dict) -> None:
    """Read-modify-write, no `await` between read and write — safe under the
    single-threaded asyncio event loop even with many scenes finishing
    concurrently, because nothing yields control mid-update."""
    path = _progress_path(video_id)
    data = _load_progress(video_id)
    data[scene_id] = snapshot
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)


def _snapshot_visual(scene: Scene) -> dict:
    return {f: getattr(scene.visual, f) for f in _VISUAL_SNAPSHOT_FIELDS}


def _apply_visual_snapshot(scene: Scene, snapshot: dict) -> None:
    for f in _VISUAL_SNAPSHOT_FIELDS:
        if f in snapshot:
            setattr(scene.visual, f, snapshot[f])


def _snapshot_is_reusable(snapshot: dict) -> bool:
    """A snapshot with no asset_path (a `solid`/no-op outcome) is always
    reusable; one WITH a path is only reusable while that file still exists —
    a cleared cache directory must not resurrect a dangling reference."""
    path = snapshot.get("asset_path")
    return not path or Path(path).is_file()


async def _dispatch_scene_resumable(scene: Scene, idx: int, graph: SceneGraph,
                                    decision: "sd.Decision", progress: dict) -> None:
    snap = progress.get(scene.id)
    if snap and _snapshot_is_reusable(snap):
        _apply_visual_snapshot(scene, snap)
        return
    await _dispatch_scene(scene, idx, graph, decision)
    _save_progress_entry(graph.meta.video_id, scene.id, _snapshot_visual(scene))


async def _resolve_resumable(scene: Scene, idx: int, graph: SceneGraph, spec: VideoSpec,
                             decision: "sd.Decision", progress: dict) -> None:
    snap = progress.get(scene.id)
    if snap and _snapshot_is_reusable(snap):
        _apply_visual_snapshot(scene, snap)
        return
    await _resolve(scene, idx, graph, spec, decision)
    _save_progress_entry(graph.meta.video_id, scene.id, _snapshot_visual(scene))


async def _dispatch_scene(scene: Scene, idx: int, graph: SceneGraph,
                          decision: "sd.Decision") -> None:
    """Resolve ONE unclaimed scene down its own ladder.

        allocated channel → self renderer → branded placeholder

    Two rules the previous control flow could not express:

      * STOCK IS ONLY REACHABLE WHEN ALLOCATED. Previously any beat that failed
        its engine could be swept into stock footage, so a chart beat shipped as
        an unrelated clip. A beat allocated charts/threejs/official now falls to
        a self-rendered visual instead — it explains the same point.
      * THERE IS NO BLANK OUTCOME. `solid` produced an empty frame; the branded
        placeholder is the floor, and it is still on-brand.

    ONE deliberate exception to the first rule: a beat allocated `ai_broll`
    reaching this function means the AI engine already ran (in `resolve_assets`)
    and failed — a single provider outage should not fall straight to plain
    kinetic type when a bounded, one-shot stock search (the same call `stock`
    beats use, not a retry loop) might have real, on-topic footage available.
    Still falls to `_render_self`'s own ladder (papercraft/chart/kinetic) if
    that one search comes up empty, exactly as before this exception existed.
    """
    channel = scene.visual.budget_channel or ""

    if channel in ("stock", "ai_broll"):
        await _resolve_support_stock(scene, idx, graph)
        if scene.visual.asset_path:
            return

    if await _render_self(scene, graph):
        return

    plate = await _branded_plate(scene, graph)
    if plate:
        scene.visual.asset_path = plate
        scene.visual.type, scene.visual.motion = "branded", "none"
        return

    # Even the last resort stays branded rather than blank: `solid` renders the
    # theme background, never black, and never an empty asset_path.
    scene.visual.asset_path = None
    scene.visual.type = "branded"
    scene.visual.motion = "none"


async def resolve_assets(graph: SceneGraph, spec: VideoSpec) -> SceneGraph:
    _reset_rank_pool(graph.meta.video_id)
    # 1) decide the per-scene strategy + enforce the visual-mix budget.
    report = sd.decide(graph, spec)
    by_id = {d.scene_id: d for d in report.decisions}
    if ((settings().multi_source_asset_engine_enabled
         or settings().threejs_visual_engine_enabled
         or settings().motion_graphics_engine_enabled
         or settings().ai_broll_engine_enabled)
            and graph.storyboard is None):
        from . import storyboard
        graph.storyboard = storyboard.generate_semantic(graph, report)

    # FASHION VISUALIZATION ENGINE — runs FIRST. These beats are explicitly
    # authored (`visual.query = "fashionviz:<module>"`), so no lookup engine may
    # satisfy one with a stock clip. A no-op for every non-fashion channel.
    fashionviz_handled: dict[str, dict] = await fashion_viz_bridge.resolve(
        graph, quality=settings().threejs_quality.strip().lower())

    enhanced: dict[str, str] = {}
    if settings().multi_source_asset_engine_enabled:
        # OFFICIAL has to mean official. Querying pexels/pixabay here let a stock
        # clip satisfy an `official` allocation, and — because a claimed scene is
        # skipped by every later engine — let stock take beats the budget had
        # allocated to Three.js before that engine ever ran.
        discovery = ("government_public_domain", "sec_regulatory",
                     "company_ir", "wikimedia_commons")
        enhanced = await asset_engine.resolve(
            graph, multi_source_candidates, download_asset_candidate,
            providers=discovery)
        # This engine may only keep what it was allocated. Anything else it
        # happened to resolve is released so the allocated engine still runs.
        channels = {s.id: s.visual.budget_channel for s in graph.scenes}
        enhanced = {sid: path for sid, path in enhanced.items()
                    if channels.get(sid, "") in ("", "official")}
        for record in graph.asset_provenance:
            source_id = next((b.source_scene_id for b in graph.storyboard.scenes
                              if b.scene_id == record.scene_id), "")
            source = next((s for s in graph.scenes if s.id == source_id), None)
            if source:
                record.legacy_query = " | ".join(_search_terms(source, graph))
        # An approved cached asset bypasses only external lookup. Existing render
        # and motion semantics remain unchanged. Unresolved beats are explicit.
        for scene in graph.scenes:
            if scene.id in enhanced:
                path = enhanced[scene.id]
                scene.visual.asset_path = path
                scene.visual.type = ("broll" if Path(path).suffix.lower() in
                                     {".mp4", ".mov", ".webm"} else "image")
            # Scenes this engine did NOT claim are left untouched. Resetting them
            # to `solid` here erased the budget allocation for every downstream
            # engine and was the single largest source of blank frames — 39% of
            # one finished render. An engine may only describe what it claimed.

    motion_handled: set[str] = set()
    if settings().motion_graphics_engine_enabled and graph.storyboard is not None:
        by_source: dict[str, list] = {}
        for beat in graph.storyboard.scenes:
            by_source.setdefault(beat.source_scene_id, []).append(beat)
        motion_jobs = []
        for index, scene in enumerate(graph.scenes):
            if scene.id in enhanced or scene.id in fashionviz_handled:
                continue
            # Engine blocks run in a fixed order and each claims what it can, so
            # whichever runs first wins. That order predates the Visual Budget
            # Manager and silently overrode it: motion graphics claimed every
            # chart and 3D beat before those engines were ever consulted.
            # When a budget has allocated the beat, only its own engine may take it.
            if scene.visual.budget_channel not in ("", "motion_gfx"):
                continue
            beat = next((candidate for candidate in by_source.get(scene.id, [])
                         if finance_motion.map_template(candidate) is not None), None)
            if beat is None:
                continue
            motion_jobs.append((index, scene, beat))
        if settings().production_optimizer_enabled and motion_jobs:
            from .production_optimizer import scheduler
            operations = [
                (lambda index=index, scene=scene, beat=beat:
                    finance_motion.render(graph, scene, beat,
                        quality=settings().motion_graphics_quality, seed=index))
                for index, scene, beat in motion_jobs]
            motion_results = await scheduler.map("motion_graphics", operations,
                                                  kind="cpu", memory_mb=380)
        else:
            motion_results = [await finance_motion.render(
                graph, scene, beat, quality=settings().motion_graphics_quality,
                seed=index) for index, scene, beat in motion_jobs]
        for (_, scene, _), result in zip(motion_jobs, motion_results):
            graph.motion_graphics_provenance.append(result)
            if result.status in ("rendered", "cache_hit") and result.render_path:
                motion_handled.add(scene.id)
                scene.visual.asset_path = result.render_path
                scene.visual.type = "motion_gfx"
                scene.visual.motion = "none"
            # A failure leaves the scene UNCLAIMED so the dispatcher can fall it
            # down its own ladder. Marking it `solid` here made the failure
            # terminal and produced a blank frame.

    threejs_handled: set[str] = set()
    if settings().threejs_visual_engine_enabled and graph.storyboard is not None:
        by_source: dict[str, list] = {}
        for beat in graph.storyboard.scenes:
            by_source.setdefault(beat.source_scene_id, []).append(beat)
        three_jobs = []
        for scene in graph.scenes:
            # Official/licensed Phase 3 assets keep priority; Three.js should
            # explain numbers, not replace strong archival evidence.
            if (scene.id in enhanced or scene.id in motion_handled
                    or scene.id in fashionviz_handled):
                continue
            if scene.visual.budget_channel not in ("", "threejs"):
                continue
            beat = next((candidate for candidate in by_source.get(scene.id, [])
                         if threejs_engine.map_template(candidate) is not None), None)
            if beat is None:
                continue
            three_jobs.append((scene, beat))
        if settings().production_optimizer_enabled and three_jobs:
            from .production_optimizer import scheduler
            three_results = await scheduler.map("threejs", [
                (lambda scene=scene, beat=beat: threejs_engine.render(graph, scene, beat))
                for scene, beat in three_jobs], kind="browser", memory_mb=900)
        else:
            three_results = [await threejs_engine.render(graph, scene, beat)
                             for scene, beat in three_jobs]
        for (scene, _), result in zip(three_jobs, three_results):
            graph.threejs_provenance.append(result)
            if result.status in ("rendered", "cache_hit") and result.render_path:
                threejs_handled.add(scene.id)
                scene.visual.asset_path = result.render_path
                scene.visual.type = "threejs"
                scene.visual.motion = "none"
            # A failed clarity-specific visual is never permission to substitute
            # unrelated stock — the dispatcher falls it to a SELF-RENDERED chart
            # or kinetic card, which explains the same beat without a lookup.
        # Chromium is done here, and ffmpeg needs the RAM. Holding the worker
        # open through composition left 47MB free on a 4GB box and failed QA.
        await threejs_engine.close_worker()

    ai_handled: set[str] = set()
    if settings().ai_broll_engine_enabled and graph.storyboard is not None:
        by_source: dict[str, list] = {}
        for beat in graph.storyboard.scenes:
            by_source.setdefault(beat.source_scene_id, []).append(beat)
        local_success = motion_handled | threejs_handled | set(fashionviz_handled)
        ai_jobs = []
        for scene in graph.scenes:
            if scene.id in enhanced or scene.id in local_success:
                continue
            beat = next((candidate for candidate in by_source.get(scene.id, [])
                         if candidate.ai_broll_candidate), None)
            if beat is None:
                continue
            ai_jobs.append((scene, beat))
        if settings().production_optimizer_enabled and ai_jobs:
            from .production_optimizer import scheduler
            ai_results = await scheduler.map("ai_broll", [
                (lambda scene=scene, beat=beat: ai_broll.generate(graph, scene, beat))
                for scene, beat in ai_jobs], kind="io", memory_mb=300)
        else:
            ai_results = [await ai_broll.generate(graph, scene, beat)
                          for scene, beat in ai_jobs]
        for (scene, _), result in zip(ai_jobs, ai_results):
            graph.ai_broll_provenance.append(result)
            if result.status in ("rendered", "cache_hit") and result.render_path:
                ai_handled.add(scene.id)
                scene.visual.asset_path = result.render_path
                scene.visual.type = "ai_video" if result.asset_type == "video" else "ai_image"
                scene.visual.motion = "none" if result.asset_type == "video" else "ken_burns"
            # Unclaimed on failure — the dispatcher decides what replaces it.

    # ── SINGLE PER-SCENE DISPATCHER ──────────────────────────────────────────
    # This replaced four mutually-exclusive `return graph` branches selected by
    # which engine flags happened to be on. That ladder meant enabling ONE engine
    # silently disabled others: with ai_broll on, the function returned before
    # `_resolve()` ran, and `_resolve()` is the only implementation of chart
    # rendering, kinetic typography and the branded plate. Charts could not reach
    # a frame no matter what the budget allocated.
    #
    # Now every scene the engines did not claim is dispatched individually, down
    # ITS OWN ladder, and the feature gates above are unchanged — they still
    # decide which engines RUN, they just no longer decide who gets a renderer.
    engines_on = (settings().multi_source_asset_engine_enabled
                  or settings().motion_graphics_engine_enabled
                  or settings().threejs_visual_engine_enabled
                  or settings().ai_broll_engine_enabled)
    if engines_on:
        handled = (set(enhanced) | motion_handled | threejs_handled | ai_handled
                   | set(fashionviz_handled))
        progress = _load_progress(graph.meta.video_id)
        await asyncio.gather(
            *[_dispatch_scene_resumable(s, i, graph, by_id[s.id], progress)
              for i, s in enumerate(graph.scenes) if s.id not in handled]
        )
        if settings().strict_visuals:
            await _dedupe_real_assets(graph)
        await _diversify_semantic_assets(graph)
        return graph

    # 2) no engines enabled → the original single-pass resolver, untouched
    #    except that a fashion-viz beat is already resolved and must not be
    #    re-dispatched: _resolve would overwrite its clip with a generic card.
    progress = _load_progress(graph.meta.video_id)
    await asyncio.gather(
        *[_resolve_resumable(s, i, graph, spec, by_id[s.id], progress)
          for i, s in enumerate(graph.scenes) if s.id not in fashionviz_handled]
    )
    # 3) STRICT: never the SAME real clip twice — re-pick duplicates to a different,
    #    still-on-topic shot. AI images are already unique per prompt+seed.
    if settings().strict_visuals:
        await _dedupe_real_assets(graph)
    await _diversify_semantic_assets(graph)
    return graph


def _is_support_shot(scene: Scene) -> bool:
    return (scene.beat_role.lower() in {
        "setup", "context", "transition", "bridge", "cta", "close"
    } or scene.visual.scene_visual_type == "subtle")


async def _resolve_support_stock(scene: Scene, index: int,
                                 graph: SceneGraph) -> None:
    """Phase 6 floor: stock is permitted only as an honest support transition."""
    terms = _strip_cliches(_exact_terms(scene) or _search_terms(scene, graph),
                           scene.narration)
    query_text = " ".join(filter(None, [scene.narration, scene.visual.visual_intent])).strip()
    rank_key = f"{graph.meta.video_id}:{scene.id}"
    hit = await _video(terms, max(2.0, scene.duration_sec), index,
                       query_text=query_text, rank_key=rank_key)
    if hit:
        scene.visual.asset_path, scene.visual.type = hit, "broll"
        return
    hit = await _image(terms, index, query_text=query_text, rank_key=rank_key)
    if hit:
        scene.visual.asset_path, scene.visual.type = hit, "image"
        scene.visual.motion = "ken_burns"
        return
    scene.visual.asset_path = None
    scene.visual.type = "solid"


async def _dedupe_real_assets(graph: SceneGraph) -> None:
    """Cross-scene anti-repeat: if two beats resolved to the SAME real footage/photo
    file, re-pick the later one to a different candidate (cheap — reuses the cached
    per-query URL list, just a different index). Bounded; if no distinct clip
    exists it keeps the original (a repeat beats a black frame)."""
    seen: set[str] = set()
    for idx, scene in enumerate(graph.scenes):
        v = scene.visual
        if v.type not in ("broll", "image") or not v.asset_path:
            continue
        if v.asset_path not in seen:
            seen.add(v.asset_path)
            continue
        terms = _exact_terms(scene) or _search_terms(scene, graph)
        min_dur = max(2.0, scene.duration_sec)
        for off in range(1, 6):                 # try a few different candidates
            pick = idx + off
            cand = (await _video(terms, min_dur, pick) if v.type == "broll"
                    else await _image(terms, pick))
            if cand and cand not in seen:
                print(f"[grounding] {scene.id}: de-duped repeated footage → "
                      f"{cand.split('/')[-1]}", flush=True)
                v.asset_path = cand
                break
        seen.add(v.asset_path)                  # whatever we ended with


async def _resolve(scene: Scene, idx: int, graph: SceneGraph, spec: VideoSpec,
                   decision: "sd.Decision") -> None:
    v = scene.visual
    terms = _search_terms(scene, graph)
    pick = idx                          # vary footage across scenes (deterministic)
    min_dur = max(2.0, scene.duration_sec)
    strat = decision.strategy

    # ── TIER 4: BRANDED PLATE (chosen up front, not fallen into) ──────────────
    # The decision engine already established this beat has nothing specific to
    # show. Reaching for stock here is exactly the habit being removed.
    if strat == sd.BRANDED or v.type == "branded":
        plate = await _branded_plate(scene, graph)
        if plate:
            v.asset_path, v.type, v.motion = plate, "branded", "none"
            return

    # ── TIER 3: ANIMATED CHART ────────────────────────────────────────────────
    # The beat states a real figure, so the figure IS the visual. Rendered locally
    # from the numbers the Director authored — no network, no Manim, and crucially
    # no placeholder data: `dataviz.render` refuses a chart it has no values for.
    if strat == sd.DATAVIZ or v.type == "dataviz":
        viz = scene.data or dataviz.from_scene(scene)
        if viz and viz.valid():
            try:
                out = _local_asset(graph.meta.video_id, scene.id, "chart.mp4")
                v.asset_path = str(await dataviz.render(
                    viz, _theme(graph), out, graph.width, graph.height,
                    graph.fps, max(2.5, scene.duration_sec)))
                v.type = "dataviz"
                scene.data = viz
                print(f"[visual] {scene.id}: chart — {dataviz.summarize(viz)}",
                      flush=True)
                return
            except Exception as e:               # noqa: BLE001
                print(f"[visual] {scene.id}: chart failed ({type(e).__name__}: "
                      f"{str(e)[:80]}) → next tier", flush=True)
        # no usable numbers → this was never really a data beat; fall through.

    # ── TIER 2: MOTION GRAPHICS ───────────────────────────────────────────────
    # No filmable subject: build the claim itself on screen in the channel's type.
    if strat == sd.MOTION_GFX or v.type == "motion_gfx":
        try:
            headline = _display_headline(scene)
            kicker = next((o.text for o in scene.overlays
                           if o.type == "lower_third"), "")
            source = next((o.text for o in scene.overlays
                           if o.type == "source"), "")
            out = _local_asset(graph.meta.video_id, scene.id, "gfx.mp4")
            v.asset_path = str(await motiongfx.kinetic(
                _theme(graph), out, graph.width, graph.height, graph.fps,
                max(2.5, scene.duration_sec), headline=headline, kicker=kicker,
                source=source, seed=abs(hash(scene.id)) % 9973))
            v.type = "motion_gfx"
            return
        except Exception as e:                   # noqa: BLE001
            print(f"[visual] {scene.id}: motion graphics failed "
                  f"({type(e).__name__}) → next tier", flush=True)

    # Legacy Manim path — only when manim is installed AND the beat has real data.
    if v.type == "manim":
        try:
            v.asset_path = await manim_render(v.query or v.visual_intent,
                                              graph.meta.video_id, scene.id)
        except Exception:
            v.asset_path = None
        if v.asset_path:
            return

    # C) AI VIDEO — a SHORT cinematic motion clip on a hero / high-emotion beat.
    #    Two engines, config-selected (AI_VIDEO_PROVIDER):
    #      • picsart (default, IMAGE→VIDEO): generate the still LOCAL ComfyUI would
    #        anyway (ai_image chain), then animate THAT SAME still into a 3–5s clip
    #        via Picsart. If Picsart fails, ship the still itself with cinematic Ken
    #        Burns motion — the fallback is free and built in.
    #      • else (legacy Pika TEXT→VIDEO): a 1–3s insert, degrading to an AI image.
    #    Either way it NEVER replaces real footage; on total failure we fall through
    #    to REAL footage below — the render never breaks.
    if strat == sd.AI_VIDEO and spec.allow_ai_video:
        cfg = settings()
        if cfg.enable_image_to_video and cfg.ai_video_provider == "picsart":
            img = (await _ai_image(scene, graph, decision, pick)
                   if spec.allow_ai_image else None)
            if img:
                clip = await _picsart_i2v(img, scene, graph, decision, pick)
                if clip:
                    v.asset_path, v.type, v.motion = clip, "ai_video", "none"
                    return
                # Picsart unavailable → ship the still with Ken Burns motion.
                v.asset_path, v.type = img, "ai_image"
                v.motion = _INTENT_MOTION.get(v.scene_visual_type, "ken_burns")
                return
            # no still produced → fall through to REAL footage below.
        else:
            clip = await _ai_video(scene, graph, decision, pick)
            if clip:
                v.asset_path, v.type, v.motion = clip, "ai_video", "none"
                return
            # Pika unavailable → degrade to a cinematic AI image, then real footage.
            if spec.allow_ai_image:
                img = await _ai_image(scene, graph, decision, pick)
                if img:
                    v.asset_path, v.type = img, "ai_image"
                    v.motion = _INTENT_MOTION.get(v.scene_visual_type, "ken_burns")
                    return

    # B/E) AI IMAGE (and HYBRID) — cinematic documentary still via Google AI
    #      Studio (free-first), with Ken Burns / parallax motion. On a missing
    #      GOOGLE_API_KEY or any generation failure, _ai_image returns None and we
    #      fall through to REAL footage below (Pexels/Pixabay) — never breaks.
    if strat in (sd.AI_IMAGE, sd.HYBRID) and spec.allow_ai_image:
        img = await _ai_image(scene, graph, decision, pick)
        if img:
            v.asset_path, v.type = img, "ai_image"
            v.motion = _INTENT_MOTION.get(v.scene_visual_type, "ken_burns")
            return

    # A) REAL footage — the narration→visual grounding lock changes the ORDER:
    #    STRICT: exact footage (Tier 1) → AI recreation of the exact event (Tier 2,
    #            skipped for everyday-realism beats) → generic stock (Tier 4, the
    #            non-black safety net only).
    #    normal: the original combined exact+generic search.
    query_text = " ".join(filter(None, [scene.narration, v.visual_intent])).strip()
    rank_key = f"{graph.meta.video_id}:{scene.id}"

    if settings().strict_visuals:
        narr = scene.narration
        km = _INTENT_MOTION.get(v.scene_visual_type, "ken_burns")

        async def _try(terms: list[str]) -> bool:
            """Try real footage then photo for one tier; set asset on a hit."""
            terms = _strip_cliches(terms, narr)        # anti-cliché guard
            hit = await _video(terms, min_dur, pick, query_text=query_text, rank_key=rank_key)
            if hit:
                v.asset_path, v.type = hit, "broll"
                return True
            hit = await _image(terms, pick, query_text=query_text, rank_key=rank_key)
            if hit:
                v.asset_path, v.type = hit, "image"
                v.motion = km
                return True
            return False

        # Tier 1 — EXACT real footage of the named subject/event.
        if await _try(_exact_terms(scene)):
            return
        # Tier 2 — AI RECREATION of the exact event, BEFORE any generic stock.
        # Skipped for everyday-realism beats (grocery/streets/crowds) where AI
        # looks fake — those stay real footage even if only generic matches.
        if spec.allow_ai_image and not decision.force_real:
            img = await _ai_image(scene, graph, decision, pick)
            if img:
                v.asset_path, v.type = img, "ai_image"
                v.motion = km
                return
        # Tier 3 — CINEMATIC SUPPORTING footage (curated, on-topic niche shots).
        if await _try(_supporting_terms(scene, graph)):
            return
        # Tier 4 — generic role filler. Demoted BELOW the branded plate: a clip
        # that says nothing about this beat is worse than an honest branded frame,
        # and it is what made every upload look like the same stock library.
        plate = await _branded_plate(scene, graph)
        if plate:
            v.asset_path, v.type, v.motion = plate, "branded", "none"
            return
        if await _try(_generic_terms(scene)):
            return
        v.type = "solid"
        return

    # normal mode — video first (Pexels → Pixabay). Realism, always preferred.
    vid = await _video(terms, min_dur, pick, query_text=query_text, rank_key=rank_key)
    if vid:
        v.asset_path, v.type = vid, "broll"
        return

    # real PHOTO — Pexels then Pixabay, with Ken Burns motion (realism tier).
    photo = await _image(terms, pick, query_text=query_text, rank_key=rank_key)
    if photo:
        v.asset_path, v.type = photo, "image"
        v.motion = _INTENT_MOTION.get(v.scene_visual_type, "ken_burns")
        return

    # Nothing on-topic was found. A branded plate before a flat colour — and
    # before generic stock, which is the point of the whole ladder.
    plate = await _branded_plate(scene, graph)
    if plate:
        v.asset_path, v.type, v.motion = plate, "branded", "none"
        return
    v.type = "solid"


# --- AI generation helpers -------------------------------------------------- #
def _ai_subject(scene: Scene) -> str:
    """The beat's subject line used to build AI image/video prompts (shared so the
    decision readout shows exactly what gets generated)."""
    v = scene.visual
    return (v.visual_intent or v.query or " ".join(v.broll_keywords[:4])
            or scene.narration)


async def _ai_image(scene: Scene, graph: SceneGraph, decision: "sd.Decision",
                    pick: int) -> str | None:
    try:
        return await ai_image_generate(
            _ai_subject(scene), graph.meta.video_id, scene.id,
            category=decision.category or "default", seed=pick,
        )
    except Exception:
        return None


async def _picsart_i2v(image_path: str, scene: Scene, graph: SceneGraph,
                       decision: "sd.Decision", pick: int) -> str | None:
    """Animate an already-generated still into a 3–5s cinematic Picsart clip, or
    None on any failure (→ resolver ships the still with Ken Burns motion; never
    breaks). The hero beat uses PICSART_HERO_MODEL when set."""
    prompt = build_video_prompt(_ai_subject(scene))
    dur = clamp_i2v_seconds(scene.duration_sec)
    # spend the premium hero model ONLY on the single hero beat, and only if set.
    hero_model = settings().picsart_hero_model.strip()
    model = hero_model if (decision.hero and hero_model) else None
    try:
        return await picsart_image_to_video(
            image_path, prompt, dur, graph.meta.video_id, scene.id,
            seed=pick, model=model,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[picsart] {scene.id}: ✗ image→video unavailable "
              f"({type(e).__name__}: {str(e)[:90]}) → falling back to "
              f"AI image (Ken Burns) / real footage", flush=True)
        return None


async def _ai_video(scene: Scene, graph: SceneGraph, decision: "sd.Decision",
                    pick: int) -> str | None:
    """Generate a 1–3s cinematic Pika insert for this beat, or None on any failure
    (→ resolver degrades to AI image / real footage; never breaks)."""
    prompt = build_video_prompt(_ai_subject(scene))
    dur = clamp_insert_seconds(scene.duration_sec)
    try:
        return await ai_video_generate(
            prompt, dur, graph.meta.video_id, scene.id, seed=pick,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[ai-video] {scene.id}: ✗ Pika unavailable "
              f"({type(e).__name__}: {str(e)[:90]}) → falling back to "
              f"AI image / real footage", flush=True)
        return None


def _ordered(*groups: list[str]) -> list[str]:
    """Flatten term groups in priority order, trimmed + case-insensitively deduped."""
    seen: set[str] = set()
    out: list[str] = []
    for g in groups:
        for t in g:
            t = (t or "").strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
    return out


# Cliché cybersecurity (and general) stock to AVOID unless the narration literally
# references it. The hoodie-hacker / matrix-rain / glowing-neon-laptop garbage that
# makes a doc look fake. `_strip_cliches` drops any search term containing one of
# these UNLESS the scene's narration mentions it (root word), so an intentional
# "matrix code on his screen" still resolves.
_CLICHE_TERMS: list[str] = [
    "hoodie", "hooded", "ski mask", "balaclava", "anonymous mask", "guy fawkes",
    "matrix code", "matrix rain", "green code", "falling code", "binary rain",
    "binary background", "glowing laptop", "neon code", "faceless hacker",
    "hacker in the dark", "mysterious hacker", "cyber hacker",
]


def _strip_cliches(terms: list[str], narration: str) -> list[str]:
    """Drop cliché stock phrases unless the narration explicitly invokes them."""
    nl = (narration or "").lower()
    out: list[str] = []
    for t in terms:
        tl = t.lower()
        hit = next((c for c in _CLICHE_TERMS if c in tl), None)
        if hit and hit not in nl and hit.split()[0] not in nl:
            continue                    # cliché the line never asked for → drop
        out.append(t)
    return out


def _exact_terms(scene: Scene) -> list[str]:
    """ONLY the Director-authored, line-specific phrases — the exact subject/event
    of THIS beat. No generic niche/role filler. This is Tier-1 grounding."""
    v = scene.visual
    return _ordered(v.broll_keywords, [v.query], scene.keywords)


def _supporting_terms(scene: Scene, graph: SceneGraph) -> list[str]:
    """CINEMATIC SUPPORTING footage — curated, on-topic niche phrases (Tier 3): a
    real SOC, server room, code-on-monitor, analysts. Relevant and cinematic, just
    not the exact event. Tried after exact footage + AI recreation, before generic."""
    return _ordered(_NICHE_TERMS.get(graph.meta.niche, []))


def _generic_terms(scene: Scene) -> list[str]:
    """Generic role filler (Tier 4) — the non-grounded last resort before a solid.
    Reached only after exact, AI recreation, and supporting all miss."""
    return _ordered(_INTENT_TERMS.get(scene.visual.scene_visual_type, []))


def _search_terms(scene: Scene, graph: SceneGraph) -> list[str]:
    """Ordered, de-duplicated search phrases for one scene (normal/smart matching):
    exact Director terms → role filler → niche filler. Preserves the original
    pre-STRICT ordering exactly (backward compatible)."""
    return _ordered(_exact_terms(scene), _generic_terms(scene),
                    _supporting_terms(scene, graph))


async def _video(terms: list[str], min_dur: float, pick: int, *,
                 query_text: str = "", rank_key: str = "") -> str | None:
    """Real-footage VIDEO: Pexels then Pixabay (priority tiers 1+2).

    When `query_text` is given (narration + visual intent for this beat),
    tries semantic ranking first — see `_semantic_pick`. That path returns
    None the moment CLIP is unavailable, the candidate pool is too small to
    rank, or nothing clears the relevance floor, in which case this falls
    through to the exact keyword-first-hit behavior below, unchanged from
    before semantic ranking existed.
    """
    if query_text:
        picked = await _semantic_pick(terms, min_dur, query_text, "video", rank_key)
        if picked:
            return picked
    return (
        await _first_hit(lambda t, p: pexels_video(t, min_dur, p), terms, pick)
        or await _first_hit(lambda t, p: pixabay_video(t, min_dur, p), terms, pick)
    )


async def _image(terms: list[str], pick: int, *,
                 query_text: str = "", rank_key: str = "") -> str | None:
    """Real-footage PHOTO: Pexels then Pixabay (realism tier, gets Ken Burns).
    See `_video` for the semantic-ranking-first / keyword-fallback contract."""
    if query_text:
        picked = await _semantic_pick(terms, 0.0, query_text, "image", rank_key)
        if picked:
            return picked
    return (
        await _first_hit(pexels_image, terms, pick)
        or await _first_hit(pixabay_image, terms, pick)
    )


async def _first_hit(search, terms: list[str], pick: int) -> str | None:
    for t in terms:
        if not t:
            continue
        try:                            # a transient network/download failure on
            hit = await search(t, pick)  # one term must NOT crash the pipeline —
        except Exception:               # fall through to the next term/tier.
            continue
        if hit:
            return hit
    return None


# --------------------------------------------------------------------------- #
# Semantic ranking — clean-room CLIP-style retrieval (see pipeline/clip_rank.py)
# --------------------------------------------------------------------------- #
# `_RANK_POOL` remembers, per scene, the full ranked candidate list a
# successful semantic pick produced — including the embeddings, which is
# expensive to recompute. `_diversify_semantic_assets` reads it after every
# scene has resolved to catch the case keyword-dedupe cannot: two DIFFERENT
# stock files that just happen to show the same generic shot (two different
# "server room with blinking lights" clips, say). Cleared per job so a
# long-lived worker process never leaks memory across renders.
_RANK_POOL: dict[str, tuple["clip_rank.RankedCandidate", list["clip_rank.RankedCandidate"]]] = {}


def _reset_rank_pool(video_id: str) -> None:
    prefix = f"{video_id}:"
    for key in [k for k in _RANK_POOL if k.startswith(prefix)]:
        del _RANK_POOL[key]


async def _semantic_pick(terms: list[str], min_dur: float, query_text: str,
                         kind: str, rank_key: str) -> str | None:
    """Try each term in order (mirrors `_first_hit`'s tier fallthrough): fetch
    a candidate pool from Pexels+Pixabay, rank it against `query_text`, and
    return the top pick if — and only if — it clears the relevance floor.
    Remembers the ranked pool under `rank_key` for the diversify post-pass.
    """
    if not clip_rank.available():
        return None
    for term in terms:
        if not term:
            continue
        try:
            if kind == "video":
                cands = (await pexels_video_candidates(term, min_dur)
                         + await pixabay_video_candidates(term, min_dur))
            else:
                cands = (await pexels_image_candidates(term)
                         + await pixabay_image_candidates(term))
        except Exception:
            continue
        if len(cands) < 2:
            continue                    # not enough to meaningfully rank
        try:
            ranked = await clip_rank.rank_async(cands, query_text)
        except Exception:
            ranked = []
        if not ranked or ranked[0].relevance < clip_rank.DEFAULT_MIN_RELEVANCE:
            continue
        best = ranked[0]
        try:
            local = await download_rank_candidate(best.candidate)
        except Exception:
            continue
        if not local:
            continue
        if rank_key:
            _RANK_POOL[rank_key] = (best, ranked)
        return local
    return None


async def _diversify_semantic_assets(graph: SceneGraph) -> None:
    """Cross-scene diversity pass over semantically-ranked picks only (see
    `_RANK_POOL`). Walks scenes in a stable, sequential order — unlike the
    concurrent resolution pass, so an MMR-style "already selected" list is
    meaningful here. A scene whose chosen asset embeds too close to one
    already kept (`clip_rank.is_near_duplicate`) is swapped for the best
    alternate in its own ranked pool that is NOT a near-duplicate of
    anything kept so far; if every alternate is also too similar, the
    original pick stands — a repeat beats an unrelated clip.
    No-op when CLIP is unavailable or no scene in this graph was ranked.
    """
    if not clip_rank.available() or not _RANK_POOL:
        return
    selected: list = []
    for scene in graph.scenes:
        key = f"{graph.meta.video_id}:{scene.id}"
        entry = _RANK_POOL.get(key)
        if entry is None:
            continue
        chosen, pool = entry
        if chosen.vec is None:
            continue
        if not any(clip_rank.is_near_duplicate(chosen.vec, s) for s in selected):
            selected.append(chosen.vec)
            continue
        replacement = next(
            (rc for rc in pool
             if rc is not chosen and rc.vec is not None
             and not any(clip_rank.is_near_duplicate(rc.vec, s) for s in selected)),
            None,
        )
        if replacement is None:
            selected.append(chosen.vec)     # nothing better on offer — keep it
            continue
        try:
            local = await download_rank_candidate(replacement.candidate)
        except Exception:
            local = None
        if local:
            scene.visual.asset_path = local
            print(f"[grounding] {scene.id}: diversified near-duplicate visual "
                  f"→ {replacement.candidate.download_url.split('/')[-1]}", flush=True)
            selected.append(replacement.vec)
        else:
            selected.append(chosen.vec)


# --------------------------------------------------------------------------- #
# Phase 3 — LIVE LAYER-ASSET WIRING
# --------------------------------------------------------------------------- #
# Fills scene.visual.layers[*].asset_path so the FFmpeg compositor (pipeline/
# layers.py) has real files to stack. STRICT CPU-safe doctrine:
#   • CACHE-FIRST: every generator (ai_image_generate) is content-addressed and
#     short-circuits on a cache hit; a pre-set asset_path is reused as-is; and
#     identical (prompt, seed) layers within a short are memoized so a reused
#     character costs ONE generation, not N.
#   • HARD BUDGET: at most `layered_ai_still_budget` (2) UNIQUE AI stills per
#     short and `layered_max_hero_scenes` (1) fully-layered scene — extra hero
#     stacks are demoted to a single background plane (→ simple render).
#   • RAM + TIMEOUT GUARDS: skip generation when free RAM is below the floor or a
#     still exceeds the timeout — degrade to footage/reuse, never block.
# No-op unless layered_render. Backward compatible: only touches scenes that the
# Storyboard Agent already gave a `layers` list.
async def resolve_layers(graph: SceneGraph, spec: VideoSpec) -> SceneGraph:
    s = settings()
    if not s.layered_render:
        return graph

    budget = max(0, int(s.layered_ai_still_budget))     # unique AI stills allowed
    heroes_left = max(0, int(s.layered_max_hero_scenes))
    gen_cache: dict[tuple[str, int], str] = {}           # (prompt, seed) → path (reuse)
    used: set[str] = set()                               # unique generated stills

    # Beats that draw their own frames. The renderer composites the clip these
    # produce and never runs the layer stack over it, so generating a layer asset
    # for one is pure waste: an image is fetched or synthesised, written to cache,
    # recorded in the scene graph, and then never appears on screen. That is
    # exactly what happened on the NYC short — a photoreal portrait generated for
    # a kinetic-typography beat, billed and discarded.
    SELF_RENDERING = {"motion_gfx", "threejs", "dataviz", "branded"}

    skipped: list[str] = []
    for idx, scene in enumerate(graph.scenes):
        layers = scene.visual.layers
        if not layers:
            continue
        if scene.visual.type in SELF_RENDERING:
            scene.visual.layers = []          # drop the plan so nothing downstream retries
            skipped.append(scene.id)
            continue
        roles = {ly.role for ly in layers}
        is_hero = ("subject" in roles or "fx" in roles)  # full stack vs light bg
        if is_hero:
            if heroes_left <= 0:                         # render-budget cap: 1 hero
                scene.visual.layers = [ly for ly in layers
                                       if ly.role == "background"][:1]
                print(f"[layers] {scene.id}: hero budget spent → demoted to a "
                      f"single background plane (simple render)", flush=True)
                continue
            heroes_left -= 1
        budget = await _resolve_scene_layers(scene, idx, graph, spec, budget,
                                             gen_cache, used)

    if skipped:
        print(f"[layers] skipped {len(skipped)} self-rendering beat(s) "
              f"({', '.join(skipped)}) — they draw their own frames, so no asset "
              "is generated for them", flush=True)
    if used:
        print(f"[layers] used {len(used)}/{s.layered_ai_still_budget} AI still "
              f"budget across the short ({len(gen_cache)} unique prompts)", flush=True)
    return graph


async def _resolve_scene_layers(scene: Scene, idx: int, graph: SceneGraph,
                                spec: VideoSpec, budget: int,
                                gen_cache: dict[tuple[str, int], str],
                                used: set[str]) -> int:
    """Resolve every layer of one scene to a real file; return remaining AI budget."""
    s = settings()
    for layer in scene.visual.layers:
        # 1) already resolved (cache hit / pre-seeded / earlier reuse) → keep it.
        if _existing(layer):
            continue

        # 2) fx plane — resolve the bare texture name (asset_path OR query) against
        #    data/assets/fx/.
        if layer.role == "fx":
            name = (layer.asset_path or layer.query or "").strip()
            cand = s.data_dir / "assets" / "fx" / name
            layer.asset_path = str(cand) if (name and cand.exists()) else None
            continue

        # 3) AI image plane — cache-first generation under the hard budget.
        if layer.kind == "ai_image" and spec.allow_ai_image:
            prompt, seed = _layer_prompt_seed(layer, scene, graph)
            key = (prompt, seed)
            if key in gen_cache:                         # identical layer already made
                layer.asset_path = gen_cache[key]        # FREE reuse (character lock)
                continue
            # budget / RAM / timeout guards BEFORE spending CPU on a new still.
            if len(used) >= budget:
                print(f"[layers] {scene.id}/{layer.role}: AI budget reached "
                      f"({budget}) → using footage instead", flush=True)
            elif not ram.budget_ok(s.layered_min_free_mb):
                print(f"[layers] {scene.id}/{layer.role}: free RAM "
                      f"{ram.available_mb():.0f}MB < floor → skip generation, "
                      f"use footage", flush=True)
            else:
                img = await _gen_layer_still(prompt, seed, scene, layer, graph)
                if img:
                    gen_cache[key] = img
                    used.add(img)
                    layer.asset_path = img
                    continue
            # generation skipped/failed → fall through to footage for this plane.

        # 4) footage / image / unresolved plane — reuse the scene's already-resolved
        #    main asset when it's real footage (cheapest), else a grounded search.
        layer.asset_path = _reuse_or_search(layer, scene, graph, idx)
    return budget


def _existing(layer: Layer) -> bool:
    p = (layer.asset_path or "").strip()
    return bool(p and Path(p).exists())


def _layer_prompt_seed(layer: Layer, scene: Scene, graph: SceneGraph) -> tuple[str, int]:
    """The grounded generation prompt + deterministic seed for an AI layer. A
    SUBJECT layer bound to a character uses that character's LOCKED seed +
    description (stable across scenes/runs → consistency + cache reuse)."""
    story_key = graph.meta.video_id or graph.meta.title
    base = (layer.prompt or scene.visual.visual_intent or scene.visual.query
            or " ".join(scene.visual.broll_keywords[:4]) or scene.narration)
    if layer.role == "subject" and layer.character and settings().character_memory:
        ref = char.get_or_create(story_key, layer.character, base)
        prompt = layer.prompt or char.character_prompt(ref, base)
        return prompt, ref.seed
    return base, idx_seed(story_key, layer.role)


def idx_seed(story_key: str, role: str) -> int:
    """Deterministic non-character seed (stable across runs → cache reuse)."""
    import hashlib
    h = hashlib.sha1(f"{story_key}:{role}".encode()).hexdigest()
    return int(h, 16) % (2 ** 31)


async def _gen_layer_still(prompt: str, seed: int, scene: Scene, layer: Layer,
                           graph: SceneGraph) -> str | None:
    """Generate (or cache-hit) one AI still for a layer, with a timeout guard.
    Returns the path or None (→ caller degrades to footage). Never raises."""
    import asyncio
    try:
        return await asyncio.wait_for(
            ai_image_generate(prompt, graph.meta.video_id,
                              f"{scene.id}:{layer.role}", seed=seed),
            timeout=settings().layered_ai_timeout_s,
        )
    except asyncio.TimeoutError:
        print(f"[layers] {scene.id}/{layer.role}: generation exceeded "
              f"{settings().layered_ai_timeout_s:.0f}s timeout → footage", flush=True)
        return None
    except Exception as e:  # noqa: BLE001
        print(f"[layers] {scene.id}/{layer.role}: generation failed "
              f"({type(e).__name__}: {str(e)[:80]}) → footage", flush=True)
        return None


def _reuse_or_search(layer: Layer, scene: Scene, graph: SceneGraph,
                     idx: int) -> str | None:
    """Cheapest grounded footage for a non-AI plane: REUSE the scene's resolved
    real asset when present, else run the grounded footage/photo search."""
    v = scene.visual
    if v.asset_path and v.type in ("broll", "image") and Path(v.asset_path).exists():
        return v.asset_path                              # reuse — no extra search
    return None  # NOTE: live footage search for layer planes is intentionally not
    # run here — a light beat is a single background plane that the compositor
    # falls back to a simple render for anyway, and the scene's own asset (set by
    # resolve_assets) already covers it. Kept as a hook for future per-plane search.
