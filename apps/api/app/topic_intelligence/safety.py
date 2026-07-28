"""
Finance safety gate — CODE-level, not prompt-level.

This runs before Gemini sees a candidate and again after Gemini returns, so a
model that ignores its instructions cannot smuggle an unsafe topic through.
Anything the gate blocks is `eligible_for_production = False`, full stop.

Two severities:
  * BLOCKING  — the topic can never win (advice, guarantees, manipulation).
  * PENALTY   — allowed but scored down (rumour-only sourcing, thin evidence,
                sensational phrasing, unverifiable numbers).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import FactualState, SourceTier, TopicCandidate

# --------------------------------------------------------------------------- #
# Blocking patterns
# --------------------------------------------------------------------------- #
BLOCKING_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("guaranteed_profit", re.compile(
        r"\b(guaranteed?|risk[- ]free|can'?t lose|sure thing|100% (win|profit|return)|"
        r"never lose|always profit|foolproof)\b", re.I),
        "guaranteed-profit claim"),
    ("financial_advice", re.compile(
        r"\b(buy (now|today|this|it)|sell (now|today|this|it)|you should (buy|sell|invest)|"
        r"load up on|all[- ]in on|dump your|put your (money|savings|401k))\b", re.I),
        "direct personalized financial advice / buy-sell recommendation"),
    ("pump_and_dump", re.compile(
        r"\b(to the moon|next 100x|next 1000x|10x overnight|pump it|moonshot|"
        r"get in before|before it explodes|last chance to buy)\b", re.I),
        "pump-and-dump framing"),
    ("manipulation_allegation", re.compile(
        r"\b(market (is )?rigged|banks are manipulating|secretly manipulat\w+|"
        r"suppressing the price|naked shorting scam|the fed is lying)\b", re.I),
        "unsupported market-manipulation allegation"),
    ("insider_trading", re.compile(
        r"\b(insider (info|tip|trade|trading) (leak|available)|non[- ]public information|"
        r"trade on inside|leaked earnings before)\b", re.I),
        "illegal insider-trading implication"),
    ("prediction_as_fact", re.compile(
        r"\b(will (crash|collapse|double|triple|hit \$?\d)|is going to (crash|zero|moon)|"
        r"guaranteed to (rise|fall)|definitely (crash|rally))\b", re.I),
        "prediction presented as fact"),
    ("named_individual_attack", re.compile(
        r"\b(\w+ (is a )?(fraud|criminal|scammer|liar|crook)|exposed as a (fraud|scam))\b",
        re.I),
        "sensational claim about a named individual"),
]

# --------------------------------------------------------------------------- #
# Penalty patterns
# --------------------------------------------------------------------------- #
PENALTY_RULES: list[tuple[str, re.Pattern[str], str, float]] = [
    ("misleading_certainty", re.compile(
        r"\b(everyone knows|obviously|without a doubt|certain to|inevitable)\b", re.I),
        "misleading certainty", 12.0),
    ("sensational", re.compile(
        r"\b(shocking|insane|you won'?t believe|nobody is talking about|"
        r"they don'?t want you to know|the truth about)\b", re.I),
        "sensational framing", 10.0),
    ("unverified_price", re.compile(
        r"\b(price target|fair value is|worth \$\d|will be worth)\b", re.I),
        "price claim requiring verification", 8.0),
    ("breaking_unsourced", re.compile(r"\b(breaking|just in|urgent)\b", re.I),
        "breaking-news framing", 6.0),
    # Personal-finance advice columns ("I'm 71 and inherited $20,000 — what should
    # I do?"). Safe to read, but retelling one is one step from giving the advice
    # ourselves, so it is heavily demoted rather than promoted.
    ("advice_column", re.compile(
        r"(\bI'?m \d{2}\b|\bmy (financial )?(adviser|advisor|husband|wife|parents)\b"
        r"|what should I do with|should I (buy|sell|invest|retire)"
        r"|\bmy \$[\d,.]+ ?(million|k\b)?)", re.I),
        "personal-finance advice-column framing", 30.0),
]


@dataclass
class SafetyVerdict:
    risk_flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    risk_penalty: float = 0.0          # 0-100, subtractive
    eligible: bool = True


def _text_of(candidate: TopicCandidate) -> str:
    parts = [candidate.canonical_topic]
    parts += [e.title for e in candidate.evidence[:10]]
    parts += [e.excerpt or "" for e in candidate.evidence[:5]]
    return " \n".join(p for p in parts if p)


def evaluate(candidate: TopicCandidate, *, extra_text: str = "") -> SafetyVerdict:
    """Score the candidate's safety. Pure function — no I/O, fully testable."""
    v = SafetyVerdict()
    text = f"{_text_of(candidate)}\n{extra_text}"

    for flag, pattern, reason in BLOCKING_RULES:
        if pattern.search(text):
            v.risk_flags.append(flag)
            v.reasons.append(f"BLOCKED: {reason}")
            v.eligible = False
            v.risk_penalty = 100.0

    if not v.eligible:
        return v

    for flag, pattern, reason, weight in PENALTY_RULES:
        if pattern.search(text):
            v.risk_flags.append(flag)
            v.reasons.append(f"penalty: {reason}")
            v.risk_penalty += weight

    # ---- structural risks (not phrasing) ----
    tiers = {e.source_tier for e in candidate.evidence}
    only_social = tiers and tiers <= {SourceTier.social, SourceTier.unknown}

    if candidate.factual_state is FactualState.rumour:
        v.risk_flags.append("unverified_rumour")
        v.reasons.append(
            "penalty: cluster is an unverified rumour — needs primary confirmation"
        )
        v.risk_penalty += 35.0
        if only_social:
            v.risk_flags.append("social_only_rumour")
            v.reasons.append(
                "BLOCKED: unverified rumour with only social sources — popularity is "
                "not verification"
            )
            v.eligible = False
            return v

    if only_social and candidate.factual_state in {
        FactualState.confirmed, FactualState.forecast
    }:
        # A factual claim whose only support is Reddit/X is not a confirmed fact.
        v.risk_flags.append("unconfirmed_factual_claim")
        v.reasons.append(
            "penalty: factual claim supported only by social sources — no primary, "
            "wire or reputable confirmation"
        )
        v.risk_penalty += 30.0

    if candidate.independent_source_count <= 1 and candidate.factual_state in {
        FactualState.confirmed
    }:
        v.risk_flags.append("single_source_confirmation")
        v.reasons.append(
            "penalty: only one independent source for a confirmed event "
            "(syndicated copies do not count as independent confirmations)"
        )
        v.risk_penalty += 15.0

    if not any(e.url for e in candidate.evidence):
        v.risk_flags.append("no_citable_url")
        v.reasons.append("penalty: no citable source URL in the evidence bundle")
        v.risk_penalty += 20.0

    ungrounded = [e for e in candidate.evidence if e.grounded and not e.grounding_complete]
    if ungrounded:
        v.risk_flags.append("incomplete_grounding")
        v.reasons.append(
            f"penalty: {len(ungrounded)} grounding item(s) missing source metadata"
        )
        v.risk_penalty += 10.0

    v.risk_penalty = round(min(100.0, v.risk_penalty), 2)
    # Even without a blocking phrase, an overwhelmingly risky candidate is out.
    if v.risk_penalty >= 60.0:
        v.eligible = False
        v.reasons.append(
            f"BLOCKED: cumulative risk penalty {v.risk_penalty} >= 60 threshold"
        )
    return v


def apply(candidates: list[TopicCandidate]) -> list[TopicCandidate]:
    """Stamp every candidate with risk_flags / risk_penalty / eligibility."""
    for c in candidates:
        v = evaluate(c)
        for f in v.risk_flags:
            if f not in c.risk_flags:
                c.risk_flags.append(f)
        c.rejection_reasons.extend(v.reasons)
        c.deterministic_scores.risk_penalty = v.risk_penalty
        if not v.eligible:
            c.eligible_for_production = False
    return candidates


def screen_text(text: str) -> list[str]:
    """Post-Gemini guard: flag unsafe phrasing in a model-authored angle or hook."""
    flags = [flag for flag, pat, _ in BLOCKING_RULES if pat.search(text or "")]
    return flags
