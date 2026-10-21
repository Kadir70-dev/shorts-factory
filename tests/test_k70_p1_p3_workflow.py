"""K70 P1 -> P3 handoff: offline, no model calls, no rendering, no source edits."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.k70_scene_engine.intelligent_editor import (
    plan_documentary, safe_transition_copy,
)
from tools.k70_scene_engine.story_draft import CHAPTERS, review_draft
from tools.k70_scene_engine.storytelling import build_plan


def test_reviewed_p1_draft_feeds_p3_without_claiming_verification():
    plan = build_plan("The end of the gold window", duration_sec=600, sources=[
        {"id": "src1", "title": "Treasury bulletin", "url": "https://example.gov/gold"}])
    assert plan["research_status"] == "sources_supplied_not_independently_verified"
    pack = {"facts": [{"id": "f1", "source_id": "src1",
                       "claim": "US gold holdings were 8133 tonnes in 1971.",
                       "excerpt": "Official holdings: 8133 tonnes (1971)."}]}
    chapters = [{"key": key, "evidence_ids": ["f1"], "analogy_limitations": "",
                 "narration": f"Why did the {key.replace('_', ' ')} matter? "
                              "Holdings reached 8133 tonnes. " + "word " * 140}
                for key in CHAPTERS]
    chapters[4]["narration"] += " Then 9999 tonnes appeared."  # unsupported figure
    review = review_draft(plan, pack, {"chapters": chapters})
    assert review["ready_for_TTS"] is False
    assert review["status"] == "editorial_review_required"
    assert review["unsupported_numeric_tokens"] == [
        {"chapter": "evidence", "numbers_to_check": ["9999"]}]

    # Editor-authored NEW unrendered SceneGraph: one scene per approved chapter.
    scenes = []
    for i, ch in enumerate(chapters):
        scenes.append({"id": f"s{i + 1}", "narration": ch["narration"], "duration_sec": 70,
                       "beat_role": ch["key"], "transition_in": "cut", "overlays": [],
                       "visual": {"type": "motion_gfx", "query": "headline"}, "data": None})
    scenes[4]["data"] = {"points": [{"label": "1971", "value": 8133}],
                         "source": "Treasury bulletin (src1, editor-supplied)"}
    scenes[2]["visual"] = {"type": "threejs", "query": "globe"}
    draft = {"meta": {"title": "Gold window"}, "scenes": scenes,
             "audio": {"voiceover_path": None}, "captions": [], "sfx": []}
    before = copy.deepcopy(draft)

    report = plan_documentary(draft)
    edited = safe_transition_copy(draft, report)
    assert draft == before
    assert report["guardrails"]["visuals_are_recommendations_only"] is True
    assert edited["scenes"][4]["visual"]["type"] == "dataviz"
    assert edited["scenes"][2]["visual"] == scenes[2]["visual"]
    assert [s["narration"] for s in edited["scenes"]] == [s["narration"] for s in scenes]
    assert [s["duration_sec"] for s in edited["scenes"]] == [70] * 8
    assert edited["scenes"][0]["transition_in"] == "cut"
