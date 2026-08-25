"""
Existing-topic and video deduplication against the topic ledger.

Two layers, both required:
  1. EXACT — deterministic canonical hash over the (factual_state, token-set) of
     the topic. Cheap, zero false positives, long window (default 365 days).
  2. SEMANTIC — blended similarity over canonical topics, hooks and angles inside
     a shorter window (default 90 days).

A rejected topic can still be produced when:
  * a materially NEW event has occurred since the previous run (a confirmed event
    supersedes an earlier forecast/expectation about the same thing), or
  * the proposed angle is substantially different, or
  * an administrator passes an explicit override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .clustering import text_similarity
from .models import FactualState, TopicCandidate
from .normalizer import canonical_key
from .repository import TopicIntelligenceRepository
from .settings import ti_settings
from .tables import TopicLedger

# Ledger rows in these states block reuse: already committed to, in flight, or
# explicitly turned down by a reviewer.
#   selected  — chosen by a run, awaiting review
#   queued    — approved and handed to the pipeline
#   rendering / published — in flight or shipped
#   rejected  — a reviewer said no (Phase 2B); re-surfacing it tomorrow would just
#               re-ask a question that was already answered. `abandoned` remains
#               deliberately NON-blocking: it means "replaced", not "refused".
BLOCKING_STATUSES = ("selected", "queued", "rendering", "published", "rejected")


@dataclass
class DedupVerdict:
    status: str = "new"          # new | duplicate | recent_semantic | superseded
    reasons: list[str] = field(default_factory=list)
    matched_topic_id: str | None = None
    similarity: float = 0.0
    blocked: bool = False


def _state_supersedes(new: FactualState, old: str) -> bool:
    """A confirmed event is materially new information relative to the forecast or
    expectation that preceded it — that is a legitimate second video."""
    return new is FactualState.confirmed and old in {
        FactualState.forecast.value,
        FactualState.expectation.value,
        FactualState.rumour.value,
        FactualState.unknown.value,
    }


def check_candidate(
    candidate: TopicCandidate,
    ledger: list[TopicLedger],
    *,
    proposed_angle: str = "",
    override: bool = False,
) -> DedupVerdict:
    s = ti_settings()
    now = datetime.now(timezone.utc)
    v = DedupVerdict()

    key = canonical_key(candidate.canonical_topic, candidate.factual_state)
    exact_cutoff = now.timestamp() - s.topic_exact_dedup_days * 86400
    semantic_cutoff = now.timestamp() - s.topic_semantic_dedup_days * 86400

    for row in ledger:
        if row.status not in BLOCKING_STATUSES:
            continue
        sel = row.selected_at
        if sel is not None and sel.tzinfo is None:
            sel = sel.replace(tzinfo=timezone.utc)
        ts = sel.timestamp() if sel else 0.0

        # --- layer 1: exact ---
        if ts >= exact_cutoff and (
            row.topic_id == candidate.topic_id or (row.canonical_key and row.canonical_key == key)
        ):
            if _state_supersedes(candidate.factual_state, row.factual_state):
                v.status, v.matched_topic_id, v.similarity = "superseded", row.topic_id, 1.0
                v.reasons.append(
                    f"supersedes ledger topic {row.topic_id} "
                    f"({row.factual_state} -> {candidate.factual_state.value}): "
                    "materially new event"
                )
                continue
            v.status, v.blocked = "duplicate", True
            v.matched_topic_id, v.similarity = row.topic_id, 1.0
            v.reasons.append(
                f"exact duplicate of ledger topic {row.topic_id} "
                f"(status={row.status}, within {s.topic_exact_dedup_days}d)"
            )
            break

        # --- layer 2: semantic ---
        if ts < semantic_cutoff:
            continue
        sim = text_similarity(candidate.canonical_topic, row.canonical_topic)
        if sim >= s.topic_similarity_threshold:
            if _state_supersedes(candidate.factual_state, row.factual_state):
                v.status = "superseded"
                v.matched_topic_id, v.similarity = row.topic_id, sim
                v.reasons.append(
                    f"semantically similar to {row.topic_id} (sim={sim:.2f}) but the "
                    "event is now confirmed — materially new"
                )
                continue
            angle_sim = (
                text_similarity(proposed_angle, row.proposed_angle)
                if proposed_angle and row.proposed_angle else 1.0
            )
            if angle_sim < s.angle_similarity_threshold:
                v.status = "recent_semantic"
                v.matched_topic_id, v.similarity = row.topic_id, sim
                v.reasons.append(
                    f"similar to recent topic {row.topic_id} (sim={sim:.2f}) but the "
                    f"angle differs (angle_sim={angle_sim:.2f}) — allowed, penalized"
                )
                continue
            v.status, v.blocked = "recent_semantic", True
            v.matched_topic_id, v.similarity = row.topic_id, sim
            v.reasons.append(
                f"semantic duplicate of {row.topic_id} (sim={sim:.2f} >= "
                f"{s.topic_similarity_threshold}) within "
                f"{s.topic_semantic_dedup_days}d; angle also repeats "
                f"(angle_sim={angle_sim:.2f})"
            )
            break

        # --- repeated hook / repeated title, independent of topic similarity ---
        if row.hook_concept and candidate.canonical_topic:
            hook_sim = text_similarity(candidate.canonical_topic, row.hook_concept)
            if hook_sim >= s.angle_similarity_threshold:
                v.reasons.append(
                    f"hook repeats ledger entry {row.topic_id} (sim={hook_sim:.2f})"
                )

    if override and v.blocked:
        v.blocked = False
        v.reasons.append("ADMIN OVERRIDE: rejection explicitly overridden")
    return v


def apply_dedup(
    candidates: list[TopicCandidate],
    *,
    channel_id: str,
    repo: TopicIntelligenceRepository,
    override_topic_ids: set[str] | None = None,
) -> list[TopicCandidate]:
    """Annotate every candidate with its dedup verdict and drop hard blocks.

    Also de-duplicates WITHIN the run: two clusters that collapse to the same
    canonical key keep only the better-sourced one.
    """
    s = ti_settings()
    override_topic_ids = override_topic_ids or set()
    window = max(s.topic_exact_dedup_days, s.topic_semantic_dedup_days)
    ledger = repo.ledger_entries(channel_id, days=window, statuses=BLOCKING_STATUSES)

    seen_keys: dict[str, TopicCandidate] = {}
    kept: list[TopicCandidate] = []
    for c in candidates:
        key = canonical_key(c.canonical_topic, c.factual_state)
        prior = seen_keys.get(key)
        if prior is not None:
            # Same story clustered twice — merge evidence into the stronger one.
            winner = prior if prior.source_count >= c.source_count else c
            loser = c if winner is prior else prior
            winner.evidence.extend(loser.evidence)
            winner.source_names = sorted(set(winner.source_names) | set(loser.source_names))
            winner.source_count = max(winner.source_count, loser.source_count)
            if winner is c:
                kept[kept.index(prior)] = c
                seen_keys[key] = c
            continue

        verdict = check_candidate(
            c, ledger, override=c.topic_id in override_topic_ids
        )
        c.dedup_status = verdict.status
        c.rejection_reasons.extend(verdict.reasons)
        if verdict.blocked:
            c.eligible_for_production = False
            continue
        seen_keys[key] = c
        kept.append(c)
    return kept
