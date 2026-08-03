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

from pathlib import Path

from ..brand import load_theme
from ..brand.theme import BrandTheme
from ..config import settings
from ..schemas.scene import Layer, Scene, SceneGraph
from ..schemas.video_spec import VideoSpec
from . import character as char
from . import dataviz
from . import motiongfx
from . import ram
from . import scene_director as sd
from . import asset_engine
from . import finance_motion
from . import threejs_engine
from .providers import (
    ai_image_generate, ai_video_generate, build_video_prompt,
    clamp_i2v_seconds, clamp_insert_seconds, manim_render, pexels_image,
    pexels_video, picsart_image_to_video, pixabay_image, pixabay_video,
    multi_source_candidates, download_asset_candidate,
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
    return load_theme(graph.brand_id or "k70")


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


async def resolve_assets(graph: SceneGraph, spec: VideoSpec) -> SceneGraph:
    # 1) decide the per-scene strategy + enforce the visual-mix budget.
    report = sd.decide(graph, spec)
    by_id = {d.scene_id: d for d in report.decisions}
    if ((settings().multi_source_asset_engine_enabled
         or settings().threejs_visual_engine_enabled
         or settings().motion_graphics_engine_enabled)
            and graph.storyboard is None):
        from . import storyboard
        graph.storyboard = storyboard.generate_semantic(graph, report)

    enhanced: dict[str, str] = {}
    if settings().multi_source_asset_engine_enabled:
        enhanced = await asset_engine.resolve(
            graph, multi_source_candidates, download_asset_candidate)
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
            else:
                scene.visual.asset_path = None
                scene.visual.type = "solid"

    motion_handled: set[str] = set()
    if settings().motion_graphics_engine_enabled and graph.storyboard is not None:
        by_source: dict[str, list] = {}
        for beat in graph.storyboard.scenes:
            by_source.setdefault(beat.source_scene_id, []).append(beat)
        for index, scene in enumerate(graph.scenes):
            if scene.id in enhanced:
                continue
            beat = next((candidate for candidate in by_source.get(scene.id, [])
                         if finance_motion.map_template(candidate) is not None), None)
            if beat is None:
                continue
            result = await finance_motion.render(
                graph, scene, beat, quality=settings().motion_graphics_quality,
                seed=index)
            graph.motion_graphics_provenance.append(result)
            motion_handled.add(scene.id)
            if result.status in ("rendered", "cache_hit") and result.render_path:
                scene.visual.asset_path = result.render_path
                scene.visual.type = "motion_gfx"
                scene.visual.motion = "none"
            else:
                scene.visual.asset_path = None
                scene.visual.type = "solid"

    threejs_handled: set[str] = set()
    if settings().threejs_visual_engine_enabled and graph.storyboard is not None:
        by_source: dict[str, list] = {}
        for beat in graph.storyboard.scenes:
            by_source.setdefault(beat.source_scene_id, []).append(beat)
        for scene in graph.scenes:
            # Official/licensed Phase 3 assets keep priority; Three.js should
            # explain numbers, not replace strong archival evidence.
            if scene.id in enhanced or scene.id in motion_handled:
                continue
            beat = next((candidate for candidate in by_source.get(scene.id, [])
                         if threejs_engine.map_template(candidate) is not None), None)
            if beat is None:
                continue
            result = await threejs_engine.render(graph, scene, beat)
            graph.threejs_provenance.append(result)
            threejs_handled.add(scene.id)
            if result.status in ("rendered", "cache_hit") and result.render_path:
                scene.visual.asset_path = result.render_path
                scene.visual.type = "threejs"
                scene.visual.motion = "none"
            else:
                # A failed clarity-specific visual is an editorially unresolved
                # scene, never permission to substitute unrelated stock.
                scene.visual.asset_path = None
                scene.visual.type = "solid"

    if settings().multi_source_asset_engine_enabled:
        return graph

    if (settings().threejs_visual_engine_enabled
            or settings().motion_graphics_engine_enabled):
        locally_handled = threejs_handled | motion_handled
        await asyncio.gather(
            *[_resolve(s, i, graph, spec, by_id[s.id])
              for i, s in enumerate(graph.scenes) if s.id not in locally_handled]
        )
        if settings().strict_visuals:
            await _dedupe_real_assets(graph)
        return graph
    # 2) resolve every scene to a concrete asset (concurrently).
    await asyncio.gather(
        *[_resolve(s, i, graph, spec, by_id[s.id])
          for i, s in enumerate(graph.scenes)]
    )
    # 3) STRICT: never the SAME real clip twice — re-pick duplicates to a different,
    #    still-on-topic shot. AI images are already unique per prompt+seed.
    if settings().strict_visuals:
        await _dedupe_real_assets(graph)
    return graph


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
            headline = next((o.text for o in scene.overlays
                             if o.type == "headline"), "") or v.visual_intent \
                or scene.narration
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
    if settings().strict_visuals:
        narr = scene.narration
        km = _INTENT_MOTION.get(v.scene_visual_type, "ken_burns")

        async def _try(terms: list[str]) -> bool:
            """Try real footage then photo for one tier; set asset on a hit."""
            terms = _strip_cliches(terms, narr)        # anti-cliché guard
            hit = await _video(terms, min_dur, pick)
            if hit:
                v.asset_path, v.type = hit, "broll"
                return True
            hit = await _image(terms, pick)
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
    vid = await _video(terms, min_dur, pick)
    if vid:
        v.asset_path, v.type = vid, "broll"
        return

    # real PHOTO — Pexels then Pixabay, with Ken Burns motion (realism tier).
    photo = await _image(terms, pick)
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


async def _video(terms: list[str], min_dur: float, pick: int) -> str | None:
    """Real-footage VIDEO: Pexels then Pixabay (priority tiers 1+2)."""
    return (
        await _first_hit(lambda t, p: pexels_video(t, min_dur, p), terms, pick)
        or await _first_hit(lambda t, p: pixabay_video(t, min_dur, p), terms, pick)
    )


async def _image(terms: list[str], pick: int) -> str | None:
    """Real-footage PHOTO: Pexels then Pixabay (realism tier, gets Ken Burns)."""
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

    for idx, scene in enumerate(graph.scenes):
        layers = scene.visual.layers
        if not layers:
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
