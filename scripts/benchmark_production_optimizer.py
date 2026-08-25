#!/usr/bin/env python3
"""Cold/warm single and three-Short Phase 9 scheduler benchmark."""
from __future__ import annotations

import asyncio
import json
import resource
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps"/"api"))

from app.config import settings
from app.pipeline import production_optimizer as opt


async def execute(short_id: str, root: Path, coordinator: opt.CacheCoordinator,
                  scheduler: opt.StageScheduler) -> dict:
    stages=("storyboard","asset_discovery","captions","motion_a","motion_b","composite")
    async def stage(name: str):
        key=f"{short_id}-{name}"; path=root/key
        async with coordinator.lock(name,key):
            if coordinator.observe(name,path): return "hit"
            await asyncio.sleep(.012 if "motion" in name else .006)
            path.write_bytes((key*200).encode()); coordinator.wrote(name); return "miss"
    started=time.perf_counter()
    results=await scheduler.map(short_id,[lambda name=name: stage(name) for name in stages],
                                kind="cpu",memory_mb=64,retries=0)
    return {"wall_ms":(time.perf_counter()-started)*1000,"hits":results.count("hit"),
            "misses":results.count("miss"),"stage_timings_ms":dict(scheduler.timings)}


async def main():
    settings().production_optimizer_enabled=True
    with tempfile.TemporaryDirectory(prefix="phase9-benchmark-") as temp:
        root=Path(temp); coordinator=opt.CacheCoordinator()
        scheduler=opt.StageScheduler(opt.detect_resources())
        cpu0=time.process_time(); cold=await execute("single",root,coordinator,scheduler)
        cold_stats=coordinator.snapshot(); coordinator.reset(); scheduler.timings.clear()
        warm=await execute("single",root,coordinator,scheduler); warm_stats=coordinator.snapshot()

        async def batch(cold_batch: bool):
            if not cold_batch:
                # same IDs intentionally exercise reproducible warm reuse
                pass
            start=time.perf_counter()
            async def runner(job_id): return await execute(job_id,root,coordinator,scheduler)
            result=await opt.run_batch(["batch-1","batch-2","batch-3"],runner,
                max_concurrency=opt.detect_resources().job_concurrency,retries=0)
            return (time.perf_counter()-start)*1000,[r.state for r in result]
        coordinator.reset(); batch_cold_ms,batch_cold_states=await batch(True)
        batch_cold_stats=coordinator.snapshot(); coordinator.reset()
        batch_warm_ms,batch_warm_states=await batch(False)
        batch_warm_stats=coordinator.snapshot()
        profile=opt.detect_resources()
        payload={"resource_profile":opt.asdict(profile),"single_cold":cold,
            "single_cold_cache":cold_stats,"single_warm":warm,"single_warm_cache":warm_stats,
            "batch_three_cold":{"wall_ms":batch_cold_ms,"states":batch_cold_states,
                                "cache":batch_cold_stats},
            "batch_three_warm":{"wall_ms":batch_warm_ms,"states":batch_warm_states,
                                "cache":batch_warm_stats},
            "cpu_seconds":round(time.process_time()-cpu0,4),
            "peak_rss_mb":round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
            "fixture":"offline non-production stage workload","target_claimed":False}
        destination=ROOT/"output"/"phase9_optimizer"/"benchmark.json"
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(json.dumps(payload,indent=2))
        print(json.dumps(payload,indent=2)); print(f"benchmark={destination}")


if __name__=="__main__": asyncio.run(main())
