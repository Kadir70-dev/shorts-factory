"""Tests for the plan-vs-delivery QA gate (OpenMontage-audit gap #3).

`visual_budget.measure()` already computes, per scene, the PLANNED channel
(`Assignment.scores["planned"]`) against the DELIVERED channel
(`Assignment.channel`) — that data already exists and is already persisted
to `visual_breakdown.json`. What was missing was turning a mismatch into a
graded pass/fail: `qa.plan_vs_delivery` classifies each mismatch against
`qa.ALLOWED_FALLBACKS`, and `qa.analyze`'s new check fails the report once
the SILENT-downgrade rate (mismatches NOT in the allowed matrix) crosses
`settings().qa_max_silent_downgrade_rate`.

These tests build synthetic `BudgetReport`/`Assignment` objects directly —
no real render needed — covering the three worked examples from the audit
(planned threejs → delivered motion_gfx, planned official/papercraft →
delivered a generic card, planned official archival → delivered typography)
plus the allowed-lateral-fallback and threshold-crossing cases.
"""
from __future__ import annotations

import pytest

from app.pipeline import qa
from app.pipeline.visual_budget import Assignment, BudgetReport


def _report(rows: list[tuple[str, str, str]]) -> BudgetReport:
    """rows: [(scene_id, planned_channel, delivered_channel), ...]"""
    assignments = [
        Assignment(scene_id=sid, channel=delivered, seconds=3.0, score=0.0,
                  reason=f"test: {planned}->{delivered}", scores={"planned": planned})
        for sid, planned, delivered in rows
    ]
    return BudgetReport(assignments=assignments, seconds={}, pct={}, bands={},
                        total_seconds=3.0 * len(rows))


def test_matched_plan_and_delivery_is_not_silent():
    rep = _report([("s1", "threejs", "threejs")])
    result = qa.plan_vs_delivery(rep)
    assert len(result) == 1
    assert result[0].matched is True
    assert result[0].silent is False


def test_lateral_lower_craft_fallback_is_allowed_not_silent():
    # Both "real content" channels — a documented, acceptable substitution.
    rep = _report([("s1", "threejs", "charts")])
    result = qa.plan_vs_delivery(rep)
    assert result[0].matched is False
    assert result[0].silent is False


def test_threejs_to_motion_gfx_is_the_audits_own_worked_example_and_is_silent():
    rep = _report([("s11", "threejs", "motion_gfx")])
    result = qa.plan_vs_delivery(rep)
    assert result[0].silent is True


def test_official_archival_falling_to_motion_gfx_typography_is_silent():
    # "planned archival footage -> delivered typography"
    rep = _report([("s5", "official", "motion_gfx")])
    result = qa.plan_vs_delivery(rep)
    assert result[0].silent is True


def test_official_papercraft_falling_to_generic_card_is_silent():
    # Paper Craft renders count as channel "official" (visual_budget.measure);
    # a branded/generic-card fallback also counts as channel "motion_gfx".
    rep = _report([("s7", "official", "motion_gfx")])
    result = qa.plan_vs_delivery(rep)
    assert result[0].silent is True


def test_falling_to_unresolved_is_always_silent():
    rep = _report([("s9", "stock", "unresolved")])
    result = qa.plan_vs_delivery(rep)
    assert result[0].silent is True


def test_unplanned_scene_is_skipped_not_counted():
    rep = _report([("s1", "-", "stock")])
    assert qa.plan_vs_delivery(rep) == []


def test_allowed_fallbacks_matrix_is_symmetric_for_real_content_channels():
    real_channels = {"stock", "official", "ai_broll", "charts", "threejs"}
    for ch in real_channels:
        assert ch in qa.ALLOWED_FALLBACKS
        assert qa.ALLOWED_FALLBACKS[ch] == real_channels - {ch}
    assert "motion_gfx" not in qa.ALLOWED_FALLBACKS  # nothing may silently absorb into it


