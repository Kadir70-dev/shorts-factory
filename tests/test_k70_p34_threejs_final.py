"""K70 P3.4: the final graph may change ONLY the Three.js asset paths."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("p34", ROOT / "scripts" / "k70_p34_threejs_final.py")
p34 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p34)


def _graph():
    scenes = [{"id": "s1", "duration_sec": 4.0, "narration": "a", "transition_in": "crossfade",
               "visual": {"type": "threejs", "asset_path": "/old/s1.mp4", "decision_reason": "x"}},
              {"id": "s2", "duration_sec": 3.0, "narration": "b", "transition_in": "cut",
               "visual": {"type": "broll", "asset_path": "/keep/s2.mp4"}}]
    return {"meta": {}, "scenes": scenes, "captions": [{"start": 0}], "audio": {"vo": "v"}}


def _manifest(tmp_path: Path, passed: bool = True):
    clip = tmp_path / "s1_final.mp4"
    clip.write_bytes(b"final-clip")
    return {"clips": [{"scene_id": "s1", "clip": str(clip), "passed": passed,
                       "sha256": hashlib.sha256(b"final-clip").hexdigest()}]}, clip


def test_build_repoints_only_threejs(tmp_path):
    src = _graph()
    before = copy.deepcopy(src)
    manifest, clip = _manifest(tmp_path)
    out = p34.build_graph(src, manifest)
    assert src == before
    assert out["scenes"][0]["visual"]["asset_path"] == str(clip)
    assert out["scenes"][1] == src["scenes"][1]
    assert out["captions"] == src["captions"] and out["audio"] == src["audio"]


def test_build_refuses_unvalidated_or_changed_clips(tmp_path):
    manifest, clip = _manifest(tmp_path, passed=False)
    with pytest.raises(ValueError, match="missing"):
        p34.build_graph(_graph(), manifest)
    manifest, clip = _manifest(tmp_path)
    clip.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="changed"):
        p34.build_graph(_graph(), manifest)
