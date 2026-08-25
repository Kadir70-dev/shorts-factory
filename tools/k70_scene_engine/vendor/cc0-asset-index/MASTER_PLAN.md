# MASTER_PLAN.md — CC0 Asset Index

A living, agent-first library of CC0/public-domain assets for Blender, Godot, and Unreal.

## Vision

One interface where any human or agent can answer: **"what open assets exist for X, and how do I get one into my editor in 30 seconds?"** — with zero licensing ambiguity. Index-time CC0 validation means every record is pre-cleared for commercial modification and redistribution of derivatives.

## Architecture decisions (recorded)

- [x] **Index-time license validation** — only CC0/PD admitted; no runtime license checks needed downstream.
- [x] **JSONL canonical + SQLite derived** — git-friendly, greppable, PR-able index; SQLite rebuilt by `cc0a reindex`.
- [x] **Python stdlib only** — no deps; runs anywhere an agent runs. Rust/C++ frontend deferred until there's a proven perf bottleneck (HTTP is the bottleneck, not parsing).
- [x] **No hosting, no server** — the git repo IS the distribution. Contribution = PRs adding indexers or seed records.
- [x] **`kind: kit` first-class** — modular packs (Kenney, Quaternius) are the best environment scaffolding; search boosts kits.
- [x] **Description field from day one** — enables keyword search now, embedding/vector search later without backfill.
- [x] **Download convention** — `assets/cc0/<provider>/<slug>/` + `LICENSE.json` beside every asset.
- [x] **Grading fields in schema from v1.1** — optional `grade` (gold/silver/bronze/archive), `grade_reason`, `generated_by`, `provenance`. Ungraded = treated as silver. Archive ≠ delete: archived records drop out of default search (`--all` shows them) so the search space stays high-quality while history is preserved. Enhancement lineage lives in `provenance` so an enhanced asset always names its original + method.
- [x] **CC0-only rule is absolute** (CONTRIBUTING.md) — no CC-BY/NC/SA, no royalty-free stock, AI-generated only when the model dedicates outputs CC0-equivalent and contributor dedicates likewise.

## Status

- [x] Schema v1.1 (schema.json) — added grade/grade_reason/generated_by/provenance (optional, non-breaking)
- [x] Search honors grading: gold boost, archive hidden by default (`--all` to include)
- [x] CONTRIBUTING.md + AGENTS.md (dual-audience: human contributors and consuming/contributing agents)
- [x] LEGAL.md (contributor reps/warranties, AS-IS disclaimer, takedown) + scripts/validate.py CI
- [x] Static gallery (scripts/generate_gallery.py → gallery/index.html: thumbnails, provider/kind/grade filters, client-side search, works from file://)
- [x] Semantic search (scripts/semantic_search.py: MiniLM ONNX, 3.6MB embeddings; `search "vibe"` + `--image caption.txt` for BLIP/CLIP/LLaVA reference-image flow). Optional deps only; core CLI remains stdlib-only.
- [x] Poly Haven indexer (2,286 records: models, HDRIs, materials) — API-backed, formats incl. blend/gltf/fbx
- [x] Kenney indexer (200 packs; paginated category scrape)
- [x] Quaternius indexer (10 curated seed packs; site is JS-driven, seed-list approach)
- [x] CLI: reindex / search / info / download (Poly Haven downloads incl. texture deps verified)
- [x] Hermes skill `cc0-assets`
- [ ] CI: weekly reindex + schema validation (GitHub Action)
- [ ] Kenney/Quaternius direct zip resolution at download time (scrape zip link from pack page)

- [x] Kenney/Quaternius direct zip resolution at download time — *Kenney done via page scrape hint; Quaternius pending*
- [x] Static gallery (`scripts/generate_gallery.py` → gallery/index.html, 1 file, thumbnails + filters, works from file://)
- [x] Semantic search (`scripts/semantic_search.py`, MiniLM-L6-v2 ONNX, 3.6MB embeddings for 2.5k assets, optional deps — core CLI stays stdlib-only)
- [x] Image→caption→search bridge (`--image caption.txt`; caption produced by any local BLIP/CLIP/LLaVA the user already runs)

### v1 — breadth + semantics
- [ ] More adapters: Openverse (CC0 filter), Smithsonian Open Access, Blend Swap CC0, ambientCG (CC0 materials), KayKit (CC0)
- [ ] Native CLIP image embeddings for true image→asset search (skip the caption step; heavier, opt-in)
- [ ] Collections manifests + `cc0a download <collection>`

### v2 — contribution loop + style layer
- [ ] Grading pipeline: automated signals (polycount, texture res, broken files) + community votes → `grade` field; archived records compress to text-only stubs keeping description + provenance so nothing is ever lost
- [ ] Enhancement loop: community-run upscaling/regeneration with open-source 3D models (at contributor's compute expense); new record links back via `provenance.original_id`, original gets `grade: archive` + `grade_reason` naming the successor
- [ ] PR-based contribution flow with license-audit CI (verify claimed CC0 against upstream)
- [ ] Optional hosted search API (only if usage demands it)
- [ ] LoRA style layers: community LoRAs applicable to asset texture re-rendering / concept-variants at the user's own inference expense (heavy compute stays client-side)
- [ ] Rust CLI mirror of cc0a (only if perf proves to matter)

### Non-goals (for now)
- Asset hosting (we index, providers host)
- Paid/attribution-licensed assets (CC-BY etc. — maybe a separate index later)
- Format conversion (glTF/blend/fbx coverage from sources is good enough; converters are a trap)

## Sources currently indexed

| Provider | License | Records | Notes |
|---|---|---|---|
| Poly Haven | CC0 | 2,286 | models, HDRIs, materials; API |
| Kenney | CC0 | 200 | modular game kits; category scrape |
| Quaternius | CC0 | 10 (seed) | animated/rigged low-poly packs; curated seed list |
