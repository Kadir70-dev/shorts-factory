#!/usr/bin/env python3
"""Before/after contact sheet: USA Inflation Short V1 vs V2 (real frames, same story beats)."""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "k70_usa_inflation_20261117"
V1 = D / "K70_Aurora_USA_Inflation_Short.mp4"
V2 = D / "K70_Aurora_USA_Inflation_Short_V2.mp4"
g2 = json.loads((D / "scene_graph_v2.json").read_text())
starts, t = {}, 0.0
for s in g2["scenes"]:
    starts[s["id"]] = (t, s["duration_sec"])
    t += s["duration_sec"]
at = lambda sid, f: starts[sid][0] + starts[sid][1] * f

ROWS = [("Hook", 1.9, at("s1", 0.6)), ("Cinematic line chart", 8.3, at("s2", 0.62)), ("Speed vs distance", 22.3, at("s5", 0.9)),
        ("Categories: bar race vs stat", 24.3, at("s6", 0.95)), ("Latest reading", 38.4, at("s8", 0.9)), ("Close", 41.3 - 1.0, at("s9", 0.5))]
W, H = 360, 640
sheet = Image.new("RGB", (W * 2 + 190, (H + 8) * len(ROWS)), (14, 18, 26))
d = ImageDraw.Draw(sheet)
f = ImageFont.load_default()
for r, (name, t1, t2) in enumerate(ROWS):
    for c, (path, tt) in enumerate(((V1, t1), (V2, t2))):
        out = ROOT / "data" / "k70_usa_inflation_20261117" / "_cmp.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{tt:.2f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={W}:{H}", "-q:v", "3", str(out)], check=True)
        sheet.paste(Image.open(out), (190 + c * W, r * (H + 8)))
    d.text((12, r * (H + 8) + H // 2 - 6), name.upper(), fill=(251, 191, 36), font=f)
d.text((190 + W // 2 - 10, 0), "V1", fill=(255, 255, 255), font=f)
d.text((190 + W + W // 2 - 10, 0), "V2", fill=(255, 255, 255), font=f)
sheet.save(D / "v1_vs_v2_comparison.jpg", quality=88)
(D / "_cmp.jpg").unlink(missing_ok=True)
print("wrote", D / "v1_vs_v2_comparison.jpg")
