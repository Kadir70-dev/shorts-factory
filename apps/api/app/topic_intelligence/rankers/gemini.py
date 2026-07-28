"""
The Gemini ranking engine.

Gemini's job is JUDGEMENT — angle, hook, why-now, and the qualitative half of the
score. It is never the source of a fact or a number.

Gemini output is NEVER accepted directly. Every response goes through:

    1. parse            (fenced/prefixed JSON tolerated)
    2. Pydantic validate (GeminiRankingResponse / GeminiTopicVerdict)
    3. topic-id verify   (unknown ids are dropped, not silently mapped)
    4. source verify     (a citation we never collected => verdict rejected)
    5. metric verify     (a fabricated figure => narrative fields discarded)
    6. safety re-screen  (model-authored angle/hook re-run through the gate)
    7. deterministic recompute of overall_score
    8. persistence of the whole decision

Anything that fails a step degrades to the deterministic result for that
candidate; the run continues.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .. import safety
from ..config_types import ChannelBrief
from ..gemini_client import (
    GeminiBudgetExceeded,
    GeminiClient,
    GeminiUnavailable,
    parse_json_response,
)
from ..models import (
    CostReport,
    GeminiRankingResponse,
    GeminiTopicVerdict,
    RankedTopic,
    TopicCandidate,
)
from ..scoring import blend_gemini_scores, explain, load_config
from ..settings import TopicIntelligenceSettings, ti_settings
from .deterministic import to_ranked

PROMPT_VERSION = "ti-rank-v1"

SYSTEM_INSTRUCTION = """\
You are the topic editor for a United States finance and trading YouTube Shorts
channel. You rank REAL, ALREADY-COLLECTED candidate topics.

ABSOLUTE RULES — violating any of these invalidates your entire response:
1. You must NOT invent trend metrics, search volumes, view counts, engagement
   figures, competitor statistics, prices, or economic data. Every number you may
   reference is already in the candidate payload. If a number is not there, it
   does not exist for you.
2. You must NOT invent sources, publishers, URLs or citations. Only the source
   names listed for a candidate may be cited.
3. You must NOT invent economic events, releases, or values (previous/forecast/
   actual). Missing means missing.
4. You must ONLY return topic_id values that appear in the candidate list.
5. You must NOT give financial advice, price targets, buy/sell recommendations,
   guaranteed-return claims, or predictions stated as facts.
6. Your scores are INTERNAL RELATIVE scores from 0-100, never real-world
   predictions. Never write a claim like "this will get 12% CTR".
7. Distinguish carefully between a FORECAST, an EXPECTATION, a CONFIRMED event,
   an OPINION and a HISTORICAL explainer. Never describe an expectation as fact.

You judge only the qualitative dimensions. Trend momentum, freshness, credibility,
competition and risk are computed from measured data and are shown to you as
context — do not attempt to restate or override them.
"""

USER_PROMPT = """\
# Channel
id: {channel_id}
name: {name}
niche: {niche}
identity: {identity}
target audience: {audience}
call to action: {cta}
region: {region}
allowed asset classes: {assets}

# Production constraints
{production_notes}
Duration: {min_dur:.0f}-{max_dur:.0f} seconds, vertical, narration-led.

# Banned topics and framings (hard editorial rules)
{banned}

# Recently used topics (do not repeat these; they are already published or queued)
{ledger}

# Candidates
Each candidate below was clustered from real collected signals. `metrics` are
measured values. `deterministic_scores` were computed in code. `evidence` lists
the only sources you may cite for that candidate.

{candidates}

# Your task
Rank the candidates best-first for the NEXT short. For each candidate return an
object with:
  topic_id                  (must match a candidate id exactly)
  proposed_angle            the single best angle for a 30-45s short
  target_viewer             who specifically this is for
  hook_concept              the opening line concept (no clickbait lie)
  why_now                   why this matters right now, grounded in the evidence
  score_explanation         2-3 sentences justifying your qualitative scores
  confidence                0.0-1.0
  risk_flags                list of risks you see (may be empty)
  rejection_reasons         why this is weak or should not run (may be empty)
  recommended_publish_window ISO-8601 timestamp or null
  cited_source_names        source names taken ONLY from that candidate's evidence
  audience_relevance, ctr_potential, retention_potential,
  subscriber_potential, monetization_potential, production_feasibility
                            integers 0-100, your qualitative judgement

