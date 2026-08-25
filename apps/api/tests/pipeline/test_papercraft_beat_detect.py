"""Paper Craft beat detection — the paper-motion premium replacement for
otherwise-static kinetic-type screens (dates, quotes, callout figures, sourced
claims). `is_eligible()` decides which beats get a laid-out document instead
of plain text; `visual_budget.measure()` must keep reporting those beats
against whichever channel they were actually allocated to (now including
"motion_gfx", not just "official"/"charts")."""
from __future__ import annotations

from app.pipeline.papercraft import beat_detect
from app.pipeline.visual_budget import CHANNELS, measure
from app.schemas.scene import Overlay, Scene, SceneGraph


def test_a_bare_claim_with_no_document_shape_is_not_eligible():
    s = Scene(id="s1", narration="Money is just trust, moving.")
    assert beat_detect.is_eligible(s) is False


def test_a_quote_overlay_makes_a_beat_eligible():
    s = Scene(id="s1", narration="He said it plainly.",
              overlays=[Overlay(type="quote", text="We had no choice.",
                                sub="the Treasury Secretary")])
    assert beat_detect.is_eligible(s) is True


def test_a_stat_overlay_makes_a_beat_eligible():
    s = Scene(id="s1", narration="The number said it all.",
              overlays=[Overlay(type="stat", text="$100,000,000,000,000",
                                sub="Zimbabwe's peak note")])
    assert beat_detect.is_eligible(s) is True


def test_a_bare_year_in_the_narration_makes_a_beat_eligible():
    s = Scene(id="s1", narration="In 1971, the gold window closed for good.")
    assert beat_detect.is_eligible(s) is True


def test_a_source_overlay_makes_a_beat_eligible():
    s = Scene(id="s1", narration="The filing confirmed it.",
              overlays=[Overlay(type="source", text="SEC 10-K, 2019")])
    assert beat_detect.is_eligible(s) is True


def test_measure_reports_a_papercraft_beat_against_its_own_budget_channel():
    """A beat planned for `motion_gfx` (kinetic type) that Paper Craft upgraded
    to a laid-out document must still be reported as `motion_gfx` delivered —
    not relabelled `official` — so the plan-vs-delivery QA gate sees a MATCH
    (an upgrade within the channel) rather than a false silent downgrade."""
    graph = SceneGraph(
        schema_version="2.0",
        meta={"video_id": "papercraft_test", "channel_id": "k70_history",
              "niche": "usa_history", "title": "t", "hook": "h"},
        scenes=[{
            "id": "s1", "narration": "In 1971, the gold window closed.",
            "duration_sec": 3.0,
            "visual": {"type": "papercraft", "budget_channel": "motion_gfx",
                      "asset_path": "/tmp/s1_papercraft.png"},
        }],
    )
    report = measure(graph)
    assert report.assignments[0].channel == "motion_gfx"
    assert "motion_gfx" in CHANNELS


def test_measure_falls_back_to_official_for_an_unrecognised_budget_channel():
    """Backward compatible: a papercraft beat with no (or a stale/unknown)
    budget_channel still reports as `official`, the pre-existing behaviour."""
    graph = SceneGraph(
        schema_version="2.0",
        meta={"video_id": "papercraft_test2", "channel_id": "k70_history",
              "niche": "usa_history", "title": "t", "hook": "h"},
        scenes=[{
            "id": "s1", "narration": "A dossier beat.", "duration_sec": 3.0,
            "visual": {"type": "papercraft", "asset_path": "/tmp/s1.png"},
        }],
    )
    report = measure(graph)
    assert report.assignments[0].channel == "official"
