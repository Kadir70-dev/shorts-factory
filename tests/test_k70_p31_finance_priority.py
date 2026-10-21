"""P3.1 priority and historical graph repair tests; no network or render needed."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as Obj

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prio = load("k70_finance_priority", "apps/api/app/pipeline/finance_documentary_priority.py")
repair = load("k70_finance_repair", "scripts/k70_p31_evidence_repair.py")


def simple_scene(sid, kind="broll", with_data=False):
    data = Obj(valid=lambda: True, source="Treasury archive") if with_data else None
    return Obj(id=sid, duration_sec=10, visual=Obj(type=kind),
               data=data)


def sample_graph(*, niche="usa_finance", portrait=False, duration=30):
    scenes = [simple_scene(f"s{i}") for i in range(duration)]
    return Obj(meta=Obj(niche=niche), scenes=scenes,
               width=360 if portrait else 640,
               height=640 if portrait else 360,
               storyboard=Obj(scenes=[]), asset_provenance=[])


def test_scope_ignores_shorts_other_niches_and_portrait():
    assert prio.is_finance_longform(sample_graph())
    assert not prio.is_finance_longform(sample_graph(niche="usa_history"))
    assert not prio.is_finance_longform(sample_graph(portrait=True))
    assert not prio.is_finance_longform(sample_graph(duration=4))
    assert prio.authored_chart_ids(sample_graph()) == set()


def test_explicit_source_backed_chart_only():
    graph = sample_graph()
    graph.scenes[0] = simple_scene("s0", "dataviz", with_data=True)
    graph.scenes[1] = simple_scene("s1", "dataviz")
    graph.scenes[2] = simple_scene("s2", "broll", with_data=True)
    assert prio.authored_chart_ids(graph) == {"s0"}


def test_licensed_specific_archive_selected_and_not_guessing():
    graph = sample_graph()
    graph.storyboard = Obj(scenes=[Obj(scene_id="s2.a", source_scene_id="s2")])
    c = Obj(source_url="https://commons.wikimedia.org/file/example.jpg",
            provider_institution="wikimedia_commons",
            commercial_use_status="allowed", local_cache_path="/tmp/a.jpg",
            relevance_score=.95, subject_specificity=.9, confidence=.88,
            license="CC BY 4.0", attribution_requirement="Attribution",
            )
    graph.asset_provenance = [
        Obj(scene_id="s2.a", status="resolved",
            selected_source_url=c.source_url, candidates=[c])
    ]
    yes = lambda row: row.license == "CC BY 4.0"
    got = prio.archive_choice(graph, "s2", "/tmp/a.jpg", license_ok=yes)
    assert got["provider"] == "wikimedia_commons"
    assert got["attribution_requirement"] == "Attribution"
    assert prio.archive_choice(graph, "s2", "/tmp/b.jpg", license_ok=yes) is None
    assert prio.archive_choice(graph, "s3", "/tmp/a.jpg", license_ok=yes) is None
    assert prio.archive_choice(graph, "s2", "/tmp/a.jpg",
                               license_ok=lambda row: False) is None
    c.confidence = .1
    assert prio.archive_choice(graph, "s2", "/tmp/a.jpg", license_ok=yes) is None


def visual(kind="broll"):
    return {"type": kind, "budget_channel": "stock", "asset_path": "old.mp4",
            "layers": [], "motion": "none", "strategy": "real"}


def p0_scene(sid, *, kind="broll", chart=False, narrator="Historical fact."):
    data = {"source": "Official original document",
            "kind": "counter", "points": [{"label": "Historical", "value": 42}]}
    return {"id": sid, "narration": narrator, "duration_sec": 6,
            "visual": visual(kind), "data": data if chart else None,
            "overlays": [], "transition_in": "cut"}


def test_repair_plan_finds_only_lost_data_charts_and_keeps_narration():
    names = [f"s{i}" for i in range(1, 31)]
    baseline = {"scenes": [p0_scene(sid) for sid in names]}
    voiced = {"meta": {"niche": "usa_finance"}, "width": 640, "height": 360,
              "scenes": copy.deepcopy(baseline["scenes"])}
    for sid in ("s35", "s67"):
        baseline["scenes"].append(p0_scene(sid, kind="dataviz", chart=True))
        voiced["scenes"].append(p0_scene(sid, kind="broll", chart=True))
    before = copy.deepcopy(voiced)
    report = repair.inspect(baseline, voiced, ROOT)
    assert {x["scene_id"] for x in report["lost_sourced_charts"]} == {"s35", "s67"}
    assert report["qualified_archive_replacements"] == []
    assert voiced == before
    assert repair._source_chart(baseline["scenes"][-1], voiced["scenes"][-1])


def test_chart_restore_refuses_changed_spoken_claim_and_unattributed_number():
    baseline = p0_scene("s35", kind="dataviz", chart=True)
    changed = p0_scene("s35", kind="broll", chart=True,
                       narrator="Different spoken historical claim.")
    assert not repair._source_chart(baseline, changed)
    same = p0_scene("s35", kind="broll", chart=True)
    baseline["data"]["source"] = ""
    same["data"]["source"] = ""
    assert not repair._source_chart(baseline, same)


def test_patch_only_changes_visual_and_keeps_history():
    scene = p0_scene("s17")
    before = copy.deepcopy(scene)
    repair._apply_archive(scene, {"path": "/repo/data/cache/exact_archive.jpg"})
    assert scene["visual"]["type"] == "image"
    assert scene["visual"]["budget_channel"] == "official"
    assert scene["visual"]["asset_path"].endswith("exact_archive.jpg")
    assert scene["narration"] == before["narration"]
    assert scene["duration_sec"] == before["duration_sec"]
    assert scene["data"] == before["data"]


def test_cli_help_requires_no_venv_or_remote_packages():
    cmd = [sys.executable, str(ROOT / "scripts/k70_p31_evidence_repair.py"), "--help"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
    assert p.returncode == 0, p.stderr
    assert "--baseline" in p.stdout
    assert "--apply" in p.stdout
    assert "--min-free-gb" in p.stdout
