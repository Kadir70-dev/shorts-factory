"""P1 CPU sprite sheet/parts tests (no network, no neural AI models)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api'))
sys.path.insert(0, str(ROOT / 'scripts'))
from app.pipeline.cartoon_asset_prep import AssetPrepError, cutout_image, prepare_assets
from app.pipeline.cartoon_motion_cpu import CartoonMotion, render_manifest
from cartoon_cpu_demo import create_example

SHEET_ORDER = ["head", "body", "arm_left", "arm_right", "leg_left", "leg_right",
               "eyes_open", "eyes_closed", "mouth_open", "mouth_closed"]


def _make_sheet(path: Path, parts: dict[str, Path]):
    sheet = Image.new('RGB', (800, 600), '#ffffff')
    for i, name in enumerate(SHEET_ORDER):
        im = Image.open(parts[name]).convert('RGBA')
        r, c = divmod(i, 4)
        sheet.paste(im, (c * 200 + 30, r * 200 + 15), im)
    sheet.save(path)


def test_corner_key_preserves_enclosed_white_region():
    image = Image.new('RGB', (90, 90), 'white')
    d = ImageDraw.Draw(image)
    d.ellipse((15, 15, 75, 75), fill='black')
    d.ellipse((20, 20, 70, 70), fill='white')
    cut = cutout_image(image)
    assert cut.method == 'border_color_key'
    assert cut.image.getpixel((30, 30))[3] == 255
    assert cut.image.getpixel((0, 0))[3] == 0


def test_part_sheet_round_trip(tmp_path):
    demo = create_example(tmp_path / 'procedural')
    base = tmp_path / 'procedural' / 'assets'
    sheet = tmp_path / 'sheet.png'
    _make_sheet(sheet, {k: base / (
        {'arm_left': 'arm', 'arm_right': 'arm', 'leg_left': 'leg', 'leg_right': 'leg'}.get(k, k) + '.png')
        for k in SHEET_ORDER})
    cfg = tmp_path / 'sheet_spec.json'
    cfg.write_text(json.dumps({'source': 'sheet', 'sheet': sheet.name,
                               'grid': [3, 4], 'width': 360, 'height': 640,
                               'cell_inset_px': 5}), encoding='utf-8')
    manifest, preview = prepare_assets(cfg, tmp_path / 'export')
    rig = json.loads(manifest.read_text())
    assert set(SHEET_ORDER).issubset(set(rig['rig']))
    assert preview.is_file()
    assert len(list((tmp_path / 'export' / 'assets').glob('*.png'))) == 10
    for name in SHEET_ORDER:
        assert Image.open(tmp_path / 'export' / 'assets' / f'{name}.png').mode == 'RGBA'
    engine = CartoonMotion(rig, manifest.parent)
    assert engine.frame(0).tobytes() != engine.frame(0.3).tobytes()
    assert json.loads((tmp_path / 'export' / 'asset_qa.json').read_text())['status'] == 'draft_requires_visual_approval'


def test_individual_parts_with_transparency(tmp_path):
    create_example(tmp_path / 'sample')
    p = tmp_path / 'sample' / 'assets'
    source_map = {k: {'arm_left':'arm','arm_right':'arm','leg_left':'leg','leg_right':'leg'}.get(k,k) + '.png'
                  for k in SHEET_ORDER}
    cfg = tmp_path / 'sample' / 'spec.json'
    cfg.write_text(json.dumps({'source': 'parts', 'input_dir': 'assets',
                               'parts': source_map, 'motions': ['idle', 'wave']}))
    manifest, preview = prepare_assets(cfg, tmp_path / 'out')
    assert manifest.is_file() and preview.is_file()
    report = json.loads((tmp_path / 'out' / 'asset_qa.json').read_text())
    assert all(x['method'] == 'source_alpha' for x in report['parts'].values())


def test_single_flat_character_and_nonuniform_backdrop_rejected(tmp_path):
    (tmp_path / 'spec.json').write_text('{"source":"flattened_full_character"}')
    with pytest.raises(AssetPrepError, match='flattened'):
        prepare_assets(tmp_path / 'spec.json', tmp_path / 'out')
    im = Image.new('RGB', (50, 50), 'white')
    im.putpixel((0, 0), (0, 0, 0))
    with pytest.raises(AssetPrepError, match='Corners differ'):
        cutout_image(im)


def test_path_traversal_rejected(tmp_path):
    (tmp_path / 'spec.json').write_text(json.dumps({'source':'parts', 'input_dir':'../../private'}))
    with pytest.raises(AssetPrepError, match='escapes'):
        prepare_assets(tmp_path / 'spec.json', tmp_path / 'out')


@pytest.mark.skipif(shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None,
                    reason='ffmpeg and ffprobe required')
def test_end_to_end_prepared_mp4(tmp_path):
    create_example(tmp_path / 'demo')
    cfg = tmp_path / 'demo' / 'spec.json'
    cfg.write_text(json.dumps({'source':'parts', 'input_dir': 'assets',
                               'parts': {k: {'arm_left':'arm','arm_right':'arm',
                                             'leg_left':'leg','leg_right':'leg'}.get(k,k)+'.png'
                                         for k in SHEET_ORDER},
                               'duration_sec': 1, 'fps': 12}))
    manifest, preview = prepare_assets(cfg, tmp_path / 'prepared')
    result = render_manifest(manifest, tmp_path / 'prepared' / 'demo.mp4')
    info = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(result)], text=True))
    assert 0.9 < float(info['format']['duration']) < 1.1
    assert info['streams'][0]['codec_name'] == 'h264'
    assert result.stat().st_size > 2000