Return JSON: {{"ranked": [ ... ], "notes": "<optional>"}}
Include EVERY candidate exactly once. Put weak candidates last with reasons.
"""

# Figures a model might fabricate: "1.2M views", "40k searches", "12% CTR".
_METRIC_CLAIM = re.compile(
    r"(\d[\d,.]*)\s*(?:%|percent)?\s*"
    r"(views?|searches|search volume|subscribers?|impressions?|ctr|"
    r"click[- ]through|retention|watch time|mentions?|upvotes?)",
    re.I,
)


def _candidate_payload(c: TopicCandidate) -> dict:
    """What Gemini sees. Deliberately compact — cost control starts here."""
    return {
        "topic_id": c.topic_id,
        "canonical_topic": c.canonical_topic,
        "factual_state": c.factual_state.value,
        "event_type": c.event_type.value,
        "asset_classes": [a.value for a in c.asset_classes],
        "tickers": c.tickers,
        "entities": c.entities[:8],
        "source_names": c.source_names,
        "source_count": c.source_count,
        "independent_source_count": c.independent_source_count,
        "provider_count": c.provider_count,
        "first_seen": c.first_seen.isoformat() if c.first_seen else None,
        "last_seen": c.last_seen.isoformat() if c.last_seen else None,
        "scheduled_event_at": (
            c.scheduled_event_at.isoformat() if c.scheduled_event_at else None
        ),
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        "measured_metrics": c.metrics,
        "deterministic_scores": {
            "trend_momentum": c.deterministic_scores.trend_momentum,
            "freshness": c.deterministic_scores.freshness,
            "credibility": c.deterministic_scores.credibility,
            "competition_opportunity": c.deterministic_scores.competition_opportunity,
            "risk_penalty": c.deterministic_scores.risk_penalty,
        },
        "risk_flags": c.risk_flags,
        "evidence": [
            {
                "provider": e.provider,
                "source_name": e.provider,
                "title": e.title,
                "url": e.url,
                "publisher": e.provider,
                "published_at": e.published_at.isoformat() if e.published_at else None,
                "source_tier": e.source_tier.value,
                "credibility": round(e.source_credibility, 2),
                "grounded": e.grounded,
                "grounding_complete": e.grounding_complete,
            }
            for e in c.evidence[:6]
        ],
    }


def allowed_source_names(c: TopicCandidate) -> set[str]:
    """Everything the model is permitted to cite for this candidate."""
    names: set[str] = {n.lower() for n in c.source_names}
    for e in c.evidence:
        names.add(e.provider.lower())
        if e.url:
            from ..entities import host_of

            host = host_of(e.url)
            if host:
                names.add(host)
                names.add(host.split(".")[0])
    return {n for n in names if n}


def known_numbers(c: TopicCandidate) -> set[str]:
    """Digit strings that legitimately appear in this candidate's own data."""
    out: set[str] = set()
    for v in c.metrics.values():
        out.add(f"{v:.0f}")
        out.add(str(v))
    for e in c.evidence:
        for m in re.finditer(r"\d[\d,.]*", f"{e.title} {e.excerpt or ''}"):
            out.add(m.group(0).rstrip(".,"))
        for v in e.metrics.values():
            out.add(f"{v:.0f}")
    return out


def find_invented_metrics(text: str, c: TopicCandidate) -> list[str]:
    """Numeric engagement/volume claims whose value is nowhere in our data."""
    if not text:
        return []
    known = known_numbers(c)
    invented: list[str] = []
    for m in _METRIC_CLAIM.finditer(text):
        num = m.group(1).rstrip(".,")
        if num in known or num.replace(",", "") in {k.replace(",", "") for k in known}:
            continue
        invented.append(m.group(0).strip())
    return invented


