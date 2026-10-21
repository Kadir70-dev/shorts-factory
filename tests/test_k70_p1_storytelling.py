"""K70 P1 — deterministic long-form storytelling QA, no TTS/video/network needed."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.k70_scene_engine.storytelling import (
    audit_graph, build_plan, write_audit_brief, write_director_brief,
)


def _scene(id: str, narration: str, seconds: float = 55,
           source: str = "", data_source: str = "") -> dict:
    return {
        "id": id, "narration": narration, "duration_sec": seconds,
        "visual": {"type": "motion_gfx"},
        "overlays": [{"type": "source", "text": source}] if source else [],
        "data": {"source": data_source} if data_source else None,
    }


def test_planner_chapters_cover_duration_without_overlaps():
    a = build_plan("The Dollar and Gold", duration_sec=660)
    b = build_plan("The Dollar and Gold", duration_sec=660)
    assert a == b
    chapters = a["chapters"]
    assert len(chapters) == 8
    assert chapters[0]["start_sec"] == 0.0
    assert chapters[-1]["end_sec"] == 660
    assert all(left["end_sec"] == right["start_sec"]
               for left, right in zip(chapters, chapters[1:]))
    assert sum(b["analogy_slot"] for b in chapters) == 2
    assert a["research_status"] == "RESEARCH_REQUIRED"
    prompt = write_director_brief(a)
    assert "STOP for research" in prompt
    assert "frozen K70" in prompt


def test_sources_are_supplied_not_certified():
    p = build_plan("How banks work", duration_sec=600, sources=[
        {"id": "fed1", "title": "Federal Reserve Explainer",
         "url": "https://federalreserve.gov/example", "claim": "Review cash requirements"}])
    assert p["source_manifest"][0]["verification"] == "user_supplied_unverified"
    assert "proposed claim: Review cash requirements" in write_director_brief(p)
    assert p["research_status"] == "sources_supplied_not_independently_verified"
    with pytest.raises(ValueError, match="unique"):
        build_plan("Banks", sources=[
            {"id": "a", "title": "One"}, {"id": "a", "title": "Two"}])
    with pytest.raises(ValueError, match="HTTP"):
        build_plan("Banks", sources=[
            {"id": "a", "title": "One", "url": "file:///etc/passwd"}])


@pytest.mark.parametrize("minutes", [0, 3.5, 20.1, float("nan")])
def test_out_of_range_duration_rejected(minutes):
    with pytest.raises(ValueError):
        build_plan("Valid topic", duration_sec=minutes * 60)
    with pytest.raises(ValueError):
        build_plan(" ", duration_sec=600)


def test_editorial_audit_flags_low_retention_without_changing_graph():
    graph = {"scenes": [
        _scene("s1", "In 1971 the gold promise changed."),
        _scene("s2", "What changed in the financial system?"),
        _scene("s3", "The decision affected ordinary households."),
        _scene("s4", "A later analysis estimated $8 billion."),
    ]}
    snapshot = copy.deepcopy(graph)
    a = audit_graph(graph)
    assert graph == snapshot
    assert a["questions"] == 1
    assert a["analogy_signals"] == 0
    assert "few_questions_for_longform" in a["warnings"]
    assert "no_obvious_roadmap_in_first_90s" in a["warnings"]
    assert "s4" in a["numeric_claim_scene_ids_to_review"]
    assert a["type"] == "text_only_heuristic_not_video_review"
    assert "not a corrected script" in write_audit_brief(a).lower()


def test_evidence_credits_and_roadmap_detected_but_not_verified():
    graph = {"scenes": [
        _scene("a", "Why did this system change? We'll look at the mechanism.", 30),
        _scene("b", "Imagine buying bread at a shop. For example, each loaf has a price.", 45),
        _scene("c", "According to the report, prices rose by 10 percent.", 45,
               source="Published original dataset"),
        _scene("d", "What about households?", 45, data_source="Dataset X"),
    ]}
    a = audit_graph(graph)
    assert a["roadmap_scene_ids"] == ["a"]
    assert a["questions"] == 2
    assert a["analogy_signals"] >= 2
    assert a["visible_source_overlay_scenes"] == 1
    assert a["chart_source_scenes"] == 1
    assert "s4" not in a["numeric_claim_scene_ids_to_review"]


def test_cli_outputs_are_real_and_never_overwritten(tmp_path: Path):
    cli = ROOT / "scripts" / "k70_p1_storytelling.py"
    folder = tmp_path / "plan"
    args = [sys.executable, str(cli), "plan", "--topic", "Economic history",
            "--minutes", "10", "--out-dir", str(folder)]
    created = subprocess.run(args, capture_output=True, text=True, timeout=20)
    assert created.returncode == 0, created.stderr
    plan = json.loads((folder / "story_plan.json").read_text())
    assert plan["duration_sec"] == 600
    assert "RESEARCH REQUIRED" in (folder / "director_story_brief.md").read_text()
    retried = subprocess.run(args, capture_output=True, text=True, timeout=20)
    assert retried.returncode != 0
    assert "output exists" in retried.stderr

    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps({"scenes": [_scene("s1", "Why now?", 120)]}))
    audit_dir = tmp_path / "qa"
    aud = subprocess.run(
        [sys.executable, str(cli), "audit", "--graph", str(graph_file),
         "--out-dir", str(audit_dir)], capture_output=True, text=True, timeout=20)
    assert aud.returncode == 0, aud.stderr
    assert json.loads((audit_dir / "narrative_qa.json").read_text())["questions"] == 1
    assert graph_file.read_text() == json.dumps({"scenes": [_scene("s1", "Why now?", 120)]})


def test_director_brief_states_research_status_and_never_claims_verification():
    bare = write_director_brief(build_plan("Gold standard", duration_sec=600))
    assert "**Research status:** RESEARCH REQUIRED" in bare
    sourced = write_director_brief(build_plan("Gold standard", duration_sec=600, sources=[
        {"id": "src1", "title": "Treasury bulletin", "url": "https://example.gov/x"}]))
    assert "NOT independently verified" in sourced
    assert "RESEARCH REQUIRED" not in sourced
