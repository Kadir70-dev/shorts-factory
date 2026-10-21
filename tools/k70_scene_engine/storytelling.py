"""K70 P1 — research-grounded long-form finance storytelling planner.

Pre-production only. Does not edit a SceneGraph, narration, voiceover, captions,
the protected K70-PRODUCTION-v1.0 14-layer renderer, or existing jobs.
Python stdlib, fully deterministic and CPU/offline friendly.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


# These are proportions of the chosen duration, not hard-coded scene lengths.
# The chapters give the writer intent; the existing narration/TTS system owns
# the authoritative timeline. Questions/analogies are slots, never invented facts.
CHAPTERS = (
    ("cold_open", 0.00, 0.07, "Open on an evidenced contradiction or a concrete human stake.",
     "What makes the audience care right now?", "Introduce the central unanswered question."),
    ("roadmap", 0.07, 0.13, "Promise a clear what / how / who-it-affects journey.",
     "What exactly will the film explain?", "Name the mechanism the viewer will soon understand."),
    ("origin", 0.13, 0.28, "Show the historical setup with dates tied to trustworthy sources.",
     "Which assumption did people rely on?", "Reveal why that assumption became fragile."),
    ("mechanism", 0.28, 0.47, "Explain the causal mechanism using an accurate everyday analogy.",
     "How does this actually work?", "Identify the analogy's limitations and the real-world mechanism."),
    ("evidence", 0.47, 0.62, "Show specific sourced figures and distinguish data from interpretation.",
     "What does the evidence really show?", "Resolve the mechanism question using documented evidence."),
    ("turning_point", 0.62, 0.77, "Introduce a consequential decision, trade-off or counterargument.",
     "Who gained, who paid, and what changed?", "Address the strongest evidence-backed alternative view."),
    ("consequences", 0.77, 0.91, "Connect the system to a relatable life, bill, job or purchase.",
     "How does this affect an ordinary person?", "Connect stakes to the opening without claiming certainty."),
    ("resolution", 0.91, 1.00, "Resolve the central question and close with a nuanced takeaway.",
     "What can the viewer now explain for themselves?", "Answer the opening promise; never insert investment advice."),
)

# Not a classifier of meaning. These are conservative signals for editorial
# review; false positives and negatives must be acknowledged in the report.
_ANALOGY = re.compile(
    r"\b(?:imagine|picture this|think of (?:it|this) as|just like|"
    r"as if|similar to|for example|for instance|"
    r"the equivalent of|like a |like an )", re.IGNORECASE,
)
_ROADMAP = re.compile(
    r"\b(?:we(?:'|’)ll (?:look at|see|explore)|"
    r"first.{0,90}then|what.{0,90}how.{0,90}why|"
    r"here(?:'|’)s (?:how|what)|by the end)\b", re.IGNORECASE | re.DOTALL,
)
_ATTRIBUTION = re.compile(
    r"\b(?:according to|data (?:from|show|shows)|"
    r"research (?:by|from)|a report (?:from|by)|"
    r"(?:federal reserve|census bureau|bureau of labor statistics|"
    r"sec filings|imf|world bank) (?:data|figures|report))\b",
    re.IGNORECASE,
)
_NUMERIC_CLAIM = re.compile(r"(?<!\w)(?:[$€£]\s*)?\d[\d,.]*(?:\s*(?:%|percent|million|billion|trillion))?", re.I)


@dataclass(frozen=True)
class StoryBeat:
    key: str
    start_sec: float
    end_sec: float
    purpose: str
    question_to_answer: str
    payoff: str
    needs_evidence: bool = True
    analogy_slot: bool = False


def _s(seconds: float) -> float:
    return round(seconds, 2)


def _validate_duration(seconds: float) -> float:
    value = float(seconds)
    if not 240 <= value <= 1200:
        raise ValueError("P1 supports documentary durations from 4 to 20 minutes")
    return value


def build_plan(topic: str, *, duration_sec: float = 660,
               sources: Sequence[Mapping[str, str]] = (),
               audience: str = "general US finance audience") -> dict[str, Any]:
    """Generate a non-fiction editorial blueprint without fabricating evidence."""
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("a real, non-empty documentary topic is required")
    duration = _validate_duration(duration_sec)
    documented = []
    ids = set()
    for raw in sources:
        if not isinstance(raw, Mapping):
            raise ValueError("each source must be an object")
        sid = str(raw.get("id", "")).strip()
        title = str(raw.get("title", "")).strip()
        url = str(raw.get("url", "")).strip()
        if not sid or not title or sid in ids:
            raise ValueError("sources need unique non-empty id and title")
        if url and not re.match(r"^https?://", url, re.I):
            raise ValueError("source URLs must be HTTP(S)")
        ids.add(sid)
        documented.append({"id": sid, "title": title, "url": url,
                           "claim": str(raw.get("claim", "")).strip(),
                           "verification": "user_supplied_unverified"})
    beats = [
        StoryBeat(name, _s(duration * start), _s(duration * end),
                  purpose, question, payoff, analogy_slot=(name in ("mechanism", "consequences")))
        for name, start, end, purpose, question, payoff in CHAPTERS
    ]
    return {
        "version": "K70-P1-NARRATIVE-v1",
        "mode": "preproduction_only",
        "topic": topic.strip(), "audience": audience.strip(),
        "duration_sec": duration, "chapters": [asdict(b) for b in beats],
        "source_manifest": documented,
        "research_status": ("sources_supplied_not_independently_verified"
                            if documented else "RESEARCH_REQUIRED"),
        "editorial_contract": {
            "opening": "A researched specific stake; no invented quote, date or statistic.",
            "roadmap": "Offer what/how/impact within first 90 seconds.",
            "questions": "Target 4–7 meaningful questions answered later; not rhetorical filler.",
            "analogies": "Target 2–3 grounded everyday analogies, explicitly show limitations.",
            "evidence": "Tie numbers, dates and causal claims to verifiable sources.",
            "counterargument": "Include the strongest relevant evidence-backed alternative.",
            "reveal": "Every chapter makes progress on the opening question.",
            "end": "Resolve opening promise and explain remaining uncertainty.",
            "tone": "Original K70 documentary voice. No imitation of an identifiable creator.",
            "visual_semantics": {
                "AI_PIKA": "FEEL", "CHARTS_DATA": "PROVE",
                "SKETCH_VECTOR": "UNDERSTAND", "REAL_FOOTAGE_DOCUMENTS": "TRUST",
            },
            "architecture": "K70-PRODUCTION-v1.0 14 frozen layers; no reordering",
        },
    }


def write_director_brief(plan: Mapping[str, Any]) -> str:
    """Copy-ready scene-writing instructions, with no unsourced example figures."""
    duration = float(plan["duration_sec"])
    def stamp(sec: float) -> str:
        return f"{int(sec // 60):02}:{int(sec % 60):02}"
    lines = [
        "# K70 Finance — P1 Director Story Brief",
        "",
        f"**Topic:** {plan['topic']}",
        f"**Audience:** {plan['audience']}",
        f"**Editorial target:** {duration / 60:.1f} minutes (TTS owns real durations)",
        "",
        "Produce an ORIGINAL, source-grounded finance documentary. Follow this",
        "outline as narrative intent, not as a replacement for the locked renderer.",
        "Write conversational narration with earned suspense, specific stakes,",
        "mechanism explanations, chapter questions, evidence and honest payoffs.",
        "Never invent numbers, quotes, causal claims, source URLs or visuals.",
        "Preserve balanced interpretations where evidence is uncertain.",
        "Any analogy must have a real mapped mechanism and a limitation.",
        "Do not give individualized investment advice or impersonate any creator.",
        "",
        "## Chapter progression",
    ]
    for b in plan["chapters"]:
        lines.extend([
            "",
            f"### {stamp(b['start_sec'])}–{stamp(b['end_sec'])}: {b['key'].replace('_',' ').title()}",
            f"**Narrative job:** {b['purpose']}",
            f"**Question:** {b['question_to_answer']}",
            f"**Payoff:** {b['payoff']}",
            ("**Analogy:** Include one *only if* it models the mechanism accurately."
             if b["analogy_slot"] else "**Evidence:** Back factual claims with real sources."),
        ])
    lines.extend(["", "## Evidence policy"])
    sources = plan.get("source_manifest") or []
    if sources:
        for s in sources:
            lines.append(f"- [{s['id']}] {s['title']} — {s['url'] or '(URL not supplied)'}"
                         + (f" — proposed claim: {s['claim']}" if s["claim"] else ""))
        lines.append("")
        lines.append("These references are *supplied, not verified*. Read each primary")
        lines.append("source and verify the actual claim before using it.")
    else:
        lines.append("**STOP for research:** No sources supplied. Research credible")
        lines.append("primary documents and numerical series before drafting factual")
        lines.append("claims. This blueprint provides structure, NOT evidence.")
    lines.extend([
        "", "## No architecture changes",
        "Keep the frozen K70 14-layer production architecture, full captions,",
        "voiceover identity, evidence provenance and original output files intact.",
        "Do not reallocate chart/evidence scenes merely to add cinematics.",
    ])
    return "\n".join(lines) + "\n"


def _scene_seconds(scene: Mapping[str, Any]) -> float:
    try:
        return max(0.0, float(scene.get("duration_sec", 0)))
    except (TypeError, ValueError):
        return 0.0


def audit_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Text-only editorial QA on existing SceneGraph JSON. Never rewrites it."""
    scenes = graph.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("SceneGraph must contain a nonempty scenes array")
    if any(not isinstance(scene, Mapping) for scene in scenes):
        raise ValueError("each SceneGraph scene must be an object")
    duration = sum(_scene_seconds(s) for s in scenes)
    if duration <= 0:
        raise ValueError("SceneGraph scenes must have positive total duration")
    beginning = 0.0
    sampled = []
    questions = 0
    analogies = 0
    source_overlays = 0
    chart_sources = 0
    numeric_without_source = []
    segments = Counter()
    roadmap_candidates = []
    for scene in scenes:
        text = str(scene.get("narration") or "")
        sec = _scene_seconds(scene)
        sid = str(scene.get("id", f"scene-{len(sampled)}"))
        start, end = beginning, beginning + sec
        midpoint = (start + end) / 2
        beginning = end
        question_hits = text.count("?")
        analogy_hits = len(_ANALOGY.findall(text))
        questions += question_hits
        analogies += analogy_hits
        if start <= 90 and _ROADMAP.search(text):
            roadmap_candidates.append(sid)
        overlays = scene.get("overlays") or []
        has_source = any(
            isinstance(o, Mapping) and o.get("type") == "source" and
            str(o.get("text") or "").strip()
            for o in overlays
        )
        viz = scene.get("data")
        has_chart_source = isinstance(viz, Mapping) and bool(viz.get("source"))
        source_overlays += int(has_source)
        chart_sources += int(has_chart_source)
        if _NUMERIC_CLAIM.search(text) and not (
            has_source or has_chart_source or _ATTRIBUTION.search(text)
        ):
            numeric_without_source.append(sid)
        zone = min(3, int(4 * midpoint / duration))
        segments[zone] += question_hits
        sampled.append({"scene_id": sid, "start_sec": _s(start),
                        "end_sec": _s(end), "questions": question_hits,
                        "analogy_signals": analogy_hits, "source_visible": has_source,
                        "chart_source": has_chart_source})
    warnings = []
    if not any(s["start_sec"] < 45 and s["questions"] for s in sampled):
        warnings.append("opening_has_no_direct_question_heuristic")
    if not roadmap_candidates:
        warnings.append("no_obvious_roadmap_in_first_90s")
    if questions < 4:
        warnings.append("few_questions_for_longform")
    if analogies < 2:
        warnings.append("few_everyday_analogy_signals")
    if any(segments[i] == 0 for i in range(4)):
        warnings.append("one_or_more_quarters_without_questions")
    if numeric_without_source:
        warnings.append("numeric_claims_without_visible_source_or_attribution_need_review")
    return {
        "type": "text_only_heuristic_not_video_review",
        "scene_count": len(scenes), "estimated_duration_sec": _s(duration),
        "word_count": sum(len(str(s.get("narration") or "").split()) for s in scenes),
        "questions": questions, "analogy_signals": analogies,
        "roadmap_scene_ids": roadmap_candidates,
        "visible_source_overlay_scenes": source_overlays,
        "chart_source_scenes": chart_sources,
        "question_count_by_quarter": [segments[i] for i in range(4)],
        "numeric_claim_scene_ids_to_review": numeric_without_source,
        "warnings": warnings, "timeline": sampled,
        "caveat": "Heuristic signals; source metadata does not verify factual accuracy. "
                  "Needs human/editorial review and final rendered-video QA.",
    }


