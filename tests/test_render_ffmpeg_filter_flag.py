"""FFmpeg 6.x has no `-/filter_complex`; the final mux must pick a supported flag."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'apps'/'api'))
from app.pipeline import render_ffmpeg as rf


@pytest.mark.parametrize('banner,flag', [
    ('ffmpeg version 6.1.1-3ubuntu5 Copyright', '-filter_complex_script'),
    ('ffmpeg version n6.0 Copyright', '-filter_complex_script'),
    ('ffmpeg version 7.1 Copyright', '-/filter_complex'),
    ('ffmpeg version N-112233-gdeadbeef Copyright', '-/filter_complex'),   # git build
    ('garbage', '-/filter_complex'),
])
def test_flag_by_version(monkeypatch, banner, flag):
    rf._filter_script_flag.cache_clear()
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: NS(stdout=banner))
    assert rf._filter_script_flag() == flag
    rf._filter_script_flag.cache_clear()


def test_installed_ffmpeg_accepts_chosen_flag(tmp_path):
    rf._filter_script_flag.cache_clear()
    script = tmp_path/'f.txt'
    script.write_text('[0:v]null[v]')
    r = subprocess.run(['ffmpeg', '-hide_banner', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=black:s=32x32:d=0.1', rf._filter_script_flag(), str(script),
                        '-map', '[v]', '-f', 'null', '-'], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