class GeminiRanker:
    """The ranking engine. `rank()` never raises — it returns ([], cost, warnings)
    when Gemini is unusable so the service can fall back cleanly."""

    name = "gemini"

    def __init__(
        self,
        settings: TopicIntelligenceSettings | None = None,
        *,
        client: GeminiClient | None = None,
        ledger_topics: list[str] | None = None,
    ) -> None:
        self.settings = settings or ti_settings()
        self.client = client or GeminiClient(self.settings)
        self.ledger_topics = ledger_topics or []

    # ------------------------------------------------------------------ prompt
    def build_prompt(self, candidates: list[TopicCandidate], brief: ChannelBrief) -> str:
        payload = [_candidate_payload(c) for c in candidates]
        ledger = "\n".join(f"- {t}" for t in self.ledger_topics[:40]) or "- (none)"
        return USER_PROMPT.format(
            channel_id=brief.channel_id, name=brief.name, niche=brief.niche,
            identity=brief.identity or "(none specified)",
            audience=brief.target_audience, cta=brief.cta, region=brief.region,
            assets=", ".join(brief.allowed_asset_classes),
            production_notes=brief.production_notes,
            min_dur=brief.min_duration_sec, max_dur=brief.max_duration_sec,
            banned="\n".join(f"- {b}" for b in brief.banned_topics),
            ledger=ledger,
            candidates=json.dumps(payload, indent=1, default=str),
        )

    # -------------------------------------------------------------------- rank
    async def rank(
        self, candidates: list[TopicCandidate], *, brief: ChannelBrief
    ) -> tuple[list[RankedTopic], CostReport, list[str]]:
        warnings: list[str] = []
        if not candidates:
            return [], self.client.cost, ["gemini: no candidates to rank"]
        if not self.settings.gemini_ranker_enabled:
            return [], self.client.cost, ["gemini: ranker disabled by GEMINI_RANKER_ENABLED"]

        # Cost control: only the deterministic finalists ever reach the model.
        subset = candidates[: max(1, self.settings.gemini_max_candidates)]
        if len(candidates) > len(subset):
            warnings.append(
                f"gemini: ranking top {len(subset)} of {len(candidates)} candidates "
                "(GEMINI_MAX_CANDIDATES)"
            )

        try:
            resp = await self.client.generate(
                self.build_prompt(subset, brief),
                system_instruction=SYSTEM_INSTRUCTION,
                response_schema=GeminiRankingResponse,
                temperature=0.2,
            )
        except GeminiBudgetExceeded as e:
            return [], self.client.cost, [f"gemini: {e}"]
        except GeminiUnavailable as e:
            return [], self.client.cost, [f"gemini: {e}"]

        try:
            data = parse_json_response(resp.text)
        except (ValueError, TypeError) as e:
            return [], self.client.cost, [
                f"gemini: unparseable response ({type(e).__name__}: {e})"
            ]

        try:
            parsed = GeminiRankingResponse.model_validate(data)
        except Exception as e:  # noqa: BLE001 — pydantic ValidationError shape varies
            return [], self.client.cost, [
                f"gemini: response failed schema validation ({type(e).__name__})"
            ]

        ranked, val_warnings = self.validate_and_merge(parsed, subset, brief)
        warnings.extend(val_warnings)
        if not ranked:
            warnings.append("gemini: no verdict survived validation")
        return ranked, self.client.cost, warnings

    # -------------------------------------------------------------- validation
    def validate_and_merge(
        self,
        parsed: GeminiRankingResponse,
        candidates: list[TopicCandidate],
        brief: ChannelBrief,
    ) -> tuple[list[RankedTopic], list[str]]:
        """Steps 3-7. This is the trust boundary."""
        cfg = load_config()
        by_id = {c.topic_id: c for c in candidates}
        warnings: list[str] = []
        seen: set[str] = set()
        ranked: list[RankedTopic] = []

        for verdict in parsed.ranked:
            # --- 3. topic id must be one WE supplied ---
            candidate = by_id.get(verdict.topic_id)
            if candidate is None:
                warnings.append(
                    f"gemini: REJECTED unknown topic_id {verdict.topic_id!r} "
                    "(not in the supplied candidate set)"
                )
                continue
            if verdict.topic_id in seen:
                warnings.append(
                    f"gemini: duplicate verdict for {verdict.topic_id} ignored"
                )
                continue
            seen.add(verdict.topic_id)

            base = to_ranked(candidate, brief)
            rejected_narrative = False

            # --- 4. citations must come from the evidence we collected ---
            allowed = allowed_source_names(candidate)
            unknown = [
                n for n in verdict.cited_source_names
                if n and n.strip().lower() not in allowed
                and not any(a in n.strip().lower() for a in allowed)
            ]
            if unknown:
                warnings.append(
                    f"gemini: REJECTED verdict for {verdict.topic_id} — cited "
                    f"unknown source(s) {unknown}; falling back to deterministic"
                )
                base.rejection_reasons.append(
                    f"Gemini cited sources not present in the evidence bundle: {unknown}"
                )
                base.risk_flags.append("gemini_invented_source")
                ranked.append(base)
                continue

            # --- 5. no fabricated figures in the narrative ---
            narrative = " ".join([
                verdict.proposed_angle, verdict.hook_concept, verdict.why_now,
                verdict.score_explanation,
            ])
            invented = find_invented_metrics(narrative, candidate)
            if invented:
                warnings.append(
                    f"gemini: discarded narrative for {verdict.topic_id} — invented "
                    f"metric claim(s) {invented}"
                )
                base.rejection_reasons.append(
                    f"Gemini asserted metrics absent from the collected data: {invented}"
                )
                base.risk_flags.append("gemini_invented_metric")
                rejected_narrative = True

            # --- 6. re-screen model-authored text through the safety gate ---
            unsafe = safety.screen_text(narrative)
            if unsafe:
                warnings.append(
                    f"gemini: unsafe phrasing in {verdict.topic_id} ({unsafe}) — "
                    "narrative discarded and candidate marked ineligible"
                )
                base.risk_flags.extend(f"gemini_{f}" for f in unsafe)
                base.rejection_reasons.append(
                    f"Gemini produced unsafe finance framing: {unsafe}"
                )
                base.eligible_for_production = False
                rejected_narrative = True

            if not rejected_narrative:
                base.proposed_angle = verdict.proposed_angle or base.proposed_angle
                base.target_viewer = verdict.target_viewer or base.target_viewer
                base.hook_concept = verdict.hook_concept or base.hook_concept
                base.why_now = verdict.why_now or base.why_now
                base.score_explanation = verdict.score_explanation
                base.confidence = verdict.confidence
                if verdict.recommended_publish_window:
                    base.recommended_publish_window = _as_utc(
                        verdict.recommended_publish_window
                    )
            for f in verdict.risk_flags:
                if f and f not in base.risk_flags:
                    base.risk_flags.append(str(f)[:60])
            base.rejection_reasons.extend(str(r)[:200] for r in verdict.rejection_reasons)

            # --- 7. deterministic recompute (Gemini never sets overall_score) ---
            base.scores = blend_gemini_scores(
                candidate.deterministic_scores,
                {
                    "audience_relevance": verdict.audience_relevance,
                    "ctr_potential": verdict.ctr_potential,
                    "retention_potential": verdict.retention_potential,
                    "subscriber_potential": verdict.subscriber_potential,
                    "monetization_potential": verdict.monetization_potential,
                    "production_feasibility": verdict.production_feasibility,
                },
                cfg=cfg,
            )
            base.ranker = "gemini"
            if not base.score_explanation or rejected_narrative:
                base.score_explanation = explain(base.scores, cfg)
            ranked.append(base)

        # Candidates the model silently dropped still get a deterministic ranking —
        # an omission is not a rejection.
        for c in candidates:
            if c.topic_id not in seen:
                warnings.append(
                    f"gemini: candidate {c.topic_id} missing from response — "
                    "using deterministic scores"
                )
                ranked.append(to_ranked(c, brief))

        ranked.sort(key=lambda r: -r.scores.overall_score)
        return ranked, warnings


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
