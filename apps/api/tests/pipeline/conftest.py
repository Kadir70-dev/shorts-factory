"""Shared fixtures for the storytelling / brand / compliance pipeline tests.

The rotation ledger is file-backed and cross-video by design, so every test that
touches structure, variety or music selection gets an isolated data dir. Without
this the tests would influence each other exactly the way consecutive uploads are
meant to.
"""
from __future__ import annotations

import pytest

from app.schemas.scene import (DataPoint, DataViz, Overlay, Scene, SceneGraph,
                               SceneMeta)


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Point the rotation ledger at a fresh directory for one test.

    The ledger is read from disk on every call (never cached), so redirecting
    `data_dir` is sufficient — and necessary, since a shared ledger would let
    tests influence each other exactly the way consecutive uploads are meant to.
    """
    from app.config import settings

    monkeypatch.setattr(settings(), "data_dir", tmp_path, raising=False)
    return tmp_path


def make_scene(sid: str, narration: str, *, role: str = "", **kw) -> Scene:
    return Scene(id=sid, narration=narration, beat_role=role, **kw)


@pytest.fixture
def graph() -> SceneGraph:
    """A small, realistic finance short."""
    return SceneGraph(
        meta=SceneMeta(video_id="vid_test", channel_id="k70_business",
                       niche="usa_business", title="Test short",
                       hook="A number that did not move"),
        scenes=[
            make_scene("s1", "Costco has sold the same hot dog since 1985.",
                       role="hook",
                       overlays=[Overlay(type="headline", text="The price never moved")]),
            make_scene("s2", "Inflation since then ran roughly 290 percent.",
                       role="evidence",
                       data=DataViz(kind="delta", title="Real price",
                                    points=[DataPoint(label="1985", value=1.5),
                                            DataPoint(label="2024", value=0.38)],
                                    prefix="$", decimals=2, abbreviate=False,
                                    source="BLS")),
            make_scene("s3", "The hot dog was never really the product.",
                       role="mechanism"),
            make_scene("s4", "Follow for more of the systems behind the numbers.",
                       role="cta"),
        ],
    )
