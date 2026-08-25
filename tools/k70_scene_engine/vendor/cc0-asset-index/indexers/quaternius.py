#!/usr/bin/env python3
"""Index Quaternius CC0 packs -> JSONL records.

Quaternius ships 100% CC0 low-poly game asset packs (quaternius.com).
The site is JS-driven, so we scrape the public packs index and fall back to
the curated seed list in indexers/quaternius_seed.json for canonical entries.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "data/quaternius.jsonl"
    with open(os.path.join(HERE, "quaternius_seed.json")) as f:
        packs = json.load(f)
    records = []
    for p in packs:
        slug = p["slug"]
        name = p["name"]
        tags = p["tags"]
        records.append({
            "id": f"quaternius:{slug}",
            "name": name,
            "license": "CC0",
            "attribution_required": False,
            "kind": "kit",
            "formats": p.get("formats", ["glb", "fbx", "obj", "blend"]),
            "tags": tags + ["low-poly", "kit", "quaternius"],
            "description": p["description"] + " Tags: " + ", ".join(tags) + ".",
            "engine_targets": ["blender", "godot", "unreal"],
            "preview_url": p.get("preview_url", ""),
            "source": {
                "provider": "Quaternius",
                "url": p["url"],
            },
        })
    with open(out, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(records)} records -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
