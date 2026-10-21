"""K70 P3 Intelligent Documentary Editor — non-destructive whole-film editorial intelligence.

Runs on SceneGraph JSON, standard library only. Never rewrites the original,
fetches assets, changes the frozen 14 layers, renders, or calls AI providers.
Untrusted semantic hints are labeled suggestions, not visual truth.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from typing import Any, Mapping

_WORD = re.compile(r"[a-z][a-z0-9'-]*", re.I)
_NUMBER = re.compile(r"(?<!\w)(?:[$€£]\s*)?\d[\d,.]*(?:\s*(?:%|percent|million|billion))?", re.I)
_STOP = frozenset("""the a an and or to of in on is was were are be as with which what why how for from by it this that they their his her we our you your at into out not can did when then over under only just than have has had will would could should one more much many use using about""".split())
_GENERIC = ("business meeting", "financial growth", "corporate handshake",
            "generic business", "generic finance", "stock market footage",
            "trading floor stock", "random money", "generic rich businessman",
            "hoodie hacker", "random city", "abstract numbers")
_DATA_ROLES = {"data", "evidence", "statistics", "proof", "comparison", "chart"}
_MECHANISM = re.compile(r"\b(how|mechanism|works|flow|system|process|why|means|explains|function)\b", re.I)
_GEO = re.compile(r"\b(japan|india|china|germany|russia|france|united kingdom|britain|argentina|zimbabwe|indonesia|thailand|maryland|new hampshire|netherlands|switzerland|california|florida|new york|usa|united states|america)\b", re.I)
_DOLLAR = re.compile(r"\b(us dollars?|usd|american dollars?|dollar bills?|federal reserve)\b", re.I)
_NON_US_CURRENCY = re.compile(r"\b(euro banknotes?|rupee banknotes?|yen banknotes?|pound sterling banknotes?|indian currency|euros? notes?|russian rubles?)\b", re.I)
_RELEVANT = frozenset({"stock","stocks","money","finance","financial","market","markets","economy","economic","history","world","people","global","business","bank","banks","price","prices","value","change","changes","growth","abstract"})
_PRESERVE_TYPES = frozenset({"threejs", "ai_video", "dataviz"})
_MOTION_TYPES = frozenset({"motion_gfx", "branded", "solid"})
_CINEMATIC = frozenset({"ai_video"})
# Lexical narration/visual comparison only means something for footage-like
# visuals chosen by a search query; cards, charts and 3D show authored content.
_FOOTAGE_TYPES = frozenset({"broll", "image", "ai_image", "ai_video", "stock", "footage"})
_TRANSITIONS = frozenset({"cut", "crossfade", "fade", "slide_l", "whip", "dip_to_black", "push_up"})
_REVEALS = frozenset({"reveal", "turning_point", "resolution", "chapter", "turn", "conclusion", "contrast"})
# A named subject (a year or a proper noun after the first word) that a generic
# stock clip cannot truthfully depict: the right person, place or event matters.
_YEAR = re.compile(r"\b(1[6-9]\d\d|20\d\d)s?\b")
_PROPER = re.compile(r"(?<=[a-z,] )[A-Z][a-z]{2,}")  # capitalised mid-clause
_BREAK = ("first", "now", "however", "but the", "then", "that changed", "the problem")


def _tokens(text: str) -> set[str]:
    return {x for x in _WORD.findall(text.lower()) if len(x) >= 4 and x not in _STOP}


def _object(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _seconds(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError("scene durations must be numeric") from None
    if not 0.0 < result < 3600.0:
        raise ValueError("scene durations must be positive and finite")
    return result


def _chart_ready(scene: Mapping[str, Any]) -> bool:
    data = _object(scene.get("data"))
    pts = data.get("points")
    return (isinstance(pts, list) and bool(pts) and
            all(isinstance(p, Mapping) and
                isinstance(p.get("value"), (float, int)) and
                not isinstance(p.get("value"), bool) for p in pts) and
            bool(str(data.get("source") or "").strip()))


def _is_locked(scene: Mapping[str, Any]) -> bool:
    visual = _object(scene.get("visual"))
    return bool(visual.get("asset_path") or visual.get("layers") or
                visual.get("type") in _PRESERVE_TYPES)


def _semantic(scene: Mapping[str, Any]) -> dict[str, Any]:
    text = str(scene.get("narration") or "").strip()
    visual = _object(scene.get("visual"))
    visual_type = str(visual.get("type") or "unknown")
    role = str(scene.get("beat_role") or "").lower().strip()
    query = str(visual.get("query") or "")
    intents = str(visual.get("visual_intent") or "")
    reasons = []
    flags = []
    if _chart_ready(scene):
        best = "dataviz"
        reasons.append("scene has sourced numeric series")
    elif _NUMBER.search(text):
        best = "evidence_review"
        reasons.append("numerical claim needs a verified data/chart decision")
        if not _object(scene.get("data")).get("source"):
            flags.append("numeric_claim_without_chart_source_review")
    elif _GEO.search(text):
        best = "subject_specific_footage"
        reasons.append("narration names a geography; show the exact location/event")
        if visual_type not in _PRESERVE_TYPES:
            flags.append("threejs_map_candidate_only_if_geo_and_render_budget_allow")
    elif role in _DATA_ROLES:
        best = "evidence_review"
        reasons.append("evidence beat needs its exact cited chart or primary document")
    elif role in _REVEALS or _MECHANISM.search(text):
        best = "mechanism_diagram"
        reasons.append("abstract mechanism needs a meaningful finance explanation")
    else:
        best = "subject_specific_footage"
        reasons.append("prefer an exact subject or documentary source, not filler")

    # A recommendation NEVER silently demotes an actual 3D, cinematic or chart.
    if _is_locked(scene):
        flags.append("protected_existing_visual_keep")
    if visual_type in _MOTION_TYPES:
        flags.append("possible_fullscreen_text_card")
    searchable = f"{query} {intents}".lower().strip()
    if any(term in searchable for term in _GENERIC):
        flags.append("generic_visual_query_review")
    if (_DOLLAR.search(text) and _NON_US_CURRENCY.search(searchable) and
            not _NON_US_CURRENCY.search(text)):
        flags.append("possible_us_currency_visual_mismatch")
    # Narrow lexical warning, only for meaningful detailed queries. Do not
    # mistake a loose keyword match for a factual hallucination.
    relevant = _tokens(text) - _RELEVANT
    shown = _tokens(searchable) - _RELEVANT
    if (visual_type in _FOOTAGE_TYPES and len(relevant) >= 2 and
            len(shown) >= 2 and not (relevant & shown)):
        flags.append("narration_visual_terms_differ_review")
    if _chart_ready(scene) and visual_type != "dataviz":
        flags.append("sourced_chart_not_shown")
    return {"recommendation": best, "why": reasons,
            "protected": _is_locked(scene), "flags": flags}


def _transition(scene: Mapping[str, Any], idx: int,
                prev_role: str) -> tuple[str, str]:
    if idx == 0:
        return "cut", "opening frame should be immediate"
    old = str(scene.get("transition_in") or "cut")
    if old != "cut":
        return old, "preserve authored transition"
    role = str(scene.get("beat_role") or "").lower().strip()
    text = str(scene.get("narration") or "").strip().lower()
    if role in _REVEALS and role != prev_role:
        return "crossfade", "meaningful editorial chapter/argument transition"
    if any(text.startswith(s) for s in _BREAK) and role != prev_role:
        return "crossfade", "sentence explicitly introduces a distinct development"
    return "cut", "keep factual explanation fast and legible"


def graph_fingerprint(graph: Mapping[str, Any]) -> str:
    """Stable binding of editorial recommendations to the exact source graph."""
    raw = json.dumps(graph, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def plan_documentary(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Review the whole film, preserve timing and authored rendered assets."""
    if not isinstance(graph, Mapping):
        raise ValueError("SceneGraph must be an object")
    scenes = graph.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("SceneGraph requires nonempty scenes")
    if any(not isinstance(s, Mapping) for s in scenes):
        raise ValueError("SceneGraph scenes must be objects")
    ids = [str(s.get("id") or "") for s in scenes]
    if any(not sid for sid in ids) or len(set(ids)) != len(ids):
        raise ValueError("scene IDs must be unique and nonempty")
    duration = sum(_seconds(s.get("duration_sec")) for s in scenes)
    if duration > 7200:
        raise ValueError("supported editorial timeline is at most two hours")
    mix = Counter()
    quarters = [Counter() for _ in range(4)]
    issues = []
    records = []
    start = 0.0
    prev_role = ""
    streak: list[str] = []
    streak_seconds = 0.0
    max_streak = {"count": 0, "duration_sec": 0.0, "ids": []}
    for i, scene in enumerate(scenes):
        length = _seconds(scene.get("duration_sec"))
        visual = _object(scene.get("visual"))
        kind = str(visual.get("type") or "unknown")
        mid = start + length / 2
        q = min(3, int(mid / duration * 4))
        mix[kind] += length
        quarters[q][kind] += length
        sem = _semantic(scene)
        transition, transition_reason = _transition(scene, i, prev_role)
        sid = ids[i]
        if kind in _MOTION_TYPES:
            streak.append(sid)
            streak_seconds += length
        else:
            if len(streak) >= 4 or streak_seconds >= 25:
                issues.append({"severity": "review", "code": "repetitive_card_run",
                               "scene_ids": list(streak), "duration_sec": round(streak_seconds, 2),
                               "suggestion": "replace eligible abstract cards with relevant diagrams, citations or actual footage"})
            if len(streak) > max_streak["count"]:
                max_streak = {"count": len(streak), "duration_sec": round(streak_seconds, 2), "ids": list(streak)}
            streak, streak_seconds = [], 0.0
        for flag in sem["flags"]:
            if flag in ("generic_visual_query_review",
                        "possible_us_currency_visual_mismatch",
                        "narration_visual_terms_differ_review",
                        "numeric_claim_without_chart_source_review",
                        "sourced_chart_not_shown"):
                issues.append({"severity": "review", "code": flag, "scene_ids": [sid]})
        records.append({
            "scene_id": sid, "index": i, "start_sec": round(start, 2),
            "duration_sec": round(length, 2), "quarter": q + 1,
            "existing_visual": kind, "suggested_visual_intent": sem["recommendation"],
            "visual_protected": sem["protected"], "rationale": sem["why"],
            "review_flags": sem["flags"], "current_transition": scene.get("transition_in", "cut"),
            "suggested_transition": transition, "transition_reason": transition_reason,
            "requires_asset_or_editor_approval_for_visual_change": True,
        })
        prev_role = str(scene.get("beat_role") or "").lower().strip()
        start += length
    if len(streak) >= 4 or streak_seconds >= 25:
        issues.append({"severity": "review", "code": "repetitive_card_run",
                       "scene_ids": list(streak), "duration_sec": round(streak_seconds, 2),
                       "suggestion": "insert exact evidence/footage/diagrams, not generic B-roll"})
    if len(streak) > max_streak["count"]:
        max_streak = {"count": len(streak), "duration_sec": round(streak_seconds, 2), "ids": list(streak)}
    cinematic = [round(q.get("ai_video", 0.0), 2) for q in quarters]
    if sum(cinematic) > 0 and sum(1 for n in cinematic if n > 0) < 3:
        issues.append({"severity": "review", "code": "cinematics_clustered",
                       "scene_ids": [r["scene_id"] for r in records if r["existing_visual"] == "ai_video"],
                       "suggestion": "consider whole-film distribution without removing fact charts"})
    if len(scenes) >= 20 and sum(x in _MOTION_TYPES for x in [str(_object(s.get("visual")).get("type") or "") for s in scenes]) / len(scenes) > 0.40:
        issues.append({"severity": "review", "code": "too_many_fullscreen_cards",
                       "scene_ids": [], "suggestion": "prefer source-grounded diagrams, maps and actual footage"})
    issues.extend(_film_issues(graph, scenes, ids))
    report = {
        "version": "K70-P3-EDITOR-v1",
        "mode": "read_only_semantic_editorial_plan",
        "source_graph_sha256": graph_fingerprint(graph),
        "documentary_title": str(_object(graph.get("meta")).get("title") or ""),
        "scene_count": len(scenes), "duration_sec": round(duration, 2),
        "existing_visual_seconds": {key: round(val, 2) for key, val in sorted(mix.items())},
        "visual_mix_by_quarter_sec": [
            {key: round(val, 2) for key, val in sorted(row.items())}
            for row in quarters
        ],
        "cinematic_seconds_by_quarter": cinematic,
        "longest_consecutive_card_run": max_streak,
        "decisions": records, "review_issues": issues,
        "issue_counts": dict(sorted(Counter(x["code"] for x in issues).items())),
        "guardrails": {
            "frozen_layers_untouched": True, "existing_media_unchanged": True,
            "no_paid_api_or_generation": True, "visuals_are_recommendations_only": True,
            "future_threejs_requires_budget_and_valid_existing_engine": True,
            "note": "Text-based relevance flags are heuristic, not video inspections.",
        }
    }
    return report


