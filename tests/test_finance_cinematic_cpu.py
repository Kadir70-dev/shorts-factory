"""F1 tests: real pixel movement, safety, protected finance data, video cache."""
from __future__ import annotations
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/"scripts"))
from tools.finance_cinematic_cpu import EngineError, FinanceShot, render_clip
from tools.finance_cinematic_cpu.bridge import attach_finance_clips
from finance_cinematic_demo import create_example


def test_motion_changes_real_frames(tmp_path):
    spec = create_example(tmp_path)
    shot = FinanceShot(json.loads(spec.read_text()), tmp_path)
    assert shot.frame(0).size == (640, 360)
    assert shot.frame(0).tobytes() != shot.frame(shot.duration*.7).tobytes()
    assert len(shot.layers) == 1


def test_transparent_cutout_required(tmp_path):
    spec = create_example(tmp_path)
    opaque = Image.open(tmp_path/"foreground.png").convert("RGB")
    opaque.save(tmp_path/"opaque.png")
    data = json.loads(spec.read_text())
    data["layers"][0]["path"] = "opaque.png"
    with pytest.raises(EngineError, match="transparency"):
        FinanceShot(data, tmp_path)


def test_asset_sandbox_and_no_url_download(tmp_path):
    spec = create_example(tmp_path)
    data = json.loads(spec.read_text())
    data["background"] = "../../etc/passwd"
    with pytest.raises(EngineError, match="escapes"):
        FinanceShot(data, tmp_path)
    data["background"] = "https://host.invalid/image.png"
    with pytest.raises(EngineError, match="relative local"):
        FinanceShot(data, tmp_path)


def test_laptop_bounds_and_camera_mode(tmp_path):
    spec = create_example(tmp_path)
    data = json.loads(spec.read_text())
    data["width"] = 5000
    with pytest.raises(EngineError, match="width"):
        FinanceShot(data, tmp_path)
    data["width"] = 640
    data["duration_sec"] = 3600
    with pytest.raises(EngineError, match="duration"):
        FinanceShot(data, tmp_path)
    data["duration_sec"] = 5
    data["camera"] = "invented_movement"
    with pytest.raises(EngineError, match="camera"):
        FinanceShot(data, tmp_path)


def _graph(duration=1, kind="broll", channel="stock", data=None):
    class Graph(SimpleNamespace):
        def model_copy(self, *, deep):
            return copy.deepcopy(self)
    return Graph(width=320, height=180, fps=12,
                 scenes=[SimpleNamespace(id="s1", duration_sec=duration, data=data,
                     visual=SimpleNamespace(type=kind, budget_channel=channel,
                         asset_path="existing.mp4", motion="pan_lr", layers=["preserve"]))])


def test_protected_evidence_scene(tmp_path):
    spec = create_example(tmp_path, width=320, height=180, duration=1)
    graph = _graph(kind="dataviz", channel="charts")
    with pytest.raises(EngineError, match="protected"):
        attach_finance_clips(graph, {"s1": spec}, tmp_path/"out")
    assert graph.scenes[0].visual.asset_path == "existing.mp4"


def test_verified_financial_data_not_overwritten(tmp_path):
    spec = create_example(tmp_path, width=320, height=180, duration=1)
    graph = _graph(data=SimpleNamespace(valid=lambda: True))
    with pytest.raises(EngineError, match="data chart"):
        attach_finance_clips(graph, {"s1": spec}, tmp_path/"out")


def test_voice_visual_timing_guard(tmp_path):
    spec = create_example(tmp_path, width=320, height=180, duration=2)
    graph = _graph(duration=1)
    with pytest.raises(EngineError, match="duration mismatch"):
        attach_finance_clips(graph, {"s1": spec}, tmp_path/"out")
    assert graph.scenes[0].visual.asset_path == "existing.mp4"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="ffmpeg/ffprobe required")
def test_silent_mp4_cache_and_scene_bridge(tmp_path):
    spec = create_example(tmp_path, width=320, height=180, duration=1)
    dest = tmp_path/"one.mp4"
    first = render_clip(spec, dest, cache_dir=tmp_path/"cache")
    second = render_clip(spec, tmp_path/"two.mp4", cache_dir=tmp_path/"cache")
    assert first["status"] == "rendered"
    assert second["status"] == "cache_hit"
    result = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format",
         "-of", "json", str(dest)], text=True))
    videos = [stream for stream in result["streams"] if stream["codec_type"] == "video"]
    assert len(videos) == 1 and videos[0]["codec_name"] == "h264"
    assert 0.9 <= float(result["format"]["duration"]) <= 1.1
    assert not any(stream["codec_type"] == "audio" for stream in result["streams"])
    graph = _graph()
    updated = attach_finance_clips(graph, {"s1": spec}, tmp_path/"out",
                                   cache_dir=tmp_path/"cache")
    assert updated is not graph
    assert graph.scenes[0].visual.asset_path == "existing.mp4"
    assert updated.scenes[0].visual.type == "ai_video"
    assert updated.scenes[0].visual.layers == []
    assert Path(updated.scenes[0].visual.asset_path).is_file()


def test_unchanged_graph_without_explicit_mapping(tmp_path):
    graph = _graph()
    assert attach_finance_clips(graph, {}, tmp_path/"out") is graph
    with pytest.raises(EngineError, match="Unknown"):
        attach_finance_clips(graph, {"bad": tmp_path/"missing.json"}, tmp_path/"out")


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="ffmpeg/ffprobe required")
def test_cpu_360p_can_fit_longform_1080p(tmp_path):
    spec = create_example(tmp_path, width=640, height=360, duration=1)
    graph = _graph(duration=1)
    graph.width, graph.height = 1920, 1080
    output = attach_finance_clips(graph, {"s1": spec}, tmp_path/"out")
    assert Path(output.scenes[0].visual.asset_path).is_file()


def test_wrong_aspect_ratio_rejected(tmp_path):
    spec = create_example(tmp_path, width=320, height=180, duration=1)
    graph = _graph(duration=1)
    graph.width, graph.height = 1080, 1920
    with pytest.raises(EngineError, match="aspect mismatch"):
        attach_finance_clips(graph, {"s1": spec}, tmp_path/"out")
