"""
Visual Budget Manager — decides WHICH SOURCE fills each beat's screen time.

The problem it solves: the previous allocator reasoned one scene at a time, so
whichever channel matched first took the beat. On a data-heavy topic that meant
charts and kinetic type absorbed everything and a finished Short was ~100% flat
2D — technically correct per-scene, and monotonous as a whole. Budgeting is a
WHOLE-VIDEO decision; it cannot be made scene-locally.

How it works:

  1. ELIGIBILITY. Every scene is scored 0..1 against every channel from its own
     content — series data, geography, institutional sourcing, whether a camera
     could have been there, whether there is a line worth setting in type. The
     weights live in config/visual_budget.yaml, so retuning the look of the whole
     channel is a config edit.

  2. ALLOCATION. Channels are filled in `fill_order`, scarcest first, each taking
     its best-scoring unassigned scenes until it reaches its band's `lo`. A
     content-gated channel (official footage exists for this beat or it doesn't)
     must claim its beats before a channel that could have taken any beat.

  3. REMAINDER. Scenes nobody claimed go to their own best-scoring channel,
     subject to that band's `hi` ceiling.

Two guarantees fall out of the design rather than being checked afterwards:

  * ONE CHANNEL PER SCENE, so the reported mix sums to 100% and can never exceed
    it — there is no arithmetic that could overflow.
  * A scene assigned to a self-rendering channel (motion_gfx / threejs / charts)
    is never eligible for AI generation, because it already has its source. This
    is the structural fix for AI stills being generated and then discarded.

Bands are targets, not quotas. `Do NOT force exact percentages if the topic
doesn't support them` is implemented as `min_eligibility`: below that threshold a
channel leaves its band under-filled rather than putting a bad visual on screen.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..config import CONFIG_DIR
from ..schemas.scene import Scene, SceneGraph

_FILE = CONFIG_DIR / "visual_budget.yaml"

CHANNELS = ("motion_gfx", "threejs", "official", "ai_broll", "stock", "charts")

# `unresolved` is a REPORTING bucket, never an allocation target. It exists so a
# failed beat is visible instead of being folded into a real channel: an earlier
# version classified every unrecognised type as motion graphics, which reported
# 52% Motion Graphics for a render that was 39% blank frames. A breakdown that
# hides failures is worse than no breakdown.
UNRESOLVED = "unresolved"
REPORT_CHANNELS = CHANNELS + (UNRESOLVED,)

# Human labels for the delivered report.
LABEL = {
    "motion_gfx": "Motion Graphics (2D)",
    "threejs": "Three.js (3D)",
    "official": "Official/Public Domain",
    "ai_broll": "AI Cinematic B-roll",
    "stock": "Pexels/Pixabay",
    "charts": "Charts/Maps/Icons/Logos",
    UNRESOLVED: "UNRESOLVED (blank)",
}

# Which `Visual.type` each channel renders as, for the downstream resolver.
VISUAL_TYPE = {
    "motion_gfx": "motion_gfx",
    "threejs": "threejs",
    "official": "broll",
    "ai_broll": "ai_image",
    "stock": "broll",
    "charts": "dataviz",
}


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Band:
    lo: float
    hi: float


@dataclass
class Policy:
    bands: dict[str, Band]
    fill_order: tuple[str, ...]
    self_rendering: frozenset[str]
    stock_yields_to: tuple[str, ...]
    min_eligibility: float
    signals: dict[str, dict[str, float]]
    one_channel_per_scene: bool = True


_DEFAULT_BANDS = {
    "motion_gfx": Band(0.25, 0.35), "threejs": Band(0.15, 0.25),
    "official": Band(0.15, 0.25), "ai_broll": Band(0.15, 0.25),
    "stock": Band(0.10, 0.20), "charts": Band(0.10, 0.20),
}


@functools.lru_cache(maxsize=1)
def policy(path: Path | None = None) -> Policy:
    raw = yaml.safe_load((path or _FILE).read_text()) if (path or _FILE).exists() else {}
    bands = {k: Band(float(v["lo"]), float(v["hi"]))
             for k, v in (raw.get("bands") or {}).items()} or dict(_DEFAULT_BANDS)
    rules = raw.get("rules") or {}
    return Policy(
        bands=bands,
        fill_order=tuple(raw.get("fill_order") or CHANNELS),
        self_rendering=frozenset(rules.get("self_rendering")
                                 or ("motion_gfx", "threejs", "charts")),
        stock_yields_to=tuple(rules.get("stock_yields_to") or ()),
        min_eligibility=float(rules.get("min_eligibility", 0.35)),
        signals={k: {sk: float(sv) for sk, sv in (v or {}).items()}
                 for k, v in (raw.get("signals") or {}).items()},
        one_channel_per_scene=bool(rules.get("one_channel_per_scene", True)),
    )


# --------------------------------------------------------------------------- #
# Content signals — read off the scene, never off a hardcoded topic list
# --------------------------------------------------------------------------- #
_GEO = re.compile(
    r"\b(map|maps|city|cities|state|states|country|countries|region|border|"
    r"coast|island|continent|globe|world|route|district|borough|boroughs|"
    r"metro|county|skyline|geography|located|across the)\b", re.I)
_SCALE = re.compile(
    r"\b(bigger|larger|smaller|taller|height|size|scale|volume|stack|tower|"
    r"outproduce|out-produce|dwarf|times the|compared with|compared to|"
    r"the size of|as big as)\b", re.I)
_INSTITUTION = re.compile(
    r"\b(BEA|Bureau of Economic Analysis|BLS|Bureau of Labor|SEC|Federal Reserve|"
    r"the Fed|FOMC|Treasury|Census|CBO|IRS|FDIC|IMF|World Bank|OECD|Eurostat|"
    r"NASA|NOAA|WHO|United Nations|government|\.gov|10-K|10-Q|annual report|"
    r"investor relations|filing|filings|NYCEDC|comptroller)\b", re.I)
_CINEMATIC = re.compile(
    r"\b(recreation|reenact|re-enact|archival|historic|historical|century|"
    r"decade|era|1[89]\d0s|founding|collapse|crisis|boardroom|trading floor|"
    r"factory|shipyard|construction|skyline at night|aerial|drone|cinematic)\b",
    re.I)
_ABSTRACT = re.compile(
    r"\b(concept|idea|system|mechanism|invisible|hidden|why|because|reason|"
    r"means|density|network|flow|engine of|driver)\b", re.I)
_EVERYDAY = re.compile(
    r"\b(shopper|shoppers|grocery|checkout|street|streets|commute|commuter|"
    r"office|offices|worker|workers|crowd|crowds|traffic|subway|restaurant|"
    r"cafe|store|shop|queue|line of people|pedestrian)\b", re.I)


def _text(s: Scene) -> str:
    v = s.visual
    return " ".join(filter(None, [
        s.narration, v.visual_intent, v.query,
        " ".join(v.broll_keywords or []), " ".join(s.keywords or []),
        " ".join(o.text or "" for o in s.overlays),
        " ".join((o.sub or "") for o in s.overlays),
        (s.data.title if s.data else ""), (s.data.source if s.data else ""),
    ]))


def _has_data(s: Scene) -> bool:
    return bool(s.data and s.data.valid())


def eligibility(scene: Scene, pol: Policy | None = None) -> dict[str, float]:
    """Score one scene 0..1 against every channel, from its own content."""
    p = pol or policy()
    sig = p.signals
    t = _text(scene)
    words = len(scene.narration.split())
    n_points = len(scene.data.points) if scene.data else 0
    has_terms = bool(scene.visual.broll_keywords)
    numeric = bool(re.search(r"\d", scene.narration))

    def g(channel: str, key: str, cond: bool) -> float:
        return sig.get(channel, {}).get(key, 0.0) if cond else 0.0

    out: dict[str, float] = {}

    out["charts"] = max(
        g("charts", "has_series_data", _has_data(scene)),
        g("charts", "numeric_narration", numeric and not _has_data(scene)))

    out["threejs"] = max(
        g("threejs", "comparable_series", _has_data(scene) and n_points >= 3),
        g("threejs", "geographic", bool(_GEO.search(t))),
        g("threejs", "scale_concept", bool(_SCALE.search(t))),
        g("threejs", "has_series_data", _has_data(scene)))

    out["official"] = max(
        g("official", "institutional_source", bool(_INSTITUTION.search(t))),
        g("official", "named_institution", bool(_INSTITUTION.search(scene.narration))),
        g("official", "historical_event", bool(_CINEMATIC.search(t))))

    out["ai_broll"] = max(
        g("ai_broll", "cinematic_subject", bool(_CINEMATIC.search(t))),
        g("ai_broll", "historical_recreation",
          bool(re.search(r"\b(1[89]\d0s|recreation|archival|historic)\b", t, re.I))),
        g("ai_broll", "abstract_concept", bool(_ABSTRACT.search(t))),
        g("ai_broll", "concrete_unfilmable",
          bool(_CINEMATIC.search(t)) and not bool(_EVERYDAY.search(t))))

    out["stock"] = max(
        g("stock", "everyday_subject", bool(_EVERYDAY.search(t))),
        g("stock", "has_search_terms", has_terms))

    out["motion_gfx"] = max(
        g("motion_gfx", "showable_line", 3 <= words <= 18),
        g("motion_gfx", "no_filmable_subject", not has_terms),
        # Universal floor. Guarantees every scene has at least one eligible
        # channel, so allocation always completes and the mix always sums to 100%.
        sig.get("motion_gfx", {}).get("baseline", 0.35))

    return {k: round(min(1.0, v), 3) for k, v in out.items()}


# --------------------------------------------------------------------------- #
# Allocation
# --------------------------------------------------------------------------- #
@dataclass
class Assignment:
    scene_id: str
    channel: str
    seconds: float
    score: float
    reason: str
    scores: dict[str, float] = field(default_factory=dict)


@dataclass
class BudgetReport:
    assignments: list[Assignment]
    seconds: dict[str, float]
    pct: dict[str, float]
    bands: dict[str, Band]
    total_seconds: float
    notes: list[str] = field(default_factory=list)

    def within_band(self, channel: str) -> bool:
        b = self.bands.get(channel)
        return b is not None and b.lo <= self.pct.get(channel, 0.0) / 100.0 <= b.hi

    def scenes_for(self, channel: str) -> list[str]:
        return [a.scene_id for a in self.assignments if a.channel == channel]

    def format(self) -> str:
        lines = [f"visual budget · {self.total_seconds:.2f}s across "
                 f"{len(self.assignments)} scenes"]
        for ch in REPORT_CHANNELS:
            if ch == UNRESOLVED and not self.seconds.get(ch):
                continue
            pct = self.pct.get(ch, 0.0)
            b = self.bands.get(ch)
            target = f"{b.lo*100:.0f}-{b.hi*100:.0f}%" if b else "n/a"
            mark = "OK " if self.within_band(ch) else "-- "
            ids = ",".join(self.scenes_for(ch)) or "—"
            lines.append(f"  [{mark}] {LABEL[ch]:24} {pct:5.1f}%  "
                         f"(target {target:>7})  {self.seconds.get(ch,0.0):5.2f}s  {ids}")
        lines.append(f"  {'total':30} {sum(self.pct.values()):5.1f}%")
        for n in self.notes:
            lines.append(f"  note: {n}")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "total_seconds": round(self.total_seconds, 3),
            "channels": {
                ch: {"label": LABEL[ch], "percent": round(self.pct.get(ch, 0.0), 2),
                     "seconds": round(self.seconds.get(ch, 0.0), 3),
                     "scenes": self.scenes_for(ch),
                     "target_lo": self.bands[ch].lo if ch in self.bands else None,
                     "target_hi": self.bands[ch].hi if ch in self.bands else None,
                     "within_band": self.within_band(ch)}
                for ch in REPORT_CHANNELS},
            "assignments": [
                {"scene_id": a.scene_id, "channel": a.channel,
                 "seconds": round(a.seconds, 3), "score": a.score,
                 "reason": a.reason, "scores": a.scores}
                for a in self.assignments],
            "notes": self.notes,
        }


def allocate(graph: SceneGraph, pol: Policy | None = None) -> BudgetReport:
    """Assign every scene exactly one visual channel and report the real mix."""
    p = pol or policy()
    scenes = list(graph.scenes)
    total = sum(s.duration_sec for s in scenes) or 1.0
    scores = {s.id: eligibility(s, p) for s in scenes}
    by_id = {s.id: s for s in scenes}

    assigned: dict[str, str] = {}
    used_sec: dict[str, float] = {c: 0.0 for c in CHANNELS}
    notes: list[str] = []

    def take(scene_id: str, channel: str) -> None:
        assigned[scene_id] = channel
        used_sec[channel] += by_id[scene_id].duration_sec

    # -- Phase 1: fill each band to `lo`, scarcest channels first ------------ #
    for ch in p.fill_order:
        band = p.bands.get(ch)
        if band is None:
            continue
        target = band.lo * total
        # Stock only takes a beat that nothing better wanted.
        candidates = []
        for s in scenes:
            if s.id in assigned:
                continue
            sc = scores[s.id][ch]
            if sc < p.min_eligibility:
                continue
            if ch == "stock" and _stock_yields(s, sc, scores, used_sec, p, total):
                continue
            candidates.append((sc, s.duration_sec, s.id))
        candidates.sort(reverse=True)
        for sc, dur, sid in candidates:
            if used_sec[ch] >= target:
                break
            if used_sec[ch] + dur > band.hi * total and used_sec[ch] > 0:
                continue                     # would blow the ceiling
            take(sid, ch)

    # -- Phase 2: remaining scenes go to their own best channel under `hi` --- #
    for s in scenes:
        if s.id in assigned:
            continue
        ranked = sorted(scores[s.id].items(), key=lambda kv: -kv[1])
        placed = False
        for ch, sc in ranked:
            band = p.bands.get(ch)
            if band is None or sc < p.min_eligibility:
                continue
            if ch == "stock" and _stock_yields(s, sc, scores, used_sec, p, total):
                continue
            if used_sec[ch] + s.duration_sec > band.hi * total and used_sec[ch] > 0:
                continue
            take(s.id, ch)
            placed = True
            break
        if not placed:
            # Every band is at its ceiling. motion_gfx is the universal floor —
            # better an on-brand typographic beat than an unassigned scene.
            take(s.id, "motion_gfx")
            notes.append(f"{s.id}: all bands at ceiling → motion_gfx floor")

    # -- Phase 3: swap-improvement ------------------------------------------ #
    # Greedy fill is order-dependent and stranding is its characteristic failure:
    # a channel hits its ceiling on a merely-adequate beat, and the beat that
    # scored 1.00 for it arrives too late and drops to a weak fallback. On the
    # first NYC run that put the flagship five-way comparison (charts 1.00,
    # threejs 0.90) onto motion_gfx at 0.70.
    #
    # Fixing the fill order can't solve this in general — any fixed order strands
    # something on some topic. A pairwise swap pass does: it keeps the band shape
    # the greedy pass achieved (swapping two scenes only moves seconds when their
    # durations differ) while letting scenes migrate to the channel that actually
    # suits them. Bounded and cheap at this scene count.
    _improve(scenes, assigned, scores, used_sec, p, total)

    assignments = []
    for s in scenes:
        ch = assigned[s.id]
        sc = scores[s.id][ch]
        assignments.append(Assignment(
            scene_id=s.id, channel=ch, seconds=s.duration_sec, score=sc,
            reason=_reason(s, ch, sc), scores=scores[s.id]))

    seconds = {c: round(sum(a.seconds for a in assignments if a.channel == c), 3)
               for c in CHANNELS}
    pct = {c: round(100.0 * seconds[c] / total, 2) for c in CHANNELS}

    for ch in CHANNELS:
        b = p.bands.get(ch)
        if b and pct[ch] / 100.0 < b.lo:
            eligible = sum(1 for s in scenes if scores[s.id][ch] >= p.min_eligibility)
            notes.append(
                f"{LABEL[ch]} under target ({pct[ch]:.1f}% < {b.lo*100:.0f}%) — "
                f"only {eligible}/{len(scenes)} scenes support it on this topic")

    return BudgetReport(assignments=assignments, seconds=seconds, pct=pct,
                        bands=p.bands, total_seconds=total, notes=notes)


def _stock_yields(scene: Scene, stock_score: float,
                  scores: dict[str, dict[str, float]], used_sec: dict[str, float],
                  p: Policy, total: float) -> bool:
    """Should this beat give way to a better source than stock?

    "Never use stock when official assets or better custom visuals exist" means
    a better channel must ACTUALLY be able to take the beat. Comparing raw scores
    alone is too strong: on a city topic the `geographic` signal scores Three.js
    0.85 almost everywhere, so stock yielded to a channel that was already at its
    ceiling and could never claim the scene — and the band sat at 0% while real
    support shots went unused.
    """
    for other in p.stock_yields_to:
        if scores[scene.id].get(other, 0.0) <= stock_score:
            continue
        band = p.bands.get(other)
        if band is None:
            return True
        # only yield if that channel has room to actually take this scene
        if used_sec.get(other, 0.0) + scene.duration_sec <= band.hi * total:
            return True
    return False


def _improve(scenes, assigned: dict[str, str], scores: dict[str, dict[str, float]],
             used_sec: dict[str, float], p: Policy, total: float,
             max_passes: int = 12) -> None:
    """Hill-climb the assignment by swapping pairs of scenes between channels.

    Accepts a swap only when it raises the summed eligibility AND leaves both
    affected channels no worse against their bands than before — so it can never
    trade a good mix for a good score.
    """
    by_id = {s.id: s for s in scenes}

    def band_penalty(ch: str, secs: float) -> float:
        b = p.bands.get(ch)
        if b is None:
            return 0.0
        share = secs / total
        if share < b.lo:
            return b.lo - share
        if share > b.hi:
            return share - b.hi
        return 0.0

    for _ in range(max_passes):
        best = None
        ids = list(assigned)
        for i, a_id in enumerate(ids):
            for b_id in ids[i + 1:]:
                ca, cb = assigned[a_id], assigned[b_id]
                if ca == cb:
                    continue
                # scenes must be eligible for the channel they'd move to
                if (scores[a_id][cb] < p.min_eligibility
                        or scores[b_id][ca] < p.min_eligibility):
                    continue
                gain = ((scores[a_id][cb] + scores[b_id][ca])
                        - (scores[a_id][ca] + scores[b_id][cb]))
                if gain <= 1e-9:
                    continue
                da, db = by_id[a_id].duration_sec, by_id[b_id].duration_sec
                new_a = used_sec[ca] - da + db
                new_b = used_sec[cb] - db + da
                before = band_penalty(ca, used_sec[ca]) + band_penalty(cb, used_sec[cb])
                after = band_penalty(ca, new_a) + band_penalty(cb, new_b)
                if after > before + 1e-9:
                    continue                 # would worsen the mix
                score = gain - (after - before)
                if best is None or score > best[0]:
                    best = (score, a_id, b_id, ca, cb, new_a, new_b)
        if best is None:
            return
        _, a_id, b_id, ca, cb, new_a, new_b = best
        assigned[a_id], assigned[b_id] = cb, ca
        used_sec[ca], used_sec[cb] = new_a, new_b


def _reason(scene: Scene, channel: str, score: float) -> str:
    if channel == "charts":
        return f"carries series data ({len(scene.data.points)} points)" \
            if scene.data else "states a figure"
    if channel == "threejs":
        return "comparable series / geography / scale — reads better in 3D"
    if channel == "official":
        return "institutional source available for this claim"
    if channel == "ai_broll":
        return "cinematic subject no camera could have captured"
    if channel == "stock":
        return "everyday subject, nothing better available"
    return "the line itself carries the beat"


def apply(graph: SceneGraph, report: BudgetReport) -> SceneGraph:
    """Write the allocation onto the graph so the resolver honours it.

    `visual.strategy` becomes the contract the asset resolver reads. A scene on a
    self-rendering channel also gets its `visual.type` set, which is what makes it
    ineligible for AI generation downstream.
    """
    p = policy()
    for a in report.assignments:
        scene = next(s for s in graph.scenes if s.id == a.scene_id)
        scene.visual.strategy = a.channel if a.channel in (
            "motion_gfx", "threejs", "dataviz") else scene.visual.strategy
        scene.visual.budget_channel = a.channel
        scene.visual.decision_reason = f"[budget] {a.reason}"
        if a.channel in p.self_rendering:
            scene.visual.type = VISUAL_TYPE[a.channel]
            # Nothing is fetched or generated for a self-rendering beat, so drop
            # any layer plan that would otherwise trigger generation.
            scene.visual.layers = []
    return graph


# --------------------------------------------------------------------------- #
# Unused-asset audit
# --------------------------------------------------------------------------- #
def measure(graph: SceneGraph) -> BudgetReport:
    """The DELIVERED mix, classified from what actually resolved on disk.

    Deliberately NOT `allocate()` re-run. The allocator is deterministic from
    scene content, so re-running it after the render reproduces the PLAN and
    reports it as though it shipped — which is how the first version of this
    report claimed 15.8% Three.js and 12.8% stock for a video that contained
    neither. A breakdown that restates intent is worse than no breakdown.

    Classification is by resolved `visual.type`, then by the provenance of the
    file the renderer actually consumed.
    """
    p = policy()
    total = sum(s.duration_sec for s in graph.scenes) or 1.0
    assignments: list[Assignment] = []

    for s in graph.scenes:
        v = s.visual
        path = (v.asset_path or "").lower()
        if v.type == "dataviz":
            ch, why = "charts", "rendered by the local chart engine"
        elif v.type == "threejs":
            ch, why = "threejs", "rendered by the Three.js worker"
        elif v.type == "motion_gfx":
            ch, why = "motion_gfx", "kinetic typography"
        elif v.type == "branded":
            ch, why = "motion_gfx", "branded plate (no external source)"
        elif v.type in ("ai_image", "ai_video"):
            ch, why = "ai_broll", "AI-generated"
        elif v.type in ("broll", "image"):
            if any(k in path for k in ("pexels", "pixabay")):
                ch, why = "stock", "stock library"
            elif any(k in path for k in ("wikimedia", "commons", "gov", "sec_",
                                         "company_ir", "public_domain")):
                ch, why = "official", "official / public-domain source"
            else:
                ch, why = "stock", "footage of unrecorded provenance"
        elif v.type == "papercraft":
            # Paper Craft only ever substitutes WITHIN a beat already allocated
            # to "official" or "charts" (pipeline/papercraft/beat_detect.py) —
            # "official" is the more accurate long-term label for a laid-out
            # document either way. Without this branch a real, on-disk Scribus
            # render fell through to the catch-all below and reported as
            # UNRESOLVED (blank) — a real render mis-reported as a failure.
            ch, why = "official", "rendered by the Scribus Paper Craft engine"
        elif v.type == "solid" or not v.asset_path:
            # No asset on disk = nothing on screen. Counted honestly.
            ch, why = UNRESOLVED, f"no asset resolved (type={v.type})"
        else:
            ch, why = UNRESOLVED, f"unrecognised visual type ({v.type})"
        assignments.append(Assignment(
            scene_id=s.id, channel=ch, seconds=s.duration_sec,
            score=0.0, reason=why,
            scores={"planned": v.budget_channel or "-"}))

    seconds = {c: round(sum(a.seconds for a in assignments if a.channel == c), 3)
               for c in REPORT_CHANNELS}
    pct = {c: round(100.0 * seconds[c] / total, 2) for c in REPORT_CHANNELS}

    notes: list[str] = []
    drift = [(a.scene_id, a.scores["planned"], a.channel) for a in assignments
             if a.scores["planned"] not in ("", "-", a.channel)]
    for sid, planned, actual in drift:
        notes.append(f"{sid}: planned {planned} → delivered {actual} "
                     "(resolver could not supply the planned source)")

    return BudgetReport(assignments=assignments, seconds=seconds, pct=pct,
                        bands=p.bands, total_seconds=total, notes=notes)


def audit_unused(graph: SceneGraph) -> list[str]:
    """Assets attached to a scene that the renderer will never composite.

    A self-rendering beat draws its own frames, so any layer asset hanging off it
    was generated and thrown away. This is the check that keeps the AI-generation
    bug from silently returning.
    """
    p = policy()
    stale: list[str] = []
    for s in graph.scenes:
        if s.visual.type not in ("motion_gfx", "threejs", "dataviz", "branded"):
            continue
        for ly in s.visual.layers:
            if ly.asset_path:
                stale.append(f"{s.id}:{ly.role}:{Path(ly.asset_path).name}")
    return stale
