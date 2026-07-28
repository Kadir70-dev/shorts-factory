"""
The ONE seam into the existing production pipeline.

A selected topic becomes a `VideoSpec` and is enqueued through the SAME path the
`/generate` endpoint uses (`routers.generate.enqueue_spec`). Nothing about the
Director, SceneGraph, TTS, asset or FFmpeg stages changes — they receive a topic
string exactly as they always have.

This phase does NOT upload, publish or schedule anything.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from ..config import ChannelConfig
from ..schemas.video_spec import Niche, VideoSpec
from .models import RankedTopic

# Channel YAML `niche` values that are not themselves Niche members map here.
_NICHE_ALIASES = {
    "usa_trading": Niche.finance,
    "trading": Niche.finance,
    "finance": Niche.finance,
    "macro": Niche.finance,
}


def resolve_niche(channel: ChannelConfig) -> Niche:
    raw = (channel.niche or "").strip()
    try:
        return Niche(raw)
    except ValueError:
        return _NICHE_ALIASES.get(raw.lower(), Niche.finance)


def build_topic_prompt(topic: RankedTopic) -> str:
    """The topic string the Director receives.

    Deliberately a rich, single line: the frozen Director takes `spec.topic` as
    free text, so the angle and hook ride along without any pipeline change.
    """
    parts = [topic.canonical_topic.strip()]
    if topic.proposed_angle:
        parts.append(f"Angle: {topic.proposed_angle.strip()}")
    if topic.hook_concept:
        parts.append(f"Hook: {topic.hook_concept.strip()}")
    if topic.why_now:
        parts.append(f"Why now: {topic.why_now.strip()}")
    return " | ".join(p for p in parts if p)[:900]


def build_video_spec(
    topic: RankedTopic,
    channel: ChannelConfig,
    *,
    evidence_bundle: dict[str, Any] | None = None,
) -> VideoSpec:
    # A human approval may be retried or double-clicked. Use a stable job id for
    # the persisted decision so every attempt targets one existing Job/ARQ task.
    job_id = None
    if evidence_bundle:
        run_id = str(evidence_bundle.get("run_id") or "")
        topic_id = str(evidence_bundle.get("topic", {}).get("topic_id") or "")
        if run_id and topic_id:
            digest = hashlib.sha256(f"{run_id}:{topic_id}".encode()).hexdigest()[:12]
            job_id = f"vid_ti_{digest}"
    spec = VideoSpec(
        **({"id": job_id} if job_id else {}),
        channel_id=channel.id,
        niche=resolve_niche(channel),
        topic=build_topic_prompt(topic),
    )
    if evidence_bundle is not None:
        # Attached out-of-band (VideoSpec is intentionally thin and frozen). The
        # enqueue path persists it alongside the job so the render retains the
        # evidence used to pick its topic.
        setattr(spec, "_ti_evidence_bundle", evidence_bundle)
    return spec


async def enqueue_topic(
    topic: RankedTopic,
    channel: ChannelConfig,
    *,
    evidence_bundle: dict[str, Any] | None = None,
) -> str:
    """Enqueue into the existing pipeline. Returns the job id.

    Imported lazily so `topic_intelligence` never drags Redis/arq into a CLI or
    test that only wants to rank.
    """
    from ..routers.generate import enqueue_spec

    spec = build_video_spec(topic, channel, evidence_bundle=evidence_bundle)
    await enqueue_spec(spec)
    if evidence_bundle is not None:
        _attach_evidence(spec.id, evidence_bundle)
    return spec.id


def _attach_evidence(job_id: str, bundle: dict[str, Any]) -> None:
    """Store the evidence bundle on the job's metadata_json.

    Additive: it writes only the `topic_intelligence` key and preserves whatever
    the pipeline later puts there. Failure is non-fatal — an unpersisted bundle
    must never block production.
    """
    try:
        from ..db import get_job, upsert_job

        job = get_job(job_id)
        if job is None:
            return
        meta = {}
        if job.metadata_json:
            try:
                meta = json.loads(job.metadata_json)
            except json.JSONDecodeError:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        meta["topic_intelligence"] = bundle
        job.metadata_json = json.dumps(meta, default=str)
        upsert_job(job)
    except Exception as e:  # noqa: BLE001
        print(f"[ti.bridge] could not attach evidence bundle to {job_id}: "
              f"{type(e).__name__}: {e}", flush=True)
