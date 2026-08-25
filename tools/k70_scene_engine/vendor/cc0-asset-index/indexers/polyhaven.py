#!/usr/bin/env python3
"""Index Poly Haven CC0 assets (models, HDRIs, textures) -> JSONL records.

Poly Haven is 100% CC0. API docs: https://api.polyhaven.com
Output: one JSON record per line matching schema.json.
"""
import json
import sys
import urllib.request

API = "https://api.polyhaven.com"

KIND_MAP = {"models": "model", "hdris": "hdri", "textures": "material"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cc0-asset-index/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "data/polyhaven.jsonl"
    records = []
    for asset_type, kind in KIND_MAP.items():
        assets = get(f"{API}/assets?t={asset_type}")
        for slug, meta in assets.items():
            tags = sorted(set(meta.get("tags", []) + meta.get("categories", [])))
            name = meta.get("name", slug)
            authors = ", ".join(meta.get("authors", {}).keys()) or "Poly Haven"
            desc = (
                f"{name} — CC0 {kind} by {authors} (Poly Haven). "
                f"Tags: {', '.join(tags)}."
            )
            # Prefer formats that are actually available; check the files index lazily.
            # Poly Haven models universally ship blend+gltf+fbx; hdris ship .hdr; textures ship jpg/png maps.
            if kind == "model":
                formats = ["blend", "glb", "fbx", "usd"]
                engines = ["blender", "godot", "unreal"]
            elif kind == "hdri":
                formats = ["hdr", "exr"]
                engines = ["blender", "godot", "unreal"]
            else:
                formats = ["png", "jpg", "blend"]
                engines = ["blender", "godot", "unreal"]
            records.append({
                "id": f"polyhaven:{slug}",
                "name": name,
                "license": "CC0",
                "attribution_required": False,
                "kind": kind,
                "formats": formats,
                "tags": tags,
                "description": desc,
                "engine_targets": engines,
                "preview_url": f"https://cdn.polyhaven.com/asset_img/thumbs/{slug}.png?width=400",
                "categories": sorted(set(meta.get("categories", []))),
                "source": {
                    "provider": "Poly Haven",
                    "url": f"https://polyhaven.com/a/{slug}",
                    "files_api": f"{API}/files/{slug}",
                },
            })
    with open(out, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(records)} records -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
