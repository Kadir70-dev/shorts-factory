"""P0.1/P0.2 regression: authored 3D restore and whole-film cinematic spread.

CPU-only, no network, no browser, no generation.
"""
from __future__ import annotations
import copy
import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.pipeline import visual_budget as vb
from app.schemas.scene import Scene
from scripts import k70_p0_cinematic_balance as balance
from scripts import k70_p0_threejs_restore as restore
from tools.finance_cinematic_cpu.auto import select_scenes


class Graph(NS):
    def model_copy(self, *, deep):
        return copy.deepcopy(self)


def _ai(sid, img, role="", duration=5.0, overlays=None, data=None):
    v = NS(type="ai_image", budget_channel="ai_broll", asset_path=str(img),
           motion="ken_burns", layers=[], evidence_card_path=None,
           scene_visual_type="dramatic", visual_intent="vault")
    return NS(id=sid, duration_sec=duration, visual=v, narration="Money changed.",
              beat_role=role, data=data, overlays=overlays or [])


def _film(tmp_path, n=24):
    img = tmp_path / "still.jpg"
    Image.new("RGB", (64, 64), "navy").save(img)
    # Hook/tension roles score higher: the old ranking spent the budget early.
    scenes = [_ai(f"s{i}", img, role="hook" if i < 8 else "") for i in range(n)]
    return Graph(width=1080, height=1920, fps=30, scenes=scenes)


def _quarters(report, total):
    return {min(4, int(p["start_sec"] / total * 4) + 1) for p in report["selected"]}


def test_balanced_clips_cover_the_whole_film_not_the_opening(tmp_path):
    g = _film(tmp_path)
    old = select_scenes(g, max_clips=6, spacing_sec=5)
    new = select_scenes(g, max_clips=6, spacing_sec=5, balanced=True)
    assert _quarters(old, 120) == {1}              # the F4 failure mode
    assert _quarters(new, 120) == {1, 2, 3, 4}
    assert new["selected_count"] == 6 and new["balanced"] is True
    assert [p["start_sec"] for p in new["selected"]] == \
        sorted(p["start_sec"] for p in new["selected"])


def test_balanced_keeps_every_f2_safety_filter(tmp_path):
    g = _film(tmp_path, n=12)
    g.scenes[5].overlays = [NS(type="source", text="Fed")]
    g.scenes[7].data = NS(valid=lambda: True)
    g.scenes[9].visual.type = "dataviz"
    r = select_scenes(g, max_clips=8, spacing_sec=0, balanced=True)
    picked = {p["scene_id"] for p in r["selected"]}
    assert not picked & {"s5", "s7", "s9"}


def test_restore_uses_authored_place_and_marks_beat_3d():
    authored = {"scenes": [
        {"id": "s31", "visual": {"type": "threejs", "query": "Japan"}},
        {"id": "s32", "visual": {"type": "motion_gfx", "query": "x"}}]}
    assert restore.authored_threejs(authored) == {"s31": "Japan"}

    class Beat(NS):
        def model_copy(self, *, update):
            return Beat(**{**vars(self), **update})
    beat = Beat(source_scene_id="s31", scene_id="s31.b1", location="",
                threejs_candidate=False, recommended_visual_type="motion_gfx",
                ai_broll_candidate=True)
    graph = NS(storyboard=NS(scenes=[beat]))
    out = restore.restore_beat(graph, "s31", "Japan")
    assert (out.location, out.threejs_candidate, out.ai_broll_candidate) == \
        ("Japan", True, False)
    assert beat.location == "" and beat.threejs_candidate is False   # input untouched
    assert restore.restore_beat(graph, "s99", "Peru") is None


def _scene(sid, kind, query="Thailand"):
    return Scene.model_validate({
        "id": sid, "narration": f"Nineteen ninety-seven. {query}'s currency broke.",
        "duration_sec": 5.0,
        "visual": {"type": kind, "query": query, "visual_intent": "Globe flight"},
        "overlays": [], "beat_role": "context"})


def test_budget_pins_authored_3d_only_when_band_allows():
    scenes = [_scene("s1", "threejs"), _scene("s2", "motion_gfx", "Russia"),
              _scene("s3", "threejs", "Hungary")]
    graph = NS(scenes=scenes)
    base = vb.policy()
    shut = vb.allocate(graph, dataclasses.replace(
        base, bands={**base.bands, "threejs": vb.Band(0.0, 0.0)}))
    assert {a.scene_id for a in shut.assignments if a.channel == "threejs"} <= {"s1"}
    open_ = vb.allocate(graph, dataclasses.replace(
        base, bands={**base.bands, "threejs": vb.Band(0.0, 0.7)}))
    got = {a.scene_id: a.channel for a in open_.assignments}
    assert got["s1"] == "threejs" and got["s3"] == "threejs"


def test_protected_content_check_flags_narration_overlay_and_stray_visuals():
    def s(sid, text="a", vis="v"):
        return NS(id=sid, narration=text, overlays=[], data=None,
                  duration_sec=1.0, visual=vis)
    before = NS(scenes=[s("s1"), s("s2"), s("s3")])
    after = NS(scenes=[s("s1", vis="clip"), s("s2", text="changed"), s("s3", vis="x")])
    assert balance.protected_unchanged(before, after, {"s1"}) == ["s2", "s3"]
    assert balance.mmss(125.5) == "2:05.5"


def test_render_v2_refuses_bad_overrides_and_existing_output(tmp_path):
    import asyncio
    import pytest
    from scripts import k70_p0_render_v2 as v2
    clip = tmp_path / "card.mp4"
    clip.write_bytes(b"x")
    assert v2.parse_overrides([f"s102={clip}"]) == {"s102": clip.resolve()}
    for bad in ("s102", f"={clip}", f"s1={tmp_path/'none.mp4'}", f"s1={tmp_path}"):
        with pytest.raises(SystemExit):
            v2.parse_overrides([bad])
    taken = tmp_path / "out"
    taken.mkdir()
    args = NS(out_dir=taken, job=tmp_path, graph=tmp_path / "g.json", override=[])
    with pytest.raises(SystemExit, match="never overwrite"):
        asyncio.run(v2.run(args))
