# CC0 Asset Index

One searchable catalog of CC0 / public-domain game assets for **Blender, Godot, and Unreal** — built for humans *and* agents.

Every record in the index is license-validated at index time: **CC0 only, no attribution required, commercial use and modification allowed.** If it's in the index, you can build on it with zero strings attached.

## What's inside

- `data/assets.jsonl` — the canonical index (~2,500 assets; greppable, diff-friendly, PR-able)
- `data/index.sqlite` — derived fast-query cache (rebuild anytime)
- `scripts/cc0a` — dependency-free Python CLI: `reindex`, `search`, `info`, `download`
- `indexers/` — one adapter per source (Poly Haven, Kenney, Quaternius; more welcome)
- `schema.json` — the record schema

## Quick start

```bash
python3 scripts/cc0a search forest --kind kit
python3 scripts/cc0a search chair
python3 scripts/cc0a info polyhaven:ArmChair_01
python3 scripts/cc0a download polyhaven:ArmChair_01 --dir assets   # -> assets/cc0/polyhaven/ArmChair_01/
python3 scripts/cc0a reindex                                      # regenerate the whole index
```

### Browse visually

```bash
python3 scripts/generate_gallery.py   # -> gallery/index.html (single self-contained file)
xdg-open gallery/index.html           # thumbnails, provider/kind/grade filters, live search
```

The gallery is one static HTML file — hotlinked thumbnails, zero hosting, works from `file://`. Click any asset id to copy it, then `cc0a download <id>`.

### Semantic ("vibe") search

```bash
# one-time setup: pip install numpy onnxruntime huggingface_hub
#   hf download Xenova/all-MiniLM-L6-v2 onnx/model_quantized.onnx vocab.txt --local-dir ~/.cache/cc0-asset-index/minilm
python3 scripts/semantic_search.py embed
python3 scripts/semantic_search.py search "cozy medieval tavern interior"
python3 scripts/semantic_search.py search --image caption.txt   # BLIP/CLIP/VLM caption of a reference image
```

Image-based flow: caption any reference image with your favorite local VLM (BLIP, LLaVA, etc.), save the caption to a text file, pass it via `--image`. Lighter than generating a new asset from scratch — find the closest existing CC0 thing first.

Downloads land in `assets/cc0/<provider>/<slug>/` with a `LICENSE.json` next to them — the full provenance record.

## Importing into your editor

**Blender** — download `--format blend` (default for models) and File → Append/Link, or import the `.gltf`/`.fbx` directly. Via [blender-mcp](https://github.com/ahujasid/blender-mcp) an agent can do this for you.

**Godot 4** — download `--format gltf` (glTF is native); drop the folder into your project, Godot imports automatically.

**Unreal** — download `--format fbx` (or glTF via the glTF importer plugin); drag into Content Browser.

**HermesForge** — after downloading a GLB into a Godot project dir, the `hermes_scene_*` / bridge tooling can place it directly.

## Record schema (summary)

```json
{
  "id": "polyhaven:ArmChair_01",
  "name": "Arm Chair 01",
  "license": "CC0",
  "attribution_required": false,
  "kind": "kit | model | hdri | material | scene",
  "formats": ["blend", "glb", "fbx"],
  "tags": ["furniture", "chair"],
  "description": "Plain-text description for keyword + future embedding search",
  "engine_targets": ["blender", "godot", "unreal"],
  "source": { "provider": "Poly Haven", "url": "...", "files_api": "..." }
}
```

`kind: kit` = composable modular pack — prefer these for environment scaffolding.

## Contributing

- **Add a source**: write `indexers/<source>.py` emitting records matching `schema.json`, wire it into `cc0a reindex`, PR it. Sources must be verifiably CC0/public-domain.
- **Fix/enrich records**: `data/assets.jsonl` is canonical — PRs improving tags/descriptions are welcome (they get overwritten by reindex only if the indexer doesn't produce them; prefer fixing the indexer).
- See `MASTER_PLAN.md` for the roadmap (semantic search, LoRA style layers, contribution flow).

## License of this repo

Index tooling: MIT. Asset records are metadata; the assets themselves are CC0 by their respective authors (see each record's `source.url`). Contributor representations, maintainer disclaimer, and takedown policy: [LEGAL.md](LEGAL.md).
