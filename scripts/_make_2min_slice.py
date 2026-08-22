import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "data" / "series" / "bitcoin_history" / "ep01" / "scene_graph.json"
dst = ROOT / "data" / "series" / "bitcoin_history" / "ep01" / "twomin_slice.json"

g = json.loads(src.read_text(encoding="utf-8"))
scenes = g["scenes"][:25]  # s1..s25, cum ~129.9s, good visual mix

g2 = dict(g)
g2["scenes"] = scenes
g2["meta"] = dict(g["meta"])
g2["meta"]["video_id"] = "btc_ep01_twomin_cut"
g2["meta"]["title"] = "The World Before Bitcoin — 2-Minute Cut"
g2["meta"]["description"] = (
    "A fast-paced 2-minute cut of Episode 1: The World Before Bitcoin. "
    "1971-2008: the gold standard breaks, inflation and bank failures follow, "
    "and a small group of cryptographers keep trying to build money no one can switch off.\n\n"
    "Educational history and commentary. Not financial advice."
)

total = sum(s["duration_sec"] for s in scenes)
print(f"scenes={len(scenes)} total_duration_sec={total:.1f}")
dst.write_text(json.dumps(g2, indent=2), encoding="utf-8")
print(f"wrote {dst}")
