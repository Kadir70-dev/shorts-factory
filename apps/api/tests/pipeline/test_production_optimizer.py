from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.config import settings
from app.pipeline import production_optimizer as opt
from app.pipeline import threejs_engine


def profile(**changes):
    base=dict(cpu_cores=4,total_ram_mb=8192,available_ram_mb=6000,gpu=False,
              docker=False,wsl=True,job_concurrency=1,cpu_stage_concurrency=2,
              io_stage_concurrency=4,browser_concurrency=1,tts_concurrency=1)
    base.update(changes); return opt.ResourceProfile(**base)


def test_resource_detection_is_bounded(monkeypatch):
    monkeypatch.setattr(opt.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(opt.ram, "total_mb", lambda: 8192)
    monkeypatch.setattr(opt.ram, "available_mb", lambda: 5000)
    monkeypatch.setattr(opt, "_cgroup_limit_mb", lambda: None)
    result=opt.detect_resources()
    assert result.job_concurrency == 1
    assert result.cpu_stage_concurrency == 2
    assert result.browser_concurrency == result.tts_concurrency == 1


@pytest.mark.asyncio
async def test_scheduler_bounds_cpu_parallelism(monkeypatch):
    monkeypatch.setattr(opt.ram, "available_mb", lambda: 8000)
    scheduler=opt.StageScheduler(profile())
    active=peak=0
    async def operation():
        nonlocal active,peak
        active+=1; peak=max(peak,active); await asyncio.sleep(.02); active-=1
        return True
    results=await scheduler.map("motion", [operation for _ in range(6)],
                                kind="cpu", memory_mb=50, retries=0)
    assert all(results) and peak == 2


@pytest.mark.asyncio
async def test_memory_floor_applies_backpressure(monkeypatch):
    monkeypatch.setattr(opt.ram, "available_mb", lambda: 200)
    monkeypatch.setattr(settings(), "optimizer_backpressure_timeout_s", .01)
    with pytest.raises(MemoryError):
        await opt.StageScheduler(profile()).wait_for_memory(600)


@pytest.mark.asyncio
async def test_cache_key_lock_deduplicates_concurrent_work(tmp_path):
    coordinator=opt.CacheCoordinator(); target=tmp_path/"render.bin"; calls=0
    async def produce():
        nonlocal calls
        async with coordinator.lock("motion", "same"):
            if coordinator.observe("motion",target): return target.read_text()
            calls+=1; await asyncio.sleep(.02); target.write_text("valid"); coordinator.wrote("motion")
            return "valid"
    assert await asyncio.gather(produce(),produce(),produce()) == ["valid"]*3
    assert calls == 1 and coordinator.stats.hits == 2 and coordinator.stats.misses == 1


def test_safe_cache_pruning_keeps_nonreproducible(tmp_path):
    old=tmp_path/"old.cache"; protected=tmp_path/"protected.voice"
    old.write_bytes(b"x"*20); protected.write_bytes(b"y"*20)
    result=opt.CacheCoordinator().prune(tmp_path,max_bytes=10,max_age_days=0,
        reproducible=lambda path: path.suffix == ".cache")
    assert result["removed"] == 1 and not old.exists() and protected.exists()


def test_checkpoint_resume_rejects_stale_or_modified_output(tmp_path, monkeypatch):
    monkeypatch.setattr(settings(), "data_dir", tmp_path)
    store=opt.CheckpointStore("job1"); artifact=store.root/"scene.json"; artifact.write_text("v1")
    store.record("assets","completed",artifact=str(artifact))
    assert store.valid("assets")
    artifact.write_text("stale")
    assert not store.valid("assets")


@pytest.mark.asyncio
async def test_retry_is_capped(monkeypatch):
    monkeypatch.setattr(opt.ram,"available_mb",lambda:8000)
    attempts=0
    async def flaky():
        nonlocal attempts
        attempts+=1
        if attempts < 3: raise RuntimeError("temporary")
        return "ok"
    assert await opt.StageScheduler(profile()).run("provider",flaky,kind="io",retries=2) == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_three_job_queue_isolates_failure_and_qa_block(tmp_path, monkeypatch):
    monkeypatch.setattr(settings(),"data_dir",tmp_path)
    async def runner(job_id):
        if job_id == "bad": raise RuntimeError("provider failed")
        if job_id == "qa": raise RuntimeError("QA failed")
    results=await opt.run_batch(["ok","bad","qa"],runner,max_concurrency=2,retries=1)
    assert [r.state for r in results] == ["completed","failed","qa_blocked"]
    assert all((tmp_path/"jobs"/r.job_id/"production-queue.json").is_file() for r in results)


def test_preview_manifest_rerenders_only_changed_scene(graph):
    approved={"scenes":{s.id:opt.scene_fingerprint(s,"brand") for s in graph.scenes}}
    assert opt.changed_scenes(graph,approved,"brand") == []
    graph.scenes[1].narration += " Changed."
    assert opt.changed_scenes(graph,approved,"brand") == [graph.scenes[1].id]


@pytest.mark.asyncio
async def test_preview_to_final_calls_only_changed_renderer(graph, monkeypatch):
    monkeypatch.setattr(opt.ram,"available_mb",lambda:8000)
    manifest=opt.preview_manifest(graph,"brand"); graph.scenes[2].narration += " updated"
    called=[]
    async def renderer(scene): called.append(scene.id); return f"final:{scene.id}"
    result=await opt.render_changed_scenes(graph,manifest,"brand",renderer)
    assert called == [graph.scenes[2].id] and list(result) == called


@pytest.mark.asyncio
async def test_resumable_stage_loads_valid_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings(),"data_dir",tmp_path)
    store=opt.CheckpointStore("resume"); calls=0
    async def operation():
        nonlocal calls; calls+=1; return "payload"
    dump=lambda value,path:path.write_text(value)
    load=lambda path:path.read_text()
    assert await opt.resumable_stage(store,"storyboard",operation,dump=dump,load=load) == "payload"
    assert await opt.resumable_stage(store,"storyboard",operation,dump=dump,load=load) == "payload"
    assert calls == 1


def test_unified_cache_report_has_all_pipeline_namespaces(graph):
    report=opt.graph_cache_report(graph)
    assert set(report["namespaces"]) == {"assets","motion_graphics","threejs",
        "ai_broll","captions","scene_composites"}


@pytest.mark.asyncio
async def test_browser_worker_restarts_at_job_threshold(monkeypatch):
    class In:
        def write(self, value): pass
        async def drain(self): pass
    class Out:
        async def readline(self): return b'{"ok":true,"rssMb":40}\n'
    class Worker:
        returncode=None; stdin=In(); stdout=Out(); stderr=Out()
    stopped=[]
    async def stop(): stopped.append(True); threejs_engine._worker=None; threejs_engine._worker_jobs=0
    async def ensure(): return Worker()
    monkeypatch.setattr(settings(),"production_optimizer_enabled",True)
    monkeypatch.setattr(settings(),"optimizer_threejs_restart_jobs",1)
    monkeypatch.setattr(threejs_engine,"_worker",Worker())
    monkeypatch.setattr(threejs_engine,"_worker_jobs",1)
    monkeypatch.setattr(threejs_engine,"_stop_worker",stop)
    monkeypatch.setattr(threejs_engine,"_ensure_worker",ensure)
    result=await threejs_engine._worker_render({"id":"test"})
    assert result["ok"] and stopped


def test_optimizer_defaults_off():
    assert settings().production_optimizer_enabled is False
