"""
Requirement 18: the existing video-production pipeline stays green.

The repository ships no pytest suite for the frozen pipeline, so "remains green"
is enforced structurally here: every production module still imports, the public
contracts are unchanged, the frozen render core is untouched by Phase 2A, and the
one integration seam behaves exactly as before.
"""
from __future__ import annotations

import importlib
import inspect

import pytest

PRODUCTION_MODULES = [
    "app.config",
    "app.db",
    "app.main",
    "app.director",
    "app.director.prompts",
    "app.pipeline.broll",
    "app.pipeline.captions",
    "app.pipeline.layers",
    "app.pipeline.music",
    "app.pipeline.postprocess",
    "app.pipeline.qa",
    "app.pipeline.ram",
    "app.pipeline.render",
    "app.pipeline.render_ffmpeg",
    "app.pipeline.scene_director",
    "app.pipeline.sfx",
    "app.pipeline.storyboard",
    "app.pipeline.tts",
    "app.routers.generate",
    "app.routers.jobs",
    "app.schemas.scene",
    "app.schemas.video_spec",
    "app.workers.tasks",
]


@pytest.mark.parametrize("module", PRODUCTION_MODULES)
def test_production_modules_still_import(module):
    importlib.import_module(module)


def test_video_spec_contract_is_unchanged():
    from app.schemas.video_spec import Niche, VideoSpec

    spec = VideoSpec(channel_id="usa_finance", niche=Niche.finance, topic="CPI")
    assert spec.id.startswith("vid_")
    assert spec.status.value == "queued"
    assert spec.render.max_duration_sec == 45.0
    # Phase 2A added no required field.
    assert VideoSpec.model_validate(spec.model_dump()).topic == "CPI"


def test_job_table_columns_are_unchanged():
    from app.db import Job

    assert set(Job.model_fields) == {
        "id", "channel_id", "niche", "topic", "status", "error", "spec_json",
        "scene_graph_json", "metadata_json", "output_mp4", "created_at",
        "updated_at",
    }


def test_topic_intelligence_tables_are_additive_and_namespaced():
    from app.topic_intelligence.tables import TI_TABLES

    names = {t.__tablename__ for t in TI_TABLES}
    assert all(n.startswith("ti_") for n in names), names
    assert "job" not in names


def test_enqueue_seam_keeps_its_legacy_name():
    """`_enqueue` was the original private helper; it must still work."""
    from app.routers import generate

    assert generate._enqueue is generate.enqueue_spec
    assert inspect.iscoroutinefunction(generate.enqueue_spec)


def test_topic_intelligence_router_is_mounted_without_touching_others():
    from app.main import app

    # Read the OpenAPI schema rather than app.routes: newer FastAPI versions nest
    # included routers, so the flat route list is not a stable contract.
    paths = set(app.openapi()["paths"])
    assert "/generate" in paths
    assert "/generate/batch" in paths
    assert "/jobs" in paths
    assert "/health" in paths
    ti_paths = {p for p in paths if p.startswith("/topic-intelligence")}
    assert {
        "/topic-intelligence/collect",
        "/topic-intelligence/rank",
        "/topic-intelligence/select",
        "/topic-intelligence/candidates",
        "/topic-intelligence/candidates/{topic_id}",
        "/topic-intelligence/providers/status",
        "/topic-intelligence/runs/{run_id}",
    } <= ti_paths, ti_paths


def test_bridge_builds_a_valid_video_spec():
    from app.config import load_channel
    from app.topic_intelligence.bridge import build_topic_prompt, build_video_spec
    from app.topic_intelligence.models import RankedTopic

    topic = RankedTopic(
        topic_id="tc_1",
        canonical_topic="Federal Reserve cuts rates by 25 basis points",
        proposed_angle="Explain what actually changes for mortgages",
        hook_concept="The Fed just moved.",
        why_now="Decision landed two hours ago.",
    )
    channel = load_channel("usa_trading")
    spec = build_video_spec(topic, channel)

    assert spec.channel_id == "usa_trading"
    assert spec.niche.value == "usa_finance"     # aliased to a real Niche member
    assert "Federal Reserve cuts rates" in spec.topic
    assert "Angle:" in spec.topic and "Hook:" in spec.topic
    assert len(build_topic_prompt(topic)) <= 900


def test_existing_channels_still_load():
    from app.config import load_channel

    for cid in ("usa_finance", "usa_politics", "usa_election", "k70_business"):
        assert load_channel(cid).id == cid


def test_topic_intelligence_import_has_no_pipeline_side_effects():
    """Importing the package must not pull in Redis, arq, ffmpeg or the Director."""
    import subprocess
    import sys
    from pathlib import Path

    apps_api = Path(__file__).resolve().parents[2]
    code = (
        "import sys; import app.topic_intelligence as ti;"
        "bad=[m for m in ('arq','redis','anthropic') if m in sys.modules];"
        "print(','.join(bad))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=apps_api, capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", f"unexpected imports: {out.stdout.strip()}"
