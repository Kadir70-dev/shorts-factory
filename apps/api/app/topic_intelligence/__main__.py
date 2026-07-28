"""
CLI:

    python -m app.topic_intelligence collect --channel usa_trading
    python -m app.topic_intelligence rank    --channel usa_trading
    python -m app.topic_intelligence select  --channel usa_trading
    python -m app.topic_intelligence run     --channel usa_trading [--enqueue]
    python -m app.topic_intelligence status

Run from `apps/api/` (the package root), same as the API and worker.
Exit codes: 0 = success, 2 = NO_SAFE_TOPIC_AVAILABLE, 1 = unexpected error.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import provenance
from .models import NO_SAFE_TOPIC_AVAILABLE
from .repository import TopicIntelligenceRepository
from .service import TopicIntelligenceService
from .settings import ti_settings

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_TOPIC = 2


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m app.topic_intelligence",
        description="Gemini-powered finance trend intelligence (Phase 2A)",
    )
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("collect", "run the connectors and report per-provider health"),
        ("rank", "collect, cluster, score and rank (no selection, no enqueue)"),
        ("select", "full run and pick one topic (no enqueue unless --enqueue)"),
        ("run", "full run; honours TI_AUTO_ENQUEUE unless overridden"),
        ("status", "show provider configuration and Gemini budget"),
    ):
        sp = sub.add_parser(name, help=help_text)
        if name != "status":
            sp.add_argument("--channel", default=None,
                            help="channel id (default: TI_DEFAULT_CHANNEL)")
            sp.add_argument("--json", action="store_true",
                            help="emit machine-readable JSON")
        if name in {"select", "run"}:
            sp.add_argument("--enqueue", action="store_true", default=None,
                            help="enqueue the winner into the existing pipeline")
            sp.add_argument("--no-enqueue", dest="enqueue", action="store_false",
                            help="never enqueue, even if TI_AUTO_ENQUEUE=true")
            sp.add_argument("--override", action="append", default=[],
                            metavar="TOPIC_ID",
                            help="admin override: allow a deduped topic to win")
            sp.add_argument("--no-persist", dest="persist", action="store_false",
                            default=True, help="dry run; do not write to the DB")
    return p


async def _collect(args) -> int:
    svc = TopicIntelligenceService()
    outcome = await svc.collect(channel_id=args.channel or ti_settings().ti_default_channel)
    if args.json:
        print(json.dumps({
            "run_id": outcome.run_id,
            "signal_count": len(outcome.signals),
            "providers": [p.model_dump() for p in outcome.statuses],
        }, indent=2, default=str))
    else:
        print(f"run {outcome.run_id}: {len(outcome.signals)} raw signals")
        for st in outcome.statuses:
            state = "ok" if st.ok else (st.skipped_reason or st.error or "failed")
            print(f"  {st.name:<20} {st.signal_count:>4}  {state}")
    return EXIT_OK


async def _rank(args) -> int:
    s = ti_settings()
    svc = TopicIntelligenceService()
    channel_id = args.channel or s.ti_default_channel
    outcome = await svc.collect(channel_id=channel_id)
    finalists, all_candidates = svc.build_candidates(
        outcome.signals, channel_id=channel_id
    )
    if not finalists:
        print(NO_SAFE_TOPIC_AVAILABLE)
        return EXIT_NO_TOPIC
    ranked, ranker, cost, warnings, model = await svc.rank(
        finalists, channel=svc._channel(channel_id), run_id=outcome.run_id
    )
    if args.json:
        print(json.dumps({
            "run_id": outcome.run_id, "ranker_used": ranker, "gemini_model": model,
            "cost": cost.model_dump(), "warnings": warnings,
            "ranked": [r.model_dump() for r in ranked],
        }, indent=2, default=str))
    else:
        print(f"run {outcome.run_id}  ranker={ranker}  "
              f"clusters={len(all_candidates)}  finalists={len(finalists)}")
        for i, r in enumerate(ranked, 1):
            flag = "" if r.eligible_for_production else "  [INELIGIBLE]"
            print(f"{i:>2}. [{r.scores.overall_score:5.1f}] {r.canonical_topic[:80]}{flag}")
            print(f"      angle: {r.proposed_angle[:100]}")
        for w in warnings:
            print(f"  warn: {w}")
    return EXIT_OK


async def _run(args, *, enqueue_default: bool | None) -> int:
    svc = TopicIntelligenceService()
    result = await svc.run(
        channel_id=args.channel,
        enqueue=enqueue_default,
        persist=getattr(args, "persist", True),
        override_topic_ids=set(getattr(args, "override", []) or []) or None,
    )
    if args.json:
        print(json.dumps(result.model_dump(), indent=2, default=str))
    else:
        print(provenance.summarize(result))
    return EXIT_NO_TOPIC if result.status == NO_SAFE_TOPIC_AVAILABLE else EXIT_OK


def _status() -> int:
    s = ti_settings()
    svc = TopicIntelligenceService()
    from .gemini_client import utc_day_start

    spent = TopicIntelligenceRepository().spend_since(utc_day_start())
    print(f"Gemini: model={s.gemini_model} ranker={'on' if s.gemini_ranker_enabled else 'off'} "
          f"grounding={'on' if s.gemini_grounding_enabled else 'off'} "
          f"key={'set' if s.gemini_usable else 'MISSING'}")
    print(f"        budget=${s.gemini_daily_budget_usd:.2f}/day  spent_today=${spent:.6f}")
    print(f"Region: {s.ti_region}   default channel: {s.ti_default_channel}")
    print("Providers:")
    for p in svc.provider_status():
        state = "USABLE" if p.ok else (p.skipped_reason or "unavailable")
        print(f"  {p.name:<20} enabled={str(p.enabled):<5} "
              f"configured={str(p.configured):<5}  {state}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "status":
            return _status()
        if args.command == "collect":
            return asyncio.run(_collect(args))
        if args.command == "rank":
            return asyncio.run(_rank(args))
        if args.command == "select":
            # `select` never enqueues unless explicitly asked.
            return asyncio.run(_run(args, enqueue_default=bool(args.enqueue)))
        if args.command == "run":
            # `run` honours TI_AUTO_ENQUEUE when the flag is not given.
            return asyncio.run(_run(args, enqueue_default=args.enqueue))
    except KeyboardInterrupt:
        return EXIT_ERROR
    except Exception as e:  # noqa: BLE001
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
