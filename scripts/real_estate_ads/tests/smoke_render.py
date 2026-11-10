"""Offline FFmpeg render check. Synthetic frames are fixtures, not marketing images."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "examples" / "azizi-florence.json").read_text())

with tempfile.TemporaryDirectory(prefix="realestate_smoke_") as d:
    base = Path(d)
    assets = base / "assets"
    assets.mkdir()
    for i, name in enumerate(MANIFEST["source_urls"]):
        image = Image.new("RGB", (900, 1600), "#677383" if i % 2 else "#435673")
        draw = ImageDraw.Draw(image)
        draw.text((100, 100), "SYNTHETIC FIXTURE - NOT A REAL PROPERTY", fill="white")
        image.save(assets / name, quality=78)
    output = base / "draft15.mp4"
    subprocess.run([
        sys.executable, str(ROOT / "render.py"),
        "--assets-dir", str(assets),
        "--duration", "15",
        "--preview-scale", "0.5",
        "--output", str(output)
    ], check=True, timeout=150)
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_name,width,height",
        "-of", "json", str(output)
    ], text=True, capture_output=True, check=True)
    details = json.loads(probe.stdout)
    assert abs(float(details["format"]["duration"]) - 15) < 0.15, details
    streams = details["streams"]
    assert any(s.get("codec_name") == "h264" and s.get("width") == 540 and s.get("height") == 960 for s in streams)
    assert any(s.get("codec_name") == "aac" for s in streams)
    print("PASS: 15s FFmpeg render, H.264 540x960, AAC, synthetic fixtures")
