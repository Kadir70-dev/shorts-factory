#!/usr/bin/env python3
"""Index Kenney.nl CC0 asset packs -> JSONL records.

All Kenney assets are CC0 (https://kenney.nl/assets, license page).
Packs are modular kits: best source of composable environment scaffolding.
We scrape the public asset listing; download URLs follow the pattern
https://kenney.nl/media/pages/assets/<slug>/.../<slug>.zip (resolved at download time).
"""
import json
import re
import sys
import urllib.request

CATEGORIES = ["3D", "2D", "Textures"]  # skip Audio (not engine-importable as assets here)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cc0-asset-index/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def iter_slugs():
    seen = set()
    for cat in CATEGORIES:
        page = 1
        while True:
            url = f"https://kenney.nl/assets/category:{cat}" + (f"/page:{page}" if page > 1 else "")
            html = get(url)
            slugs = sorted(set(re.findall(r"assets/([a-z0-9\-]+)'>", html)))
            new = [s for s in slugs if s not in seen]
            if not new:
                break
            for s in new:
                seen.add(s)
                yield s, cat
            if len(slugs) < 16:
                break
            page += 1


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "data/kenney.jsonl"
    records = []
    for slug, cat in iter_slugs():
        name = " ".join(w.capitalize() for w in slug.split("-"))
        tags = [t for t in re.split(r"[-]", slug) if len(t) > 2]
        kind = "kit" if ("kit" in slug or "pack" in slug or cat == "3D") else "material"
        desc = (
            f"{name} — CC0 game asset pack by Kenney ({cat}). "
            f"Game-ready; packs ship source formats (GLB/FBX/OBJ/PNG). "
            f"Tags: {', '.join(tags)}."
        )
        records.append({
            "id": f"kenney:{slug}",
            "name": name,
            "license": "CC0",
            "attribution_required": False,
            "kind": kind,
            "formats": ["zip", "glb", "fbx", "obj", "png"],
            "tags": tags + ["kenney", cat.lower()],
            "description": desc,
            "engine_targets": ["blender", "godot", "unreal"],
            "preview_url": "",
            "source": {
                "provider": "Kenney",
                "url": f"https://kenney.nl/assets/{slug}",
            },
        })
    with open(out, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(records)} records -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