def write_audit_brief(audit: Mapping[str, Any]) -> str:
    lines = [
        "# K70 P1 — Existing Narration Editorial Review",
        "",
        f"- Duration estimate from SceneGraph: {audit['estimated_duration_sec']:.1f}s",
        f"- Narrated words: {audit['word_count']}",
        f"- Questions: {audit['questions']} (heuristic)",
        f"- Analogy cues: {audit['analogy_signals']} (heuristic)",
        f"- Question distribution Q1–Q4: {audit['question_count_by_quarter']}",
        f"- Source-credit overlays: {audit['visible_source_overlay_scenes']}",
        f"- Chart source fields: {audit['chart_source_scenes']}",
        "", "## Editorial issues",
    ]
    for issue in audit["warnings"]:
        lines.append(f"- {issue.replace('_', ' ')}")
    if not audit["warnings"]:
        lines.append("- None detected by the limited text heuristics.")
    if audit["numeric_claim_scene_ids_to_review"]:
        lines.extend([
            "",
            "## Numbers to check (not asserted false)",
            ", ".join(audit["numeric_claim_scene_ids_to_review"]),
        ])
    lines.extend([
        "", "## Safe next pass",
        "Treat this as editorial feedback, not a corrected script. Rework new",
        "narration BEFORE TTS and captions, and verify claims against original",
        "sources. Do not rewrite an already-voiced graph in place.",
    ])
    return "\n".join(lines) + "\n"