@pytest.mark.parametrize("mp4_exists", [True])
def test_analyze_passes_below_the_downgrade_threshold(monkeypatch, tmp_path, mp4_exists):
    from app.schemas.scene import SceneGraph

    graph = SceneGraph(
        schema_version="2.0",
        meta={"video_id": "pvd_pass", "channel_id": "k70_history", "niche": "usa_history",
              "title": "t", "hook": "h"},
        scenes=[{"id": f"s{i}", "narration": "x", "duration_sec": 2.0,
                "visual": {"type": "broll", "query": "x"}} for i in range(10)],
    )
    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"0" * 60_000)

    # 1 silent downgrade out of 10 planned beats = 10% = right at the default
    # threshold (0.10) -> must PASS (<=), not fail.
    rows = [(f"s{i}", "stock", "stock") for i in range(9)]
    rows.append(("s9", "threejs", "motion_gfx"))
    rep = _report(rows)

    monkeypatch.setattr(qa, "_stream_types", lambda mp4: ["video", "audio"])
    monkeypatch.setattr(qa, "_probe", lambda *a, **kw: "1080" if "width" in str(a) else "1920")
    monkeypatch.setattr(qa, "_black_seconds", lambda mp4: 0.0)
    monkeypatch.setattr(qa, "_yavg", lambda mp4, t: 100.0)
    monkeypatch.setattr(qa, "_to_float", lambda x: 20.0)

    result = qa.analyze(graph, str(mp4), render_seconds=5.0, ram_peak_mb=100,
                        min_free_mb=1000, budget_report=rep)
    pvd_check = next(c for c in result.checks if c.name.startswith("plan-vs-delivery"))
    assert pvd_check.passed is True
    assert result.metrics["silent_downgrade_count"] == 1
    assert result.metrics["silent_downgrade_rate"] == pytest.approx(0.1)


def test_analyze_fails_above_the_downgrade_threshold(monkeypatch, tmp_path):
    from app.schemas.scene import SceneGraph

    graph = SceneGraph(
        schema_version="2.0",
        meta={"video_id": "pvd_fail", "channel_id": "k70_history", "niche": "usa_history",
              "title": "t", "hook": "h"},
        scenes=[{"id": f"s{i}", "narration": "x", "duration_sec": 2.0,
                "visual": {"type": "broll", "query": "x"}} for i in range(4)],
    )
    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"0" * 60_000)

    # 2 of 4 planned beats silently downgraded = 50%, well above the default
    # 10% ceiling -> must FAIL the overall report (severity="error" by default).
    rows = [("s0", "stock", "stock"), ("s1", "stock", "stock"),
           ("s2", "threejs", "motion_gfx"), ("s3", "official", "unresolved")]
    rep = _report(rows)

    monkeypatch.setattr(qa, "_stream_types", lambda mp4: ["video", "audio"])
    monkeypatch.setattr(qa, "_probe", lambda *a, **kw: "1080" if "width" in str(a) else "1920")
    monkeypatch.setattr(qa, "_black_seconds", lambda mp4: 0.0)
    monkeypatch.setattr(qa, "_yavg", lambda mp4, t: 100.0)
    monkeypatch.setattr(qa, "_to_float", lambda x: 8.0)

    result = qa.analyze(graph, str(mp4), render_seconds=5.0, ram_peak_mb=100,
                        min_free_mb=1000, budget_report=rep)
    pvd_check = next(c for c in result.checks if c.name.startswith("plan-vs-delivery"))
    assert pvd_check.passed is False
    assert result.passed is False
    assert result.metrics["silent_downgrade_count"] == 2


def test_analyze_without_budget_report_skips_the_check_entirely(monkeypatch, tmp_path):
    """Backward compatible: callers that don't pass budget_report (or an older
    caller that hasn't been updated) get the exact same report shape as
    before this check existed — no crash, no spurious failure."""
    from app.schemas.scene import SceneGraph

    graph = SceneGraph(
        schema_version="2.0",
        meta={"video_id": "pvd_none", "channel_id": "k70_history", "niche": "usa_history",
              "title": "t", "hook": "h"},
        scenes=[{"id": "s0", "narration": "x", "duration_sec": 2.0,
                "visual": {"type": "broll", "query": "x"}}],
    )
    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"0" * 60_000)

    monkeypatch.setattr(qa, "_stream_types", lambda mp4: ["video", "audio"])
    monkeypatch.setattr(qa, "_probe", lambda *a, **kw: "1080" if "width" in str(a) else "1920")
    monkeypatch.setattr(qa, "_black_seconds", lambda mp4: 0.0)
    monkeypatch.setattr(qa, "_yavg", lambda mp4, t: 100.0)
    monkeypatch.setattr(qa, "_to_float", lambda x: 2.0)

    result = qa.analyze(graph, str(mp4), render_seconds=5.0, ram_peak_mb=100, min_free_mb=1000)
    assert not any(c.name.startswith("plan-vs-delivery") for c in result.checks)
    assert result.metrics["silent_downgrade_count"] is None
