from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.brand import theme_for
from app.config import settings
from app.pipeline import qa
from app.schemas.scene import (AudioTrack, Caption, Scene, SceneGraph, SceneMeta,
                               Visual)


def _run(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *args], check=True)


@pytest.fixture(scope="module")
def qa_media(tmp_path_factory):
    root = tmp_path_factory.mktemp("production_qa_media")
    good = root / "good.mp4"
    broken = root / "broken.mp4"
    thumb = root / "thumbnail.jpg"
    metadata = root / "metadata.json"
    _run("-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
         "-t", "1.2", "-af", "loudnorm=I=-14:TP=-1.5:LRA=7",
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-movflags", "+faststart",
         "-y", str(good))
    _run("-f", "lavfi", "-i", "color=black:size=640x360:rate=24",
         "-t", "1.2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(broken))
    _run("-ss", "0.3", "-i", str(good), "-frames:v", "1", "-y", str(thumb))
    metadata.write_text(json.dumps({"title": "Finance Test", "description": "Test",
        "tags": ["finance"], "thumbnail_text": "THE NUMBER"}))
    return root, good, broken, thumb, metadata


def _graph(media: Path) -> SceneGraph:
    graph = SceneGraph(meta=SceneMeta(video_id="qa_fixture", channel_id="k70_business",
        niche="finance", title="Finance Test", hook="The number moved",
        description="A finance fixture", tags=["finance"], thumbnail_text="THE NUMBER"),
        width=1080, height=1920, fps=30,
        scenes=[Scene(id="s1", narration="Revenue rose ten percent.", duration_sec=1.2,
                      visual=Visual(type="solid"))],
        captions=[Caption(start=0, end=1.1, text="Revenue rose ten percent")],
        audio=AudioTrack(voiceover_path=str(media)))
    settings().brand_identity_enabled = True
    theme_for(graph, "compositor")
    return graph


def test_good_fixture_passes_all_required_checks(qa_media, monkeypatch):
    root, good, _, thumb, metadata = qa_media
    monkeypatch.setattr(settings(), "brand_identity_enabled", True)
    report_path = root / "good.qa.json"
    report = qa.production_analyze(_graph(good), str(good), thumbnail=str(thumb),
                                   metadata_path=str(metadata), report_path=str(report_path))
    failures = [c for c in report.checks if c.status == "FAIL"]
    assert not failures, [(c.category, c.check, c.reason) for c in failures]
    assert report.status in ("PASS", "WARNING")
    assert report_path.is_file() and json.loads(report_path.read_text())["status"] == report.status


def test_broken_fixture_reports_actionable_failures(qa_media, monkeypatch):
    root, _, broken, _, _ = qa_media
    monkeypatch.setattr(settings(), "brand_identity_enabled", True)
    report = qa.production_analyze(_graph(broken), str(broken), report_path=str(root/"broken.qa.json"))
    assert report.status == "FAIL"
    names = {c.check for c in report.checks if c.status == "FAIL"}
    assert {"black frames", "production resolution", "missing narration",
            "1080x1920", "H.264 and AAC-LC/48kHz", "thumbnail"}.issubset(names)
    assert all(c.reason and c.suggested_fix for c in report.checks if c.status == "FAIL")


def test_synthetic_scene_requires_ai_provenance(qa_media, monkeypatch):
    _, good, _, thumb, metadata = qa_media
    monkeypatch.setattr(settings(), "brand_identity_enabled", True)
    graph = _graph(good)
    graph.scenes[0].visual.type = "ai_image"
    graph.scenes[0].visual.asset_path = str(thumb)
    report = qa.production_analyze(graph, str(good), thumbnail=str(thumb),
                                   metadata_path=str(metadata))
    finding = next(c for c in report.checks if c.check == "synthetic content tracking")
    assert finding.status == "FAIL" and finding.scene == "__export__"


def test_phase8_gate_defaults_off_and_legacy_qa_remains_independent():
    assert settings().visual_qa_engine_enabled is False
    assert hasattr(qa, "analyze") and hasattr(qa, "production_analyze")


def test_report_has_all_required_categories(qa_media, monkeypatch):
    _, good, _, thumb, metadata = qa_media
    monkeypatch.setattr(settings(), "brand_identity_enabled", True)
    report = qa.production_analyze(_graph(good), str(good), thumbnail=str(thumb),
                                   metadata_path=str(metadata))
    assert {c.category for c in report.checks} == {
        "visual", "text", "audio", "motion", "finance", "legal", "youtube"}
    assert report.metrics["checks"] == len(report.checks)


def test_every_failure_has_complete_action_context(qa_media, monkeypatch):
    _, _, broken, _, _ = qa_media
    monkeypatch.setattr(settings(), "brand_identity_enabled", True)
    report = qa.production_analyze(_graph(broken), str(broken))
    assert all(item.reason and item.scene and item.timestamp is not None and
               item.suggested_fix for item in report.checks if item.status == "FAIL")
