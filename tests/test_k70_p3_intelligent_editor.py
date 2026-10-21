"""K70 P3 Intelligent Documentary Editor tests: no AI, rendering or network."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.k70_scene_engine.intelligent_editor import (
    graph_fingerprint, plan_documentary, review_markdown, safe_transition_copy,
)


def scene(sid="s1", narration="The United States explained the dollar system.",
          kind="broll", seconds=4, role="", visual_query="United States Federal Reserve"):
    return {"id": sid, "narration": narration, "duration_sec": seconds,
            "beat_role": role, "visual": {"type": kind, "query": visual_query},
            "transition_in": "cut", "overlays": [], "data": None}


def graph(scenes):
    return {"meta": {"video_id": "p3-test", "title": "The Dollar",
                     "niche": "usa_finance", "channel_id": "usa_trading",
                     "hook": "The Dollar"},
            "scenes": scenes, "audio": {"voiceover_path": None, "music_path": None},
            "captions": [], "sfx": []}


def test_no_mutation_exact_timeline_and_determinism():
    data = graph([scene(f"s{i}", seconds=3 + i) for i in range(1, 17)])
    before = copy.deepcopy(data)
    first = plan_documentary(data)
    assert first == plan_documentary(data)
    assert data == before
    assert first["scene_count"] == 16
    assert first["duration_sec"] == sum(range(4, 20))
    assert first["source_graph_sha256"] == graph_fingerprint(data)
    assert sum(first["existing_visual_seconds"].values()) == first["duration_sec"]
    assert "visuals_are_recommendations_only" in first["guardrails"]
    assert len(first["visual_mix_by_quarter_sec"]) == 4


def test_sourced_data_chart_gets_priority_without_demoting_authored_media():
    first = scene(kind="motion_gfx", narration="The index was 123.",
                  visual_query="numbers")
    first["data"] = {"points": [{"label": "2020", "value": 123}], "source": "Federal Reserve"}
    second = scene("s2", "The Japan announcement happened.", "threejs", 9, "",
                   "Japan animated globe")
    third = scene("s3", "Interest rates changed.", "ai_video", 8, "", "historical recreation")
    data = graph([first, second, third])
    result = plan_documentary(data)
    assert result["decisions"][0]["suggested_visual_intent"] == "dataviz"
    assert result["decisions"][0]["visual_protected"] is True
    assert result["decisions"][1]["visual_protected"] is True
    assert result["decisions"][2]["visual_protected"] is True
    assert all(d["requires_asset_or_editor_approval_for_visual_change"]
               for d in result["decisions"])


def test_detect_money_mismatch_and_generic_footage():
    data = graph([scene(narration="The US dollar was used in shops.",
                        visual_query="Euro banknotes and business meeting")])
    report = plan_documentary(data)
    codes = [i["code"] for i in report["review_issues"]]
    assert "possible_us_currency_visual_mismatch" in codes
    assert "generic_visual_query_review" in codes
    assert "possible_us_currency_visual_mismatch" in report["decisions"][0]["review_flags"]


def test_long_motion_card_run_and_missing_number_source():
    scenes = [scene(f"s{i}", "In 1971, everything changed.", "motion_gfx", 7,
                    visual_query="headline") for i in range(5)]
    report = plan_documentary(graph(scenes))
    codes = [issue["code"] for issue in report["review_issues"]]
    assert "repetitive_card_run" in codes
    assert "numeric_claim_without_chart_source_review" in codes
    assert report["longest_consecutive_card_run"]["count"] == 5
    assert "too_many_fullscreen_cards" not in codes  # only >=20 scenes


def test_four_quarter_cinematic_coverage_no_false_cluster():
    shots = []
    for i in range(16):
        kind = "ai_video" if i in (1, 5, 9, 13) else "broll"
        shots.append(scene(f"s{i+1}", "An exact historic subject", kind, 10))
    report = plan_documentary(graph(shots))
    assert all(val == 10 for val in report["cinematic_seconds_by_quarter"])
    assert "cinematics_clustered" not in report["issue_counts"]
    assert "| ai_video |" in review_markdown(report)


def test_transitions_safe_unrendered_copy_and_protected_media_unchanged():
    a = scene("s1", "What started the story?", "broll", 7, "hook")
    b = scene("s2", "However, the system changed.", "broll", 8, "turning_point")
    c = scene("s3", "The globe shows the Japan location.", "threejs", 7, "resolution")
    data = graph([a, b, c])
    report = plan_documentary(data)
    edited = safe_transition_copy(data, report)
    assert data["scenes"][1]["transition_in"] == "cut"
    assert edited["scenes"][1]["transition_in"] == "crossfade"
    assert edited["scenes"][2]["transition_in"] == "cut"
    assert edited["scenes"][0]["transition_in"] == "cut"
    assert edited["scenes"][1]["narration"] == b["narration"]
    assert edited["scenes"][1]["visual"] == b["visual"]


def test_refuses_stale_report_and_rendered_media_edit():
    data = graph([scene("s1"), scene("s2", role="reveal")])
    report = plan_documentary(data)
    changed = copy.deepcopy(data)
    changed["scenes"][0]["narration"] = "Changed narration"
    with pytest.raises(ValueError, match="exact source"):
        safe_transition_copy(changed, report)
    for field, value in [
        ("captions", [{"start": 0, "end": 1, "text": "hello"}]),
        ("sfx", [{"sound": "pop", "at": 1}]),
    ]:
        modified = copy.deepcopy(data)
        modified[field] = value
        with pytest.raises(ValueError, match="exact source"):
            safe_transition_copy(modified, report)
    asset = copy.deepcopy(data)
    asset["scenes"][0]["visual"]["asset_path"] = "/tmp/existing.mp4"
    asset_report = plan_documentary(asset)
    with pytest.raises(ValueError, match="resolved media"):
        safe_transition_copy(asset, asset_report)
    voiced = copy.deepcopy(data)
    voiced["audio"]["voiceover_path"] = "data/vo.wav"
    voice_report = plan_documentary(voiced)
    with pytest.raises(ValueError, match="audio exists"):
        safe_transition_copy(voiced, voice_report)


@pytest.mark.parametrize("bad", [
    {}, {"scenes": []}, {"scenes": [scene("dup"), scene("dup")]},
    {"scenes": [scene(seconds=0)]},
])
def test_bad_graph_rejected(bad):
    with pytest.raises(ValueError):
        plan_documentary(bad)


def test_cli_read_only_and_opt_in_copy(tmp_path):
    inp = graph([scene("s1", role="hook"),
                 scene("s2", "But the answer changed.", role="reveal")])
    source = tmp_path / "graph.json"
    original = json.dumps(inp, indent=2)
    source.write_text(original)
    cli = ROOT / "scripts" / "k70_p3_editor.py"
    out = tmp_path / "review"
    args = [sys.executable, str(cli), "--graph", str(source), "--out-dir", str(out)]
    run = subprocess.run(args, capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stderr
    assert (out / "editorial_plan.json").is_file()
    assert (out / "editorial_review.md").is_file()
    assert not (out / "scene_graph_editorial_copy.json").exists()
    assert source.read_text() == original
    again = subprocess.run(args, capture_output=True, text=True, timeout=20)
    assert again.returncode != 0
    out_copy = tmp_path / "new-copy"
    run_copy = subprocess.run(args[:-1] + [str(out_copy), "--apply-transitions-to-copy"],
                              capture_output=True, text=True, timeout=20)
    assert run_copy.returncode == 0, run_copy.stderr
    revision = json.loads((out_copy / "scene_graph_editorial_copy.json").read_text())
    assert revision["scenes"][1]["transition_in"] == "crossfade"
    assert source.read_text() == original
