"""Run: PYTHONPATH=apps/api pytest -q tests/test_cartoon_motion_cpu.py"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api'))
sys.path.insert(0, str(ROOT / 'scripts'))
from app.pipeline.cartoon_motion_cpu import CartoonMotion, render_manifest
from app.pipeline.cartoon_motion_adapter import apply_cartoon_to_graph
from cartoon_cpu_demo import create_example


def test_character_moves_and_canvas(tmp_path):
    src = create_example(tmp_path)
    engine = CartoonMotion(json.loads(src.read_text()), tmp_path)
    a = engine.frame(0).tobytes()
    b = engine.frame(0.55).tobytes()
    assert (engine.width, engine.height) == (360, 640)
    assert a != b, 'Animation must change pixels, not just loop a still'


def test_missing_sprite_rejected(tmp_path):
    src = create_example(tmp_path)
    payload = json.loads(src.read_text())
    payload['rig']['head']['file'] = 'does_not_exist.png'
    with pytest.raises(FileNotFoundError):
        CartoonMotion(payload, tmp_path)


@pytest.mark.skipif(shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None,
                    reason='Needs ffmpeg and ffprobe')
def test_mp4_and_scenegraph_adapter(tmp_path):
    src = create_example(tmp_path)
    movie = render_manifest(src, tmp_path / 'test.mp4', duration_override=1.25)
    check = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                                     'format=duration', '-of', 'default=nokey=1:noprint_wrappers=1',
                                     str(movie)], text=True).strip()
    assert 1.0 < float(check) < 1.5
    class Graph(SimpleNamespace):
        def model_copy(self, *, deep):
            return copy.deepcopy(self)
    old = Graph(width=360, height=640, fps=12,
                scenes=[SimpleNamespace(id='scene1', duration_sec=1.25,
                           visual=SimpleNamespace(type='image', asset_path=None,
                                                   motion='ken_burns', layers=['old']))])
    patched = apply_cartoon_to_graph(old, {'scene1': src}, tmp_path / 'scenes')
    assert patched is not old
    assert old.scenes[0].visual.asset_path is None
    assert patched.scenes[0].visual.type == 'broll'
    assert patched.scenes[0].visual.layers == []
    assert Path(patched.scenes[0].visual.asset_path).is_file()


def test_unknown_scene_rejected_without_mutation(tmp_path):
    src = create_example(tmp_path)
    graph = SimpleNamespace(scenes=[SimpleNamespace(id='ok')])
    with pytest.raises(ValueError, match='Unknown scene'):
        apply_cartoon_to_graph(graph, {'bad': src}, tmp_path)
