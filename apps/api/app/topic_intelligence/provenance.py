"""
Provenance: the evidence bundle that travels with a decision.

The bundle answers "why did we make this video?" without needing the database:
which providers ran, what they returned, which sources supported the winner, what
the model was asked and answered, and what the score was made of. It is attached
to the VideoSpec handed to the Director, so a finished job retains the evidence
used to select its topic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import RankedTopic, SelectionResult, TopicCandidate

BUNDLE_VERSION = "1"


def evidence_bundle(
    result: SelectionResult,
    topic: RankedTopic,
    candidate: TopicCandidate | None,
) -> dict[str, Any]:
    """A self-contained, JSON-serializable record of the selection decision."""
    return {
        "bundle_version": BUNDLE_VERSION,
        "run_id": result.run_id,
        "channel_id": result.channel_id,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "ranking_version": result.ranking_version,
        "prompt_version": result.prompt_version,
        "ranker_used": result.ranker_used,
        "gemini_model": result.gemini_model,
        "topic": {
            "topic_id": topic.topic_id,
            "canonical_topic": topic.canonical_topic,
            "proposed_angle": topic.proposed_angle,
            "target_viewer": topic.target_viewer,
            "hook_concept": topic.hook_concept,
            "why_now": topic.why_now,
            "confidence": topic.confidence,
            "expires_at": topic.expires_at.isoformat() if topic.expires_at else None,
            "recommended_publish_window": (
                topic.recommended_publish_window.isoformat()
                if topic.recommended_publish_window else None
            ),
            "factual_state": candidate.factual_state.value if candidate else None,
            "event_type": candidate.event_type.value if candidate else None,
            "asset_classes": (
                [a.value for a in candidate.asset_classes] if candidate else []
            ),
            "tickers": candidate.tickers if candidate else [],
        },
        "scores": topic.scores.model_dump(),
        "score_explanation": topic.score_explanation,
        "risk_flags": topic.risk_flags,
        "rejection_reasons": topic.rejection_reasons,
        "eligible_for_production": topic.eligible_for_production,
        "evidence": [
            {
                "provider": e.provider,
                "title": e.title,
                "url": e.url,
                "external_id": e.external_id,
                "published_at": e.published_at.isoformat() if e.published_at else None,
                "collected_at": e.collected_at.isoformat(),
                "source_tier": e.source_tier.value,
                "source_credibility": e.source_credibility,
                "metrics": e.metrics,
                "grounded": e.grounded,
                "grounding_complete": e.grounding_complete,
            }
            for e in topic.supporting_evidence
        ],
        "measured_metrics": candidate.metrics if candidate else {},
        "source_names": topic.source_names,
        "source_count": topic.source_count,
        "independent_source_count": (
            candidate.independent_source_count if candidate else 0
        ),
        "providers": [p.model_dump() for p in result.providers],
        "funnel": {
            "raw_signals": result.raw_signal_count,
            "clusters": result.cluster_count,
            "finalists": result.finalist_count,
        },
        "cost": result.cost.model_dump(),
        "warnings": result.warnings,
        "runner_up_topic_ids": [
            r.topic_id for r in result.ranked if r.topic_id != topic.topic_id
        ][:5],
    }


def summarize(result: SelectionResult) -> str:
    """One-screen human summary — printed by the CLI, logged by the API."""
    lines = [
        f"run {result.run_id}  channel={result.channel_id}  status={result.status}",
        f"  funnel: {result.raw_signal_count} raw -> {result.cluster_count} clusters "
        f"-> {result.finalist_count} finalists",
        f"  ranker: {result.ranker_used}"
        + (f" (model={result.gemini_model})" if result.gemini_model else "")
        + f"  cost=${result.cost.estimated_usd:.6f}"
        f" tokens={result.cost.input_tokens}in/{result.cost.output_tokens}out",
    ]
    for p in result.providers:
        state = (
            "ok" if p.ok else
            ("circuit-open" if p.circuit_open else
             (p.skipped_reason or p.error or "failed"))
        )
        stale = " [STALE]" if p.stale else ""
        lines.append(f"  provider {p.name:<20} {p.signal_count:>4} signals  {state}{stale}")
    if result.selected:
        t = result.selected
        lines.append(f"  SELECTED [{t.scores.overall_score:.1f}] {t.canonical_topic}")
        lines.append(f"    angle: {t.proposed_angle}")
        lines.append(f"    hook : {t.hook_concept}")
        lines.append(f"    why  : {t.why_now}")
        lines.append(f"    conf : {t.confidence:.2f}  sources: {t.source_count} "
                     f"({', '.join(t.source_names)})")
        if t.risk_flags:
            lines.append(f"    risks: {', '.join(t.risk_flags)}")
    else:
        lines.append(f"  NO TOPIC SELECTED ({result.status})")
    for r in result.ranked[1:6]:
        lines.append(f"  runner-up [{r.scores.overall_score:5.1f}] {r.canonical_topic[:70]}")
    for w in result.warnings[:10]:
        lines.append(f"  warn: {w}")
    return "\n".join(lines)
