#!/usr/bin/env python3
"""Revalidate the full-resolution production fixture with Phase 9 enabled."""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps"/"api")); sys.path.insert(0,str(ROOT/"scripts"))


async def main() -> int:
    from app.config import settings
    from app.pipeline import production_optimizer as opt
    import render_phase8_sample
    settings().production_optimizer_enabled=True
    result=await render_phase8_sample.main()
    if result: return result
    source=ROOT/"output"/"phase8_visual_qa"; target=ROOT/"output"/"phase9_optimizer"
    target.mkdir(parents=True,exist_ok=True)
    video=target/"phase9-production-sample.mp4"
    report=target/"phase9-production-sample.qa.json"
    shutil.copy2(source/"phase8-production-sample.mp4",video)
    payload=json.loads((source/"phase8-production-sample.qa.json").read_text())
    payload["media_path"]=str(video); report.write_text(json.dumps(payload,indent=2))
    (target/"optimizer-resources.json").write_text(json.dumps(
        {"resources":opt.asdict(opt.detect_resources()),"cache":opt.cache.snapshot()},indent=2))
    print(f"phase9_sample={video}")
    print(f"phase9_qa={report}")
    print(f"status={payload['status']}")
    return 0


if __name__=="__main__": raise SystemExit(asyncio.run(main()))
