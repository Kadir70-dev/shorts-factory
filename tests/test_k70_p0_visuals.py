"""P0 regression checks: original K70 layouts, distribution, 3D readiness.

Existing F1/F2/F3 tests must also continue passing on the target laptop.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"apps"/"api"))

from app.pipeline import motiongfx
from tools.finance_cinematic_cpu.p0 import spread_items, timeline_report
from scripts import k70_p0_visual_audit as audit


def _graph(n=24):
    scenes=[]
    for i in range(n):
        scenes.append(NS(id=f"s{i}",duration_sec=5.0,visual=NS(
            type="ai_image" if i%3==0 else "motion_gfx",
            budget_channel="ai_broll" if i%3==0 else "motion_gfx")))
    return NS(scenes=scenes)


def test_layouts_are_distinct_and_readable():
    positions=[]
    for layout in motiongfx.LAYOUTS:
        y,x,align=motiongfx.kinetic_layout_geometry(layout,640,360,65)
        assert 36<=y<310 and x
        assert align in ("center","left","right")
        positions.append((y,x))
    assert len(motiongfx.LAYOUTS)>=5
    assert len(set(positions))>=4
    with pytest.raises(ValueError):
        motiongfx.kinetic_layout_geometry("untrusted_layout",640,360,65)


def test_spread_covers_documentary_not_just_cold_open():
    g=_graph()
    candidates=[{"scene_id":f"s{i}","query":f"scene-{i}"} for i in range(24)]
    chosen=spread_items(g,candidates,limit=6)
    numbers=[int(it["scene_id"][1:]) for it in chosen]
    assert len(chosen)==6
    assert numbers==sorted(numbers)
    assert min(numbers)<6 and max(numbers)>=18
    assert spread_items(g,candidates,limit=6)==chosen


def test_sparse_spread_never_duplicates_or_invents():
    g=_graph()
    items=[{"scene_id":"s0"},{"scene_id":"s1"},{"scene_id":"s23"}]
    assert {x["scene_id"] for x in spread_items(g,items,limit=8)}=={"s0","s1","s23"}
    assert spread_items(g,[],limit=8)==[]
    assert spread_items(g,[{"scene_id":"ghost"}],limit=8)==[]
    with pytest.raises(ValueError):
        spread_items(g,items,limit=0)


def test_mix_segments_and_planned_vs_delivered():
    g=_graph(24)
    r=timeline_report(g,segments=4)
    assert r["total_duration_sec"]==120.0
    assert r["scene_count"]==24
    assert r["actual_types"]["ai_image"]==8
    assert sum(z["cinematic_count"] for z in r["zones"])==8
    assert all(z["end_sec"]>z["start_sec"] for z in r["zones"])


def test_threejs_readiness_reports_missing_before_runtime(tmp_path,monkeypatch):
    monkeypatch.setattr(audit,"_which_node",lambda: tmp_path/"node")
    app=tmp_path/"apps"/"remotion"/"node_modules"
    app.mkdir(parents=True)
    result=audit.threejs_readiness(tmp_path)
    assert result["dependency_preflight_passed"] is False
    assert "npm ci" in result["fix_if_missing"]
    for name in ("three","puppeteer","typescript"):
        (app/name).mkdir()
        (app/name/"package.json").write_text("{}")
    (app/".bin").mkdir()
    (app/".bin"/"tsc").write_text("bin")
    result=audit.threejs_readiness(tmp_path)
    assert result["dependency_preflight_passed"] is True
    assert result["browser_launch"]=="not_checked"


def test_kinetic_first_headline_is_visible_at_time_zero(tmp_path,monkeypatch):
    """No more first-frame empty slate before kinetic headline appears."""
    calls=[]
    class Font:
        path=""
        @staticmethod
        def apply_case(s): return s
    class FakeTheme:
        fingerprint="fake-k70"
        background={}
        display=Font()
        body=Font()
        @staticmethod
        def rgb(_): return (110,155,200)
        @staticmethod
        def ff(_): return "#CCDDEE"
        @staticmethod
        def size(role,h): return 20 if role=="source" else 44
    async def write(frames,w,h,fps,out,vf=None):
        frame=next(iter(frames))
        assert frame.w==w and frame.h==h
        return out
    monkeypatch.setattr(motiongfx,"_cached",lambda *a:None)
    monkeypatch.setattr(motiongfx,"write_video",write)
    monkeypatch.setattr(motiongfx,"visual_cache_store",lambda *a:None)
    monkeypatch.setattr(motiongfx,"visual_cache_path",lambda *a:tmp_path/"cache.mp4")
    monkeypatch.setattr(motiongfx.tx,"drawtext",
                        lambda text,**kw: calls.append((text,kw)) or "null")
    out=tmp_path/"scene.mp4"
    asyncio.run(motiongfx.kinetic(FakeTheme(),out,320,480,12,2.5,
                                headline="How an economy changes when the money supply expands",
                                layout="split_left",treatment="grid_drift"))
    assert calls
    assert calls[0][1]["alpha"]==1.0
    assert calls[0][1]["x"]==str(int(320*.095))
