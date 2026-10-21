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


def test_bitcoin_f4_p0_job_metadata_changes_but_narrative_fingerprint_is_stable():
    baseline = json.loads((ROOT / "data/series/bitcoin_history/ep01/scene_graph.json").read_text())
    voiced = copy.deepcopy(baseline)
    assert prio.is_legacy_bitcoin_history(baseline["meta"], 156)
    assert prio.is_bitcoin_episode_content(baseline["scenes"])
    # Simulate real local F4 and voiced P0 files: job-specific metadata and two
    # altered voiceover lines; neither is a different 156-beat film.
    baseline["meta"].update(video_id="finance_history_ep01_f4",
                            niche="usa_history",
                            channel_id="k70_finance_longform",
                            title="Bitcoin Episode 1 — Authored F4")
    voiced["meta"].update(video_id="k70_f4_bitcoin_ep01",
                          niche="usa_history",
                          channel_id="legacy_documentary_job",
                          title="F4 premium Bitcoin documentary")
    voiced["scenes"][29]["narration"] = "A race sharply higher."
    voiced["scenes"][125]["narration"] = (
        "Within weeks the central bank would print an one hundred trillion dollar note.")
    assert prio.is_bitcoin_episode_content(baseline["scenes"])
    assert prio.is_bitcoin_episode_content(voiced["scenes"])
    legacy = Obj(meta=Obj(**voiced["meta"]),
                 scenes=[Obj(id=row["id"], narration=row["narration"],
                             duration_sec=row["duration_sec"]) for row in voiced["scenes"]],
                 width=1080, height=1920)
    assert prio.is_finance_longform(legacy)
    report = repair.inspect(baseline, voiced, ROOT)
    assert report["scope"] == "legacy_bitcoin_history_ep01"
    assert report["total_scenes"] == 156
    assert all(item["scene_id"] not in ("s30", "s126")
               for item in report["lost_sourced_charts"])


def test_unrelated_history_content_does_not_gain_finance_repair_access():
    original = json.loads((ROOT / "data/series/bitcoin_history/ep01/scene_graph.json").read_text())
    unrelated = copy.deepcopy(original)
    # Metadata is not an identity proof; changing narrative identity must
    # reject even if the name, channel and number of scenes remain similar.
    for i in (34, 66, 81, 125):
        unrelated["scenes"][i]["narration"] = "Unrelated history topic."
    assert not prio.is_bitcoin_episode_content(unrelated["scenes"])
    with pytest.raises(ValueError, match="not an identified K70 Bitcoin"):
        repair.inspect(original, unrelated, ROOT)

    # A mismatched baseline with the right scene IDs is not sufficient.
    with pytest.raises(ValueError, match="not an identified K70 Bitcoin"):
        repair.inspect(unrelated, original, ROOT)


def test_standard_finance_jobs_still_need_matching_video_ids():
    names = [f"s{i}" for i in range(1, 31)]
    meta = {"video_id": "test_finance_film", "niche": "usa_finance"}
    original = {"meta": copy.deepcopy(meta),
                "scenes": [p0_scene(id) for id in names]}
    voiced = {"meta": {"video_id": "different_film", "niche": "usa_finance"},
              "scenes": copy.deepcopy(original["scenes"]), "width": 640, "height": 360}
    with pytest.raises(ValueError, match="same video ID"):
        repair.inspect(original, voiced, ROOT)



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
    return {"id": sid, "narration": narrator, "duration_sec": 8,
            "visual": visual(kind), "data": data if chart else None,
            "overlays": [], "transition_in": "cut"}


def test_repair_plan_finds_only_lost_data_charts_and_keeps_narration():
    names = [f"s{i}" for i in range(1, 31)]
    meta = {"video_id": "test_finance_film", "niche": "usa_finance"}
    baseline = {"meta": copy.deepcopy(meta), "scenes": [p0_scene(sid) for sid in names]}
    voiced = {"meta": copy.deepcopy(meta), "width": 640, "height": 360,
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
