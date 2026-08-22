"""Tests for the production-checkpointing wiring (OpenMontage-audit gap #2).

Two layers are covered:
  1. `scripts/produce.py`'s module-level glue (`_dump_graph`/`_load_graph`/
     `_stage_op`) that adapts pipeline stage functions to the pre-existing
     `production_optimizer.resumable_stage`/`CheckpointStore` primitives —
     those primitives already have their own tests
     (`tests/pipeline/test_production_optimizer.py`); these tests cover the
     NEW glue, not the primitives themselves.
  2. `pipeline/broll.py`'s beat-level resume layer (`_load_progress`,
     `_save_progress_entry`, `_snapshot_is_reusable`, `_dispatch_scene_resumable`),
     which persists per-scene results so a crash mid-`resolve_assets` doesn't
     force every scene to be re-resolved on the next run — proven here with a
     synthetic dispatcher whose call count is asserted directly, and against
     the real Bitcoin Episode 1 SceneGraph end-to-end during the benchmark.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from app.pipeline import broll  # noqa: E402
from app.pipeline.production_optimizer import CheckpointStore, resumable_stage  # noqa: E402
from app.schemas.scene import SceneGraph  # noqa: E402


def _minimal_graph_json(video_id: str) -> str:
    return SceneGraph(
        schema_version="2.0",
        meta={"video_id": video_id, "channel_id": "k70_history", "niche": "usa_history",
              "title": "checkpoint test", "hook": "a hook"},
        scenes=[{
            "id": "s1", "narration": "a test beat", "duration_sec": 3.0,
            "visual": {"type": "broll", "query": "test"},
        }],
    ).model_dump_json()


# --------------------------------------------------------------------------- #
# produce.py glue
# --------------------------------------------------------------------------- #
def test_stage_op_wraps_a_sync_function():
    import produce

    calls = []

    def sync_fn(x, y=1):
        calls.append((x, y))
        return x + y

    op = produce._stage_op(sync_fn, 2, y=3)
    import asyncio
    result = asyncio.run(op())
    assert result == 5
    assert calls == [(2, 3)]


def test_stage_op_wraps_an_async_function():
    import produce
    import asyncio

    async def async_fn(x):
        return x * 2

    op = produce._stage_op(async_fn, 4)
    assert asyncio.run(op()) == 8


def test_load_graph_clamps_sub_floor_duration_instead_of_crashing(tmp_path):
    """Real bug this checkpoint system's dump/load round-trip exposed on the
    actual Bitcoin Episode 1 job: measured TTS can legitimately produce a
    duration a hair under Scene.duration_sec's `ge=0.8` floor (0.747s was the
    real observed value on scene 47). That's harmless via plain attribute
    assignment (no re-validation) but crashed `model_validate_json` on
    resume. `_load_graph` must clamp, not crash."""
    import produce

    raw = json.loads(_minimal_graph_json("clamp_test"))
    raw["scenes"][0]["duration_sec"] = 0.747
    p = tmp_path / "voiceover.checkpoint"
    p.write_text(json.dumps(raw), encoding="utf-8")

    loaded = produce._load_graph(p)
    assert loaded.scenes[0].duration_sec == 0.8


def test_dump_and_load_graph_round_trip(tmp_path):
    import produce

    graph = SceneGraph.model_validate_json(_minimal_graph_json("rt_test"))
    p = tmp_path / "storyboard.checkpoint"
    produce._dump_graph(graph, p)
    reloaded = produce._load_graph(p)
    assert reloaded.meta.video_id == "rt_test"
    assert reloaded.scenes[0].id == "s1"


@pytest.mark.asyncio
async def test_resumable_stage_skips_the_second_call_via_stage_op(tmp_path, monkeypatch):
    """End-to-end glue check: a stage wrapped through `_stage_op` +
    `resumable_stage` runs its underlying function exactly once across two
    invocations for the same job — the second one loads the checkpointed
    graph instead."""
    import produce
    from app.pipeline import production_optimizer as optimizer

    # Patch the SAME `settings` reference `CheckpointStore` will actually read
    # — `optimizer.settings`, not a fresh `from app.config import settings`.
    # `test_path_resolution.py::test_compose_env_pins_repo` (elsewhere in this
    # suite, pre-existing, unrelated to this change) does
    # `importlib.reload(config)`, which replaces `sys.modules["app.config"]`
    # with a NEW module — so a settings() looked up fresh in THIS test body
    # can silently resolve to a different singleton than the one
    # `production_optimizer.py` already imported at ITS module-load time,
    # and patching the wrong one leaves `data_dir` untouched from
    # `CheckpointStore`'s point of view. Going through `optimizer.settings`
    # directly sidesteps that entirely.
    monkeypatch.setattr(optimizer.settings(), "data_dir", tmp_path)

    # A job id derived from `tmp_path` (pytest guarantees this is unique per
    # test invocation) rather than a fixed literal — belt-and-suspenders
    # against ever again colliding with a leftover real `data/jobs/<id>/`
    # checkpoint from an earlier run.
    job_id = f"resume_glue_{tmp_path.name}"
    graph = SceneGraph.model_validate_json(_minimal_graph_json(job_id))
    store = optimizer.CheckpointStore(job_id)
    assert tmp_path in store.root.parents, (
        f"CheckpointStore.root ({store.root}) did not land under the isolated "
        f"tmp_path ({tmp_path}) — data_dir patch did not take effect")
    calls = 0

    def fake_storyboard(g):
        nonlocal calls
        calls += 1
        g.scenes[0].narration = "touched"
        return g

    op = produce._stage_op(fake_storyboard, graph)
    first = await resumable_stage(store, "storyboard", op,
                                  dump=produce._dump_graph, load=produce._load_graph)
    op2 = produce._stage_op(fake_storyboard, graph)
    second = await resumable_stage(store, "storyboard", op2,
                                   dump=produce._dump_graph, load=produce._load_graph)

    assert calls == 1                     # the underlying stage ran ONCE
    assert first.scenes[0].narration == "touched"
    assert second.scenes[0].narration == "touched"   # loaded from checkpoint


# --------------------------------------------------------------------------- #
# broll.py beat-level resume
# --------------------------------------------------------------------------- #
def test_progress_round_trips_through_disk(tmp_path, monkeypatch):
    # Patch via `broll.settings` (the reference `broll.py` itself reads), not a
    # fresh `from app.config import settings` — see the long comment in
    # `test_resumable_stage_skips_the_second_call_via_stage_op` above for why
    # a fresh import can silently resolve to the wrong singleton in this suite.
    monkeypatch.setattr(broll.settings(), "data_dir", tmp_path)

    broll._save_progress_entry("job1", "s1", {"asset_path": None, "type": "solid", "motion": "none"})
    broll._save_progress_entry("job1", "s2", {"asset_path": None, "type": "branded", "motion": "none"})

    loaded = broll._load_progress("job1")
    assert set(loaded) == {"s1", "s2"}
    assert loaded["s2"]["type"] == "branded"


def test_progress_is_scoped_per_job(tmp_path, monkeypatch):
    # Patch via `broll.settings` (the reference `broll.py` itself reads), not a
    # fresh `from app.config import settings` — see the long comment in
    # `test_resumable_stage_skips_the_second_call_via_stage_op` above for why
    # a fresh import can silently resolve to the wrong singleton in this suite.
    monkeypatch.setattr(broll.settings(), "data_dir", tmp_path)

    broll._save_progress_entry("job_a", "s1", {"asset_path": None, "type": "solid", "motion": "none"})
    assert broll._load_progress("job_b") == {}


def test_snapshot_with_no_path_is_always_reusable():
    assert broll._snapshot_is_reusable({"asset_path": None, "type": "solid", "motion": "none"}) is True


def test_snapshot_with_missing_file_is_not_reusable(tmp_path):
    ghost = str(tmp_path / "does_not_exist.mp4")
    assert broll._snapshot_is_reusable({"asset_path": ghost, "type": "broll", "motion": "none"}) is False


def test_snapshot_with_existing_file_is_reusable(tmp_path):
    real = tmp_path / "clip.mp4"
    real.write_bytes(b"fake")
    assert broll._snapshot_is_reusable({"asset_path": str(real), "type": "broll", "motion": "none"}) is True


def test_apply_visual_snapshot_sets_fields():
    graph = SceneGraph.model_validate_json(_minimal_graph_json("apply_test"))
    scene = graph.scenes[0]
    broll._apply_visual_snapshot(scene, {"asset_path": "/x/y.mp4", "type": "broll", "motion": "ken_burns"})
    assert scene.visual.asset_path == "/x/y.mp4"
    assert scene.visual.type == "broll"
    assert scene.visual.motion == "ken_burns"


@pytest.mark.asyncio
async def test_dispatch_scene_resumable_skips_when_snapshot_is_reusable(monkeypatch, tmp_path):
    # Patch via `broll.settings` (the reference `broll.py` itself reads), not a
    # fresh `from app.config import settings` — see the long comment in
    # `test_resumable_stage_skips_the_second_call_via_stage_op` above for why
    # a fresh import can silently resolve to the wrong singleton in this suite.
    monkeypatch.setattr(broll.settings(), "data_dir", tmp_path)

    graph = SceneGraph.model_validate_json(_minimal_graph_json("skip_test"))
    scene = graph.scenes[0]
    calls = 0

    async def fake_dispatch(s, i, g, decision):
        nonlocal calls
        calls += 1
        s.visual.asset_path, s.visual.type = "/should/not/be/reached.mp4", "broll"

    monkeypatch.setattr(broll, "_dispatch_scene", fake_dispatch)

    progress = {"s1": {"asset_path": None, "type": "branded", "motion": "none"}}
    await broll._dispatch_scene_resumable(scene, 0, graph, decision=None, progress=progress)

    assert calls == 0                     # dispatch was skipped
    assert scene.visual.type == "branded"  # snapshot applied instead


@pytest.mark.asyncio
async def test_dispatch_scene_resumable_runs_and_persists_on_a_miss(monkeypatch, tmp_path):
    # Patch via `broll.settings` (the reference `broll.py` itself reads), not a
    # fresh `from app.config import settings` — see the long comment in
    # `test_resumable_stage_skips_the_second_call_via_stage_op` above for why
    # a fresh import can silently resolve to the wrong singleton in this suite.
    monkeypatch.setattr(broll.settings(), "data_dir", tmp_path)

    graph = SceneGraph.model_validate_json(_minimal_graph_json("run_test"))
    scene = graph.scenes[0]
    calls = 0

    async def fake_dispatch(s, i, g, decision):
        nonlocal calls
        calls += 1
        s.visual.asset_path, s.visual.type = None, "solid"

    monkeypatch.setattr(broll, "_dispatch_scene", fake_dispatch)

    await broll._dispatch_scene_resumable(scene, 0, graph, decision=None, progress={})

    assert calls == 1
    saved = broll._load_progress("run_test")
    assert saved["s1"]["type"] == "solid"