def _film_issues(graph: Mapping[str, Any], scenes: list, ids: list[str]) -> list[dict]:
    """Whole-film checks: reused media, transition monotony, policy rewrites."""
    issues = []
    used: dict[str, list[str]] = {}
    for sid, scene in zip(ids, scenes):
        path = str(_object(scene.get("visual")).get("asset_path") or "")
        if path:
            used.setdefault(path, []).append(sid)
    for path, owners in used.items():
        if len(owners) > 1:
            issues.append({"severity": "review", "code": "duplicate_visual_asset",
                           "scene_ids": owners, "asset_path": path})
    moves = Counter(str(s.get("transition_in") or "cut") for s in scenes[1:])
    if len(scenes) >= 20:
        kind, count = max(moves.items(), key=lambda kv: (kv[1], kv[0]))
        if kind != "cut" and count / (len(scenes) - 1) > 0.5:
            issues.append({"severity": "review", "code": "transition_monotony",
                           "scene_ids": [], "transition": kind, "count": count,
                           "suggestion": "reserve soft transitions for chapter/argument turns; "
                                         "hard cuts keep factual explanation crisp"})
    resolved: dict[str, str] = {}
    provenance = graph.get("asset_provenance")
    for row in provenance if isinstance(provenance, list) else []:
        row = _object(row)
        if row.get("status") == "resolved" and row.get("selected_source_url"):
            resolved.setdefault(str(row.get("scene_id") or "").split(".", 1)[0],
                                str(row["selected_source_url"]))
    for sid, scene in zip(ids, scenes):
        visual = _object(scene.get("visual"))
        if visual.get("type") != "broll" or visual.get("budget_channel") not in ("stock", "ai_broll"):
            continue
        if sid in resolved:
            issues.append({"severity": "review", "code": "resolved_archival_source_not_used",
                           "scene_ids": [sid], "source_url": resolved[sid],
                           "suggestion": "use the licensed archival asset, not a stock substitute"})
        queries = [str(visual.get("query") or "")] + [
            str(_object(layer).get("query") or "") for layer in visual.get("layers") or []]
        if any(_YEAR.search(q) or _PROPER.search(q) for q in queries):
            issues.append({"severity": "review", "code": "named_subject_on_generic_stock",
                           "scene_ids": [sid],
                           "suggestion": "a stock clip cannot show this specific person/place/event; "
                                         "verify the frame or use archival/diagram"})
    notes = _object(graph.get("meta")).get("compliance_notes") or []
    for note in notes if isinstance(notes, list) else []:
        sid = str(note).split(":", 1)[0].strip()
        if sid in ids:
            issues.append({"severity": "review", "code": "compliance_rewrite_changed_narration",
                           "scene_ids": [sid], "note": str(note),
                           "suggestion": "confirm the policy rewrite kept the factual meaning"})
    return issues


