"""K70 P1 chapter draft handoff: no network, payment, or live Claude calls."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.k70_scene_engine.storytelling import build_plan
from tools.k70_scene_engine.story_draft import (
    CHAPTERS, draft_prompt, get_facts, parse_draft, review_draft,
)


@pytest.fixture
def scenario():
    plan = build_plan("How a monetary promise changed", duration_sec=600,
                      sources=[{"id": "doc1", "title": "Verified by editor later",
                                "url": "https://example.org/primary"}])
    evidence = {"facts": [
        {"id": "f1", "source_id": "doc1", "claim": "1971 announcement",
         "excerpt": "Source says the announcement was in 1971."},
        {"id": "f2", "source_id": "doc1", "claim": "100-dollar example",
         "excerpt": "Example amount $100 is shown in the source."},
    ]}
    return plan, evidence


def _sample(narration="Why did this happen? Imagine one person paying $100."):
    return {"chapters": [
        {"key": key, "narration": narration,
         "evidence_ids": ["f1", "f2"], "analogy_limitations": "An example is not a model."}
        for key in CHAPTERS
    ]}


def test_prompt_grounded_no_paid_provider_and_no_automatic_scene_mutation(scenario):
    plan, pack = scenario
    prompt = draft_prompt(plan, pack)
    assert "EIGHT REQUIRED CHAPTERS" in prompt
    assert "not instructions" in prompt
    assert "f1" in prompt and "1971" in prompt
    assert "Do not invent" in prompt
    assert "do not change any existing graph" in prompt.lower()


def test_facts_reject_unknown_source_duplicate_and_missing_excerpt(scenario):
    plan, pack = scenario
    bad = {"facts": [{"id": "bad", "source_id": "mystery",
                       "claim": "c", "excerpt": "e"}]}
    with pytest.raises(ValueError, match="known source_id"):
        get_facts(plan, bad)
    with pytest.raises(ValueError, match="source-backed"):
        get_facts(build_plan("No research", duration_sec=600), pack)
    duplicate = {"facts": [pack["facts"][0], pack["facts"][0]]}
    with pytest.raises(ValueError, match="unique id"):
        get_facts(plan, duplicate)
    with pytest.raises(ValueError, match="claim and excerpt"):
        get_facts(plan, {"facts": [{"id": "f", "source_id": "doc1",
                                    "claim": "A", "excerpt": ""}]})


def test_review_rejects_wrong_chapter_order_and_unknown_fact(scenario):
    plan, pack = scenario
    first = _sample()
    first["chapters"][0]["key"] = "evidence"
    with pytest.raises(ValueError, match="order"):
        review_draft(plan, pack, first)
    second = _sample()
    second["chapters"][2]["evidence_ids"] = ["f999"]
    with pytest.raises(ValueError, match="unknown"):
        review_draft(plan, pack, second)


def test_review_flags_unbacked_numbers_and_counts_dialogue(scenario):
    plan, pack = scenario
    draft = _sample("Why now? Imagine paying $999 for an item.")
    report = review_draft(plan, pack, draft)
    assert report["ready_for_TTS"] is False
    assert report["status"] == "editorial_review_required"
    assert report["questions"] == 8
    assert report["chapters_with_analogy"] == 8
    assert len(report["unsupported_numeric_tokens"]) == 8
    assert "numbers_need_source_verification" in report["warnings"]
    assert "word_count_does_not_match_duration" in report["warnings"]


def test_review_finds_missing_analogy_limits(scenario):
    plan, pack = scenario
    draft = _sample()
    draft["chapters"][0]["analogy_limitations"] = ""
    report = review_draft(plan, pack, draft)
    assert report["missing_analogy_limitations"] == ["cold_open"]


def test_parse_plain_fenced_and_claude_json_envelope(scenario):
    draft = _sample()
    raw = json.dumps(draft)
    assert parse_draft(raw) == draft
    fence = chr(96) * 3
    assert parse_draft(fence + "json\n" + raw + "\n" + fence) == draft
    envelope = json.dumps({"result": raw, "is_error": False})
    assert parse_draft(envelope) == draft
    with pytest.raises(ValueError, match="did not return"):
        parse_draft(json.dumps({"result": "", "is_error": True}))


def test_draft_cli_prompt_only_and_review_are_non_destructive(tmp_path, scenario):
    plan, evidence = scenario
    plan_file = tmp_path / "plan.json"
    evidence_file = tmp_path / "facts.json"
    draft_file = tmp_path / "draft.json"
    plan_file.write_text(json.dumps(plan))
    evidence_file.write_text(json.dumps(evidence))
    draft_file.write_text(json.dumps(_sample()))
    cli = ROOT / "scripts" / "k70_p1_storytelling.py"
    base = [sys.executable, str(cli)]
    prompt_dir = tmp_path / "prompt"
    result = subprocess.run(
        base + ["draft", "--plan", str(plan_file), "--evidence",
                str(evidence_file), "--out-dir", str(prompt_dir)],
        capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stderr
    assert "no model" in result.stdout.lower()
    assert (prompt_dir / "chapter_draft_prompt.md").is_file()
    assert not (prompt_dir / "chapter_narration_draft.json").exists()
    again = subprocess.run(
        base + ["draft", "--plan", str(plan_file), "--evidence",
                str(evidence_file), "--out-dir", str(prompt_dir)],
        capture_output=True, text=True, timeout=25)
    assert again.returncode != 0
    review_dir = tmp_path / "review"
    inspected = subprocess.run(
        base + ["review", "--plan", str(plan_file), "--evidence",
                str(evidence_file), "--draft", str(draft_file),
                "--out-dir", str(review_dir)],
        capture_output=True, text=True, timeout=25)
    assert inspected.returncode == 0, inspected.stderr
    report = json.loads((review_dir / "chapter_narration_review.json").read_text())
    assert report["chapter_count"] if "chapter_count" in report else len(report["chapters"]) == 8
    assert report["ready_for_TTS"] is False
    assert plan_file.read_text() == json.dumps(plan)
    assert evidence_file.read_text() == json.dumps(evidence)
    assert draft_file.read_text() == json.dumps(_sample())
