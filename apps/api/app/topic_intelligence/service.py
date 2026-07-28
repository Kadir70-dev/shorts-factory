"""
The orchestrator. Collect -> normalize -> cluster -> dedup -> safety -> score ->
Gemini rank -> validate -> select -> persist -> (optionally) enqueue.

Funnel discipline (this is the cost control):

    200-500 raw signals
        -> 20-40 normalized topic clusters      (clustering.py)
        -> 10-20 deterministic finalists        (scoring.py + TI_MAX_FINALISTS)
        -> Gemini ranks the finalists ONLY
        -> 1 selected topic

Failure discipline: providers run concurrently and independently; any subset can
fail. Gemini failure falls back to the deterministic ranker. If nothing credible
and safe survives, the run returns NO_SAFE_TOPIC_AVAILABLE and produces nothing —
filler content is never generated.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..config import ChannelConfig, load_channel
from . import clustering, dedup, normalizer, provenance, safety, scoring
from .config_types import ChannelBrief
from .gemini_client import GeminiClient, utc_day_start
from .models import (
    NO_SAFE_TOPIC_AVAILABLE,
    CostReport,
    ProviderStatus,
    RankedTopic,
    RawTrendSignal,
    SelectionResult,
    TopicCandidate,
)
from .providers import build_providers
from .rankers import PROMPT_VERSION, DeterministicRanker, GeminiRanker
from .repository import TopicIntelligenceRepository
from .settings import TopicIntelligenceSettings, ti_settings


class CollectionOutcome:
    """Intermediate state so `collect` and `rank` can be driven independently."""

    def __init__(
        self,
        run_id: str,
        signals: list[RawTrendSignal],
        statuses: list[ProviderStatus],
    ) -> None:
        self.run_id = run_id
        self.signals = signals
        self.statuses = statuses


class TopicIntelligenceService:
    def __init__(
        self,
        *,
        settings: TopicIntelligenceSettings | None = None,
        repo: TopicIntelligenceRepository | None = None,
        providers: list | None = None,
        gemini_client: GeminiClient | None = None,
    ) -> None:
        self.settings = settings or ti_settings()
        self.repo = repo or TopicIntelligenceRepository()
        self._providers = providers
        self._gemini_client = gemini_client

    # ------------------------------------------------------------------ helpers
    def providers(self) -> list:
        if self._providers is None:
            self._providers = build_providers(self.settings)
        return self._providers

    def _channel(self, channel_id: str) -> ChannelConfig:
        return load_channel(channel_id)

    def provider_status(self) -> list[ProviderStatus]:
        """Health/config snapshot without running anything."""
        from .http import circuit_state

        out = []
        for p in self.providers():
            out.append(ProviderStatus(
                name=p.name, enabled=p.enabled, configured=p.configured,
                ok=p.usable and not circuit_state(p.name),
                circuit_open=circuit_state(p.name),
                skipped_reason=(
                    None if p.usable else
                    ("disabled by feature flag" if not p.enabled
                     else "missing credentials or endpoint configuration")
                ),
            ))
        return out

    # ------------------------------------------------------------------ collect
    async def collect(
        self, *, channel_id: str, run_id: str | None = None, persist: bool = True
    ) -> CollectionOutcome:
        """Run every provider CONCURRENTLY. One failure never stops the others."""
        s = self.settings
        run_id = run_id or f"tir_{uuid4().hex[:12]}"
        since = datetime.now(timezone.utc) - timedelta(hours=s.ti_lookback_hours)
        channel = self._channel(channel_id)
        per_provider = max(20, s.ti_max_raw_signals // max(1, len(self.providers())))

        results = await asyncio.gather(*[
            p.run(niche=channel.niche, region=s.ti_region, since=since,
                  limit=per_provider)
            for p in self.providers()
        ])

        signals: list[RawTrendSignal] = []
        statuses: list[ProviderStatus] = []
        for sig_list, status in results:
            signals.extend(sig_list)
            statuses.append(status)

        signals = signals[: s.ti_max_raw_signals]
        if persist:
            self.repo.save_provider_runs(run_id, statuses)

        healthy = [st.name for st in statuses if st.ok]
        print(f"[ti] run={run_id} collected {len(signals)} signals from "
              f"{len(healthy)}/{len(statuses)} providers: {', '.join(healthy) or 'none'}",
              flush=True)
        return CollectionOutcome(run_id, signals, statuses)

    # -------------------------------------------------------------- build funnel
    def build_candidates(
        self,
        signals: list[RawTrendSignal],
        *,
        channel_id: str,
        now: datetime | None = None,
        override_topic_ids: set[str] | None = None,
    ) -> tuple[list[TopicCandidate], list[TopicCandidate]]:
        """normalize -> cluster -> dedup -> safety -> score.

        Returns (finalists, all_candidates). `all_candidates` includes the ones
        that were scored but did not make the cut, so rejections are auditable.
        """
        now = now or datetime.now(timezone.utc)
        normalized = normalizer.normalize_all(signals, now=now)
        clusters = clustering.cluster_signals(normalized, now=now)
        survivors = dedup.apply_dedup(
            clusters, channel_id=channel_id, repo=self.repo,
            override_topic_ids=override_topic_ids,
        )
        # Candidates the dedup layer hard-blocked. They are deliberately kept out
        # of `survivors` but scored and returned anyway so the review dashboard can
        # show WHAT was rejected and WHY — a duplicate you cannot see is one you
        # cannot knowingly override. Clusters merged into a stronger sibling are
        # not rejections and stay out (they keep eligible_for_production=True).
        kept_ids = {c.topic_id for c in survivors}
        blocked = [
            c for c in clusters
            if c.topic_id not in kept_ids and not c.eligible_for_production
        ]
        # Editorial relevance: a general news feed carries politics, war and court
        # stories. They are not unsafe, they are simply not this channel's beat.
        if self.settings.ti_require_finance_relevance:
            for c in survivors:
                if not scoring.is_on_niche(c):
                    c.eligible_for_production = False
                    c.rejection_reasons.append(
                        "off-niche: no asset class, ticker or recognized financial "
                        "event — outside this channel's finance/trading beat"
                    )

        safety.apply(survivors + blocked)
        scored = scoring.score_all(survivors, now=now)

        eligible = [
            c for c in scored
            if c.eligible_for_production
            and c.source_count >= self.settings.ti_min_source_count
        ]
        finalists = eligible[: self.settings.ti_max_finalists]
        return finalists, scored + scoring.score_all(blocked, now=now)

    # --------------------------------------------------------------------- rank
    async def rank(
        self,
        candidates: list[TopicCandidate],
        *,
        channel: ChannelConfig,
        run_id: str,
    ) -> tuple[list[RankedTopic], str, CostReport, list[str], str | None]:
        """Gemini first, deterministic fallback. Returns
        (ranked, ranker_used, cost, warnings, gemini_model)."""
        s = self.settings
        brief = ChannelBrief.from_channel(channel, region=s.ti_region)
        ledger_topics = [
            r.canonical_topic for r in self.repo.ledger_entries(
                channel.id, days=s.topic_semantic_dedup_days,
                statuses=dedup.BLOCKING_STATUSES,
            )
        ]
        warnings: list[str] = []

        if s.gemini_ranker_enabled and s.gemini_usable:
            spent = self.repo.spend_since(utc_day_start())
            client = self._gemini_client or GeminiClient(s, spend_today=spent)
            ranker = GeminiRanker(s, client=client, ledger_topics=ledger_topics)
            ranked, cost, warn = await ranker.rank(candidates, brief=brief)
            warnings.extend(warn)
            if ranked:
                return ranked, "gemini", cost, warnings, s.gemini_model
            warnings.append(
                "gemini ranker produced no usable output — deterministic fallback engaged"
            )
            fallback_cost = cost
        else:
            reason = (
                "GEMINI_RANKER_ENABLED=false" if not s.gemini_ranker_enabled
                else "GEMINI_API_KEY is not set"
            )
            warnings.append(f"gemini ranker not used ({reason}) — deterministic ranking")
            fallback_cost = CostReport(budget_usd=s.gemini_daily_budget_usd)

        ranked, det_cost, det_warn = await DeterministicRanker().rank(
            candidates, brief=brief
        )
        warnings.extend(det_warn)
        return ranked, "deterministic", fallback_cost, warnings, None

    # ------------------------------------------------------------------- select
    def select(
        self, ranked: list[RankedTopic]
    ) -> tuple[RankedTopic | None, list[RankedTopic], str]:
        """Pick exactly ONE eligible topic, or refuse.

        Refusal conditions: nothing eligible, or fewer than
        TI_MIN_ELIGIBLE_CANDIDATES credible candidates survived.
        """
        s = self.settings
        eligible = [
            r for r in ranked
            if r.eligible_for_production and not _expired(r)
        ]
        rejected = [r for r in ranked if r not in eligible]

        if len(eligible) < max(1, s.ti_min_eligible_candidates):
            return None, ranked, NO_SAFE_TOPIC_AVAILABLE
        winner = max(eligible, key=lambda r: r.scores.overall_score)
        return winner, rejected, "ok"

    # ---------------------------------------------------------------------- run
    async def run(
        self,
        *,
        channel_id: str | None = None,
        enqueue: bool | None = None,
        persist: bool = True,
        override_topic_ids: set[str] | None = None,
        now: datetime | None = None,
    ) -> SelectionResult:
        """The full pipeline. Never raises for provider/model failures."""
        s = self.settings
        channel_id = channel_id or s.ti_default_channel
        enqueue = s.ti_auto_enqueue if enqueue is None else enqueue
        channel = self._channel(channel_id)
        started = datetime.now(timezone.utc)

        outcome = await self.collect(channel_id=channel_id, persist=persist)
        finalists, all_candidates = self.build_candidates(
            outcome.signals, channel_id=channel_id, now=now,
            override_topic_ids=override_topic_ids,
        )

        result = SelectionResult(
            run_id=outcome.run_id, channel_id=channel_id,
            providers=outcome.statuses,
            raw_signal_count=len(outcome.signals),
            cluster_count=len(all_candidates),
            finalist_count=len(finalists),
            prompt_version=PROMPT_VERSION,
            ranking_version=s.ranking_version,
            started_at=started,
        )
        for st in outcome.statuses:
            if st.stale:
                result.warnings.append(
                    f"provider {st.name}: stale data (newest signal older than "
                    f"{s.ti_stale_after_hours}h)"
                )
            elif not st.ok and st.error:
                result.warnings.append(f"provider {st.name}: {st.error}")

        if not finalists:
            result.status = NO_SAFE_TOPIC_AVAILABLE
            result.ranker_used = "none"
            result.warnings.append(
                "no eligible candidate survived clustering, dedup and the safety "
                "gate — refusing to produce filler content"
            )
            result.finished_at = datetime.now(timezone.utc)
            if persist:
                self.repo.save_candidates(outcome.run_id, channel_id, all_candidates)
                self.repo.save_run(result)
            _log_decision(result)
            return result

        ranked, ranker_used, cost, warnings, model = await self.rank(
            finalists, channel=channel, run_id=outcome.run_id
        )
        result.ranked = ranked
        result.ranker_used = ranker_used
        result.gemini_model = model
        result.cost = cost
        result.warnings.extend(warnings)

        # Gemini may have marked a candidate ineligible; mirror that onto the
        # candidate records BEFORE persisting them.
        verdicts = {r.topic_id: r for r in ranked}
        for c in all_candidates:
            rt = verdicts.get(c.topic_id)
            if rt is not None and not rt.eligible_for_production:
                c.eligible_for_production = False
                for f in rt.risk_flags:
                    if f not in c.risk_flags:
                        c.risk_flags.append(f)

        winner, rejected, status = self.select(ranked)
        result.rejected = rejected
        result.status = status
        result.selected = winner

        if winner is not None:
            candidate = next(
                (c for c in all_candidates if c.topic_id == winner.topic_id), None
            )
            bundle = provenance.evidence_bundle(result, winner, candidate)
            if enqueue:
                try:
                    result.enqueued_job_id = await self._enqueue(
                        winner, channel, bundle
                    )
                except Exception as e:  # noqa: BLE001 — a queue outage is not a
                    # ranking failure; the decision stands and stays persisted.
                    result.warnings.append(
                        f"enqueue failed ({type(e).__name__}: {e}) — topic selected "
                        "but not queued"
                    )
            if persist:
                self.repo.record_selection(
                    channel_id=channel_id, topic=winner, candidate=candidate,
                    run_id=outcome.run_id, job_id=result.enqueued_job_id,
                    status="queued" if result.enqueued_job_id else "selected",
                    override_reason=(
                        "admin override" if override_topic_ids
                        and winner.topic_id in override_topic_ids else None
                    ),
                )
        else:
            result.warnings.append(
                "no eligible topic after ranking — returning NO_SAFE_TOPIC_AVAILABLE"
            )

        result.finished_at = datetime.now(timezone.utc)
        if persist:
            self.repo.save_candidates(outcome.run_id, channel_id, all_candidates)
            self.repo.save_run(result)
        _log_decision(result)
        return result

    async def _enqueue(
        self, topic: RankedTopic, channel: ChannelConfig, bundle: dict
    ) -> str:
        from .bridge import enqueue_topic

        return await enqueue_topic(topic, channel, evidence_bundle=bundle)


def _log_decision(result: SelectionResult) -> None:
    """One compact audit line. The full multi-line summary is the CALLER's job
    (`provenance.summarize`) so a CLI run does not print the same report twice."""
    picked = (
        f"{result.selected.canonical_topic[:70]!r} "
        f"@{result.selected.scores.overall_score:.1f}"
        if result.selected else result.status
    )
    print(
        f"[ti] run={result.run_id} channel={result.channel_id} "
        f"status={result.status} ranker={result.ranker_used} "
        f"funnel={result.raw_signal_count}/{result.cluster_count}/"
        f"{result.finalist_count} cost=${result.cost.estimated_usd:.6f} "
        f"selected={picked}",
        flush=True,
    )


def _expired(topic: RankedTopic) -> bool:
    if topic.expires_at is None:
        return False
    exp = topic.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp < datetime.now(timezone.utc)