def compare_graphs(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict:
    """Read-only diff of two versions of one film: what the later pass changed."""
    def index(graph: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        scenes = graph.get("scenes")
        if not isinstance(scenes, list) or any(not isinstance(s, Mapping) for s in scenes):
            raise ValueError("comparison requires SceneGraphs with scene objects")
        return {str(s.get("id") or ""): s for s in scenes}
    old, new = index(baseline), index(candidate)
    narration, swaps, lost_charts, lost_protected = [], Counter(), [], []
    for sid, before in old.items():
        after = new.get(sid)
        if after is None:
            continue
        if str(before.get("narration") or "").strip() != str(after.get("narration") or "").strip():
            narration.append({"scene_id": sid, "before": before.get("narration"),
                              "after": after.get("narration")})
        a = str(_object(before.get("visual")).get("type") or "unknown")
        b = str(_object(after.get("visual")).get("type") or "unknown")
        if a != b:
            swaps[f"{a}->{b}"] += 1
            if a == "dataviz" and _chart_ready(before):
                lost_charts.append(sid)
            if a in ("threejs", "ai_video"):
                lost_protected.append(sid)
    return {
        "same_scene_order": list(old) == list(new),
        "missing_scene_ids": [sid for sid in old if sid not in new],
        "added_scene_ids": [sid for sid in new if sid not in old],
        "narration_changed": narration,
        "visual_type_changes": dict(sorted(swaps.items())),
        "sourced_charts_replaced": lost_charts,
        "authored_3d_or_cinematic_replaced": lost_protected,
    }


def safe_transition_copy(graph: Mapping[str, Any], report: Mapping[str, Any]) -> dict:
    """Opt-in editorial copy for UNRENDERED drafts; never overwrite inputs.

    Only 'cut' -> 'crossfade' is allowed for ordinary unrendered scenes.
    An unrendered text fallback with actual authored sourced numeric points
    may also become 'dataviz'. Existing footage, 3D and cinematic inserts stay
    unchanged. A film with voiceover, captions, provenance or resolved media
    is refused to protect synchronization and editorial source integrity.
    """
    if report.get("source_graph_sha256") != graph_fingerprint(graph):
        raise ValueError("editorial report does not match exact source graph")
    if graph.get("captions") or graph.get("sfx"):
        raise ValueError("refuse editorial edits after captions/SFX authoring")
    if any(graph.get(k) for k in ("asset_provenance", "threejs_provenance",
                                 "motion_graphics_provenance", "ai_broll_provenance",
                                 "paperima_provenance", "brand_identity_provenance")):
        raise ValueError("refuse editorial edits after asset/render provenance exists")
    audio = _object(graph.get("audio"))
    if any(audio.get(k) for k in ("voiceover_path", "music_path", "music_bed_path")):
        raise ValueError("refuse transition edits after audio exists")
    scenes = graph.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("invalid source SceneGraph")
    if any(_object(s.get("visual")).get("asset_path") or
           _object(s.get("visual")).get("layers") for s in scenes):
        raise ValueError("refuse transition edits on resolved media/layer scenes")
    decisions = report.get("decisions")
    if not isinstance(decisions, list) or [d.get("scene_id") for d in decisions] != [
            s.get("id") for s in scenes]:
        raise ValueError("report does not match source scene IDs")
    result = copy.deepcopy(graph)
    for scene, decision in zip(result["scenes"], decisions):
        old = scene.get("transition_in", "cut")
        proposed = decision.get("suggested_transition")
        if old not in _TRANSITIONS or proposed not in _TRANSITIONS:
            raise ValueError("unrecognized transition type")
        kind = str(_object(scene.get("visual")).get("type") or "")
        # Only chart-ready *fallback* cards can be promoted. Existing authored
        # footage, 3D, cinematic inserts, and evidence charts are never demoted.
        if kind in _MOTION_TYPES and _chart_ready(scene):
            scene["visual"]["type"] = "dataviz"
            scene["visual"]["strategy"] = "dataviz"
            kind = "dataviz"
        if (old == "cut" and proposed == "crossfade" and
                kind not in _PRESERVE_TYPES):
            scene["transition_in"] = "crossfade"
    return result


def review_markdown(report: Mapping[str, Any],
                    comparison: Mapping[str, Any] | None = None) -> str:
    rows = [
        "# K70 P3 — Intelligent Documentary Editorial Review", "",
        f"**Scenes:** {report['scene_count']} · **Duration:** {report['duration_sec']:.1f}s",
        "", "## Visual distribution (seconds)", "",
        "| Visual | Whole film | Q1 | Q2 | Q3 | Q4 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    alltypes = sorted(set(report["existing_visual_seconds"]) |
                      {k for row in report["visual_mix_by_quarter_sec"] for k in row})
    for kind in alltypes:
        secs = report["existing_visual_seconds"].get(kind, 0)
        q = [v.get(kind, 0) for v in report["visual_mix_by_quarter_sec"]]
        rows.append(f"| {kind} | {secs:.1f} | {q[0]:.1f} | {q[1]:.1f} | {q[2]:.1f} | {q[3]:.1f} |")
    rows.extend(["", "## Editorial review issues", ""])
    for issue in report["review_issues"]:
        ids = ", ".join(issue["scene_ids"][:12]) or "whole film"
        rows.append(f"- **{issue['code']}** ({ids})"
                    + (f" — {issue['suggestion']}" if issue.get("suggestion") else ""))
    if not report["review_issues"]:
        rows.append("- No issues detected by the limited text/timeline heuristics.")
    if comparison:
        rows.extend(["", "## Changes versus baseline graph", "",
            f"- Same scene order: {comparison['same_scene_order']}",
            f"- Missing / added scenes: {len(comparison['missing_scene_ids'])} / "
            f"{len(comparison['added_scene_ids'])}",
            f"- Visual type changes: {comparison['visual_type_changes'] or 'none'}",
            f"- Sourced charts replaced: {', '.join(comparison['sourced_charts_replaced']) or 'none'}",
            f"- Authored 3D/cinematic replaced: "
            f"{', '.join(comparison['authored_3d_or_cinematic_replaced']) or 'none'}",
            f"- Narration changed: {len(comparison['narration_changed'])} scene(s)"])
        for row in comparison["narration_changed"]:
            rows.append(f"  - {row['scene_id']}: \"{row['before']}\" → \"{row['after']}\"")
    rows.extend(["", "## Safety", "",
        "This is an editorial **recommendation**, not fact verification or a render.",
        "Existing visuals, 3D assets, AI clips, charts, TTS, captions and the frozen",
        "14-layer pipeline were not touched. False-positive text relevance warnings",
        "must be reviewed by an editor before changing media.",
    ])
    return "\n".join(rows) + "\n"
