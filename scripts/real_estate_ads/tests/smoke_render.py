"""Offline FFmpeg render check: 15s and 30s drafts with every image slot PENDING_ASSET.

No images of any kind are supplied; the renderer must fall back to neutral IMAGE PENDING frames.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory(prefix="realestate_smoke_") as d:
    base = Path(d)
    empty_assets = base / "assets"
    empty_assets.mkdir()
    for duration in (15, 30):
        output = base / f"draft{duration}.mp4"
        subprocess.run([
            sys.executable, str(ROOT / "render.py"),
            "--assets-dir", str(empty_assets),
            "--duration", str(duration),
            "--preview-scale", "0.5",
            "--output", str(output)
        ], check=True, timeout=300)
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_name,width,height",
            "-of", "json", str(output)
        ], text=True, capture_output=True, check=True)
        details = json.loads(probe.stdout)
        assert abs(float(details["format"]["duration"]) - duration) < 0.15, details
        streams = details["streams"]
        assert any(s.get("codec_name") == "h264" and s.get("width") == 540 and s.get("height") == 960 for s in streams)
        assert any(s.get("codec_name") == "aac" for s in streams)
        print(f"PASS: {duration}s blank-image draft, H.264 540x960, AAC, no images supplied")

    # Public export must refuse while slots are pending, even with every clearance flag.
    blocked = subprocess.run([
        sys.executable, str(ROOT / "render.py"), "--assets-dir", str(empty_assets),
        "--duration", "15", "--preview-scale", "0.5", "--output", str(base / "public.mp4"),
        "--public", "--confirm-render-rights", "--confirm-current-price", "--permit-id", "TEST-ONLY",
    ], text=True, capture_output=True, timeout=120)
    assert blocked.returncode != 0 and "PENDING_ASSET" in blocked.stderr, blocked.stderr[-400:]
    assert not (base / "public.mp4").exists()
    print("PASS: public export blocked while image slots are PENDING_ASSET")
