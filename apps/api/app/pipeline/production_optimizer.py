"""Phase 9 resource-aware orchestration for the existing production pipeline.

This module supplies scheduling, cache coordination, checkpoints and batch
isolation. It owns no creative/render stages: callers pass the existing stage
functions into these bounded primitives.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import shutil
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Literal, TypeVar

from ..config import settings
from . import ram

T = TypeVar("T")
QueueState = Literal["queued", "running", "retrying", "failed", "qa_blocked", "completed"]


def _cgroup_limit_mb() -> float | None:
    for candidate in (Path("/sys/fs/cgroup/memory.max"),
                      Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")):
        try:
            raw = candidate.read_text().strip()
            if raw != "max":
                value = int(raw) / 1024 / 1024
                if value < 2**40: return value
        except (OSError, ValueError):
            pass
    return None


@dataclass(frozen=True)
class ResourceProfile:
    cpu_cores: int
    total_ram_mb: int
    available_ram_mb: int
    gpu: bool
    docker: bool
    wsl: bool
    job_concurrency: int
    cpu_stage_concurrency: int
    io_stage_concurrency: int
    browser_concurrency: int = 1
    tts_concurrency: int = 1


def detect_resources() -> ResourceProfile:
    cores = max(1, os.cpu_count() or 1)
    total = ram.total_mb() or 4096
    cgroup = _cgroup_limit_mb()
    if cgroup: total = min(total, cgroup)
    available = min(ram.available_mb() or total, total)
    wsl = "microsoft" in platform.release().lower() or bool(os.environ.get("WSL_DISTRO_NAME"))
    gpu = Path("/dev/nvidia0").exists() or Path("/dev/dri/renderD128").exists()
    docker = Path("/.dockerenv").exists() or Path("/var/run/docker.sock").exists()
    # On the target 4-core/low-memory WSL host: one full job, two CPU scene tasks,
    # and up to four lightweight network/discovery tasks.
    by_ram = max(1, int(max(0, total-settings().optimizer_memory_floor_mb) // 3200))
    jobs = min(settings().optimizer_max_jobs, max(1, cores//3), by_ram)
    return ResourceProfile(cores, round(total), round(available), gpu, docker, wsl,
        jobs, max(1, min(2 if cores <= 4 else cores//2, cores-1)),
        max(1, min(4, cores)), 1, 1)


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    bytes_reused: int = 0
    namespaces: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class CacheCoordinator:
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self.stats = CacheStats()

    def _count(self, namespace: str, field_name: str, size: int = 0) -> None:
        bucket = self.stats.namespaces.setdefault(namespace,
            {"hits": 0, "misses": 0, "writes": 0, "bytes_reused": 0})
        bucket[field_name] += 1 if field_name != "bytes_reused" else size
        setattr(self.stats, field_name, getattr(self.stats, field_name) +
                (size if field_name == "bytes_reused" else 1))

    @asynccontextmanager
    async def lock(self, namespace: str, key: str):
        lock = self._locks.setdefault(f"{namespace}:{key}", asyncio.Lock())
        async with lock:
            yield

    def observe(self, namespace: str, path: Path) -> bool:
        hit = path.is_file() and path.stat().st_size > 0
        self._count(namespace, "hits" if hit else "misses",
                    path.stat().st_size if hit else 0)
        if hit: self._count(namespace, "bytes_reused", path.stat().st_size)
        return hit

    def wrote(self, namespace: str) -> None:
        self._count(namespace, "writes")

    def snapshot(self) -> dict:
        return {**asdict(self.stats), "hit_rate": round(self.stats.hit_rate, 4)}

    def reset(self) -> None:
        self.stats = CacheStats()

    def prune(self, root: Path, *, max_bytes: int, max_age_days: int,
              reproducible: Callable[[Path], bool] | None = None) -> dict:
        if not root.is_dir(): return {"removed": 0, "bytes": 0}
        now = time.time(); entries=[]
        for path in root.rglob("*"):
            if path.is_file():
                try: entries.append((path.stat().st_mtime, path.stat().st_size, path))
                except OSError: pass
        total=sum(size for _,size,_ in entries); removed=freed=0
        for mtime,size,path in sorted(entries):
            too_old=(now-mtime) > max_age_days*86400
            if not too_old and total <= max_bytes: continue
            if reproducible and not reproducible(path): continue
            try:
                path.unlink(); removed += 1; freed += size; total -= size
            except OSError: pass
        return {"removed":removed,"bytes":freed,"remaining_bytes":total}


cache = CacheCoordinator()


@dataclass
class StageRecord:
    status: str
    attempts: int
    started_at: float
    completed_at: float = 0
    artifact: str = ""
    artifact_sha256: str = ""
    error: str = ""


class CheckpointStore:
    def __init__(self, job_id: str):
        self.root = settings().data_dir / "jobs" / job_id
        self.path = self.root / "optimizer-state.json"
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict:
        try: return json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError): return {"version":1,"stages":{}}

    def save(self, data: dict) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2, sort_keys=True))
        temp.replace(self.path)

    @staticmethod
    def digest(path: Path) -> str:
        h=hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024*1024), b""): h.update(block)
        return h.hexdigest()

    def valid(self, stage: str) -> bool:
        record=self.load().get("stages",{}).get(stage,{})
        if record.get("status") != "completed": return False
        artifact=Path(record.get("artifact", ""))
        return (artifact.is_file() and artifact.stat().st_size > 0 and
                self.digest(artifact) == record.get("artifact_sha256"))

    def record(self, stage: str, status: str, *, attempts: int = 1,
               artifact: str = "", error: str = "") -> None:
        data=self.load(); now=time.time(); old=data["stages"].get(stage,{})
        sha=self.digest(Path(artifact)) if artifact and Path(artifact).is_file() else ""
        data["stages"][stage] = asdict(StageRecord(status, attempts,
            old.get("started_at",now), now if status=="completed" else 0,
            artifact, sha, error))
        self.save(data)


class StageScheduler:
    def __init__(self, profile: ResourceProfile | None = None):
        self.profile=profile or detect_resources()
        self.cpu=asyncio.Semaphore(self.profile.cpu_stage_concurrency)
        self.io=asyncio.Semaphore(self.profile.io_stage_concurrency)
        self.browser=asyncio.Semaphore(1); self.tts=asyncio.Semaphore(1)
        self.timings: dict[str,float]={}

    async def wait_for_memory(self, cost_mb: int) -> None:
        deadline=time.monotonic()+settings().optimizer_backpressure_timeout_s
        while True:
            available=ram.available_mb()
            floor=max(settings().optimizer_memory_floor_mb,
                      settings().optimizer_memory_hard_floor_mb + cost_mb)
            if available is None or available >= floor: return
            if time.monotonic() >= deadline:
                raise MemoryError(f"resource budget denied: {available:.0f}MB available, {floor}MB required")
            await asyncio.sleep(.1)

    async def run(self, stage: str, operation: Callable[[], Awaitable[T]], *,
                  kind: Literal["cpu","io","browser","tts"]="cpu",
                  memory_mb: int=256, retries: int | None=None) -> T:
        await self.wait_for_memory(memory_mb)
        semaphore=getattr(self,kind); attempts=(settings().optimizer_max_retries
            if retries is None else retries)+1
        started=time.perf_counter()
        async with semaphore:
            for attempt in range(1,attempts+1):
                try:
                    result=await operation()
                    self.timings[stage]=self.timings.get(stage,0)+(time.perf_counter()-started)*1000
                    return result
                except Exception:
                    if attempt == attempts: raise
                    await asyncio.sleep(min(2**(attempt-1),4))
        raise RuntimeError("unreachable")

    async def map(self, stage: str, operations: list[Callable[[], Awaitable[T]]],
                  **kwargs) -> list[T]:
        return await asyncio.gather(*[self.run(f"{stage}:{i}",op,**kwargs)
                                      for i,op in enumerate(operations)])


scheduler = StageScheduler()


def scene_fingerprint(scene, brand_fingerprint: str) -> str:
    payload=json.dumps({"scene":scene.model_dump(mode="json"),"brand":brand_fingerprint},
                       sort_keys=True,separators=(",",":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def changed_scenes(graph, approved_manifest: dict, brand_fingerprint: str) -> list[str]:
    previous=approved_manifest.get("scenes",{})
    return [scene.id for scene in graph.scenes
            if previous.get(scene.id) != scene_fingerprint(scene,brand_fingerprint)]


def preview_manifest(graph, brand_fingerprint: str, *, quality: str="preview") -> dict:
    return {"video_id":graph.meta.video_id,"quality":quality,"approved":False,
            "scenes":{scene.id:scene_fingerprint(scene,brand_fingerprint)
                      for scene in graph.scenes}}


async def render_changed_scenes(graph, approved_manifest: dict, brand_fingerprint: str,
                                renderer: Callable[[object],Awaitable[T]]) -> dict[str,T]:
    """Promote only changed/never-approved scenes; final composition and QA stay
    downstream and always run over the complete timeline."""
    changed=set(changed_scenes(graph,approved_manifest,brand_fingerprint))
    results=await scheduler.map("preview_to_final",[
        (lambda scene=scene: renderer(scene)) for scene in graph.scenes if scene.id in changed],
        kind="cpu",memory_mb=400)
    return dict(zip([s.id for s in graph.scenes if s.id in changed],results))


async def resumable_stage(store: CheckpointStore, stage: str,
                          operation: Callable[[],Awaitable[T]], *,
                          dump: Callable[[T,Path],None], load: Callable[[Path],T]) -> T:
    state=store.load().get("stages",{}).get(stage,{})
    if store.valid(stage): return load(Path(state["artifact"]))
    attempts=int(state.get("attempts",0))+1
    store.record(stage,"running",attempts=attempts)
    try:
        result=await operation(); artifact=store.root/f"{stage}.checkpoint"
        dump(result,artifact); store.record(stage,"completed",attempts=attempts,artifact=str(artifact))
        return result
    except Exception as exc:
        store.record(stage,"failed",attempts=attempts,error=f"{type(exc).__name__}: {exc}")
        raise


def graph_cache_report(graph, *, captions_hit: bool=False,
                       composite_hit: bool=False) -> dict:
    namespaces={
        "assets":{"hits":sum(1 for r in graph.asset_provenance if r.status=="resolved"),
                  "misses":sum(1 for r in graph.asset_provenance if r.status!="resolved")},
        "motion_graphics":{"hits":sum(1 for r in graph.motion_graphics_provenance if r.status=="cache_hit"),
                           "misses":sum(1 for r in graph.motion_graphics_provenance if r.status!="cache_hit")},
        "threejs":{"hits":sum(1 for r in graph.threejs_provenance if r.status=="cache_hit"),
                   "misses":sum(1 for r in graph.threejs_provenance if r.status!="cache_hit")},
        "ai_broll":{"hits":sum(1 for r in graph.ai_broll_provenance if r.status=="cache_hit"),
                    "misses":sum(1 for r in graph.ai_broll_provenance if r.status!="cache_hit")},
        "captions":{"hits":int(captions_hit),"misses":int(not captions_hit)},
        "scene_composites":{"hits":int(composite_hit),"misses":int(not composite_hit)},
    }
    hits=sum(v["hits"] for v in namespaces.values()); misses=sum(v["misses"] for v in namespaces.values())
    return {"hits":hits,"misses":misses,"hit_rate":hits/(hits+misses) if hits+misses else 0,
            "namespaces":namespaces}


@dataclass
class QueueResult:
    job_id: str
    state: QueueState
    attempts: int
    error: str = ""


async def run_batch(job_ids: list[str], runner: Callable[[str], Awaitable[object]],
                    *, max_concurrency: int | None=None, retries: int=1) -> list[QueueResult]:
    limit=asyncio.Semaphore(max_concurrency or detect_resources().job_concurrency)
    async def one(job_id: str) -> QueueResult:
        root=settings().data_dir/"jobs"/job_id; root.mkdir(parents=True,exist_ok=True)
        log=root/"production-queue.json"; state="queued"
        for attempt in range(1,retries+2):
            state="running" if attempt==1 else "retrying"
            log.write_text(json.dumps({"job_id":job_id,"state":state,"attempt":attempt}))
            try:
                async with limit: await runner(job_id)
                log.write_text(json.dumps({"job_id":job_id,"state":"completed","attempt":attempt}))
                return QueueResult(job_id,"completed",attempt)
            except Exception as exc:
                if attempt > retries:
                    qa_blocked="QA" in str(exc).upper()
                    final="qa_blocked" if qa_blocked else "failed"
                    log.write_text(json.dumps({"job_id":job_id,"state":final,"attempt":attempt,
                                               "error":f"{type(exc).__name__}: {exc}"}))
                    return QueueResult(job_id,final,attempt,f"{type(exc).__name__}: {exc}")
        raise RuntimeError("unreachable")
    return await asyncio.gather(*[one(job_id) for job_id in job_ids])
