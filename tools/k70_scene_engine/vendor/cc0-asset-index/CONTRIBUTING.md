# Contributing to CC0 Asset Index

Thanks for helping grow the library. The bar for entry is intentionally simple, and there is **one rule that overrides everything else**:

## The one hard rule: CC0 / public domain only

Every asset in this index must be usable by **anyone, for anything, forever** — commercial use, modification, redistribution of derivatives, no attribution, no copyleft, no field-of-use restrictions.

That means:

- ACCEPTED: CC0, public domain dedications (e.g. Unlicense-style dedications for assets), government/public-domain works (e.g. Smithsonian Open Access CC0)
- REJECTED: CC-BY, CC-BY-SA, CC-BY-NC (any -NC or -SA variant), GPL/MIT/BSD-licensed *assets* (fine for code, wrong tool for art — they impose attribution/share-alike on derivatives), "free for personal use", "free with account", royalty-free-but-restricted stock licenses, AI-generated content of unclear provenance

If you are not 100% sure an asset or source is CC0-equivalent, **it does not go in**. When in doubt, leave it out or open an issue to discuss first. License validation happens at index time and is the foundation of the whole project — one bad record erodes trust in every record.

By contributing, you accept the contributor representations in [LEGAL.md](LEGAL.md) — read it before your first PR. Malicious or repeat license violations result in a permanent ban from the project.

### AI-generated assets

AI-generated assets are welcome **only if** the generating model's license dedicates outputs to the public domain or CC0-equivalent, and the contributor explicitly dedicates their own contribution as CC0. Record the generator in the record's `generated_by` field (see schema). This keeps the door open for open-source generation to grow the library without contaminating it.

## Ways to contribute

### 1. Add a new source (indexer)

The highest-leverage contribution. One good adapter = hundreds of new assets.

1. Verify the source is genuinely, entirely CC0 (read their license page; link it in your PR).
2. Create `indexers/<source>.py`:
   - Emit one JSON object per line matching `schema.json`
   - `id` format: `<source>:<slug>`
   - Fill `description` with rich, human-readable text (this powers keyword search now and embedding search later — a good description is as valuable as the asset)
   - Set `kind` honestly: `kit` only for composable modular packs
   - Use only Python stdlib (no new dependencies)
3. Wire it into `scripts/cc0a` `cmd_reindex` (add to the `indexers` list).
4. Run `python3 scripts/cc0a reindex` and confirm your records appear and validate.
5. PR: include the source's license URL and a sample of 2-3 records.

If the source is JS-driven and can't be scraped with stdlib, use a curated seed JSON (see `indexers/quaternius_seed.json`) — hand-maintained entries are fine; quality over coverage.

### 2. Improve records (tags, descriptions, grading)

Better metadata beats more assets. PRs that enrich descriptions, add tags, or correct `kind`/`formats` are very welcome — but **fix the indexer, not the JSONL output** (the JSONL is regenerated on reindex; hand edits there get overwritten).

### 3. Curate collections (coming in v1)

Collection manifests ("fantasy village starter", "sci-fi corridor set") will live in `collections/` as JSON lists of asset ids. Watch MASTER_PLAN.md.

### 4. Grading and enhancement (coming in v2 — help design it)

The schema already reserves `grade` and `provenance` fields. If you want to help build:

- **Grading**: community/automated quality signals (polycount sanity, texture resolution, broken normals, generation method) → `grade: gold|silver|bronze|archive`. Low-grade assets get demoted in search, never deleted.
- **Enhancement/upscaling**: as open-source 3D generation models improve, community members regenerate or enhance old assets at their own compute expense. The original is never destroyed — it's archived in text/compressed form with a `provenance` note (`original_model`, `enhanced_with`, `enhanced_by`, `date`) so anyone can trace or remake it.

Design discussion happens in GitHub issues before code.

## PR checklist

- [ ] Every new asset/source is verifiably CC0 (license URL included in PR)
- [ ] `python3 scripts/cc0a reindex` runs clean and records match `schema.json`
- [ ] Indexer uses Python stdlib only
- [ ] Descriptions are genuinely descriptive (what it is, style, best use)
- [ ] No asset binaries committed (we index, providers host)

## Code of conduct

Be kind, be precise about licenses, assume good faith. Maintainers may reject any contribution on license-grounds alone without further justification — that's the job.
