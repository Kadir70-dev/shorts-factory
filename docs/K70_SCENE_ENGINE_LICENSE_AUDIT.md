# K70 Scene Engine — License Audit

Verified 2026-08-22 directly against the GitHub API (`GET /repos/{owner}/{repo}`)
and each repo's actual `LICENSE` file content (not README claims alone).
Machine-readable form: `tools/k70_scene_engine/license/sources.py` +
generated `tools/k70_scene_engine/license/manifest.json`.

## Summary table

| # | Repo (as named in the brief) | Actual repo | SPDX | GitHub-detected? | Commercial use | Integration mode |
|---|---|---|---|---|---|---|
| 1 | CC0 Asset Index | `Jpalmer95/cc0-asset-index` | MIT | Yes | Yes | vendored |
| 2 | Gobkit Free Assets | `Ariescar/gobkit-free-assets` (renamed from `ariescar0326-sketch`) | CC0-1.0 | **No** (NOASSERTION) | Yes | vendored |
| 3 | CC0Tree | `SkywolfGameStudios/CC0Tree` | CC0-1.0 | Yes | Yes | vendored |
| 4 | Procedural City Generation | `josauder/procedural_city_generation` | MPL-2.0 | Yes | Yes | subprocess-only, **not wired** |
| 5 | Procgen Maps | `Beneking102/bene-proggen-maps` | GPL-3.0-or-later | **No** (NOASSERTION) | Conditional (external tool only) | subprocess-only |
| 6 | Minecraft Voxel Loader | `carl-vbn/minecraft-voxel-loader` | MIT | Yes | Yes | vendored (voxelizer script only) |

Two of six show `NOASSERTION` from GitHub's own license detector despite
having a real, unambiguous LICENSE file — GitHub's detector is a
best-effort text matcher and both of these had non-standard preambles
(gobkit's LICENSE leads with an attribution note before the CC0 legal
code; bene-proggen-maps' leads with an addon-specific rationale
paragraph before the GPLv3 text) that threw it off. Both were manually
read in full before being marked `clarity=verified`.

## Per-repo notes

### 1. CC0 Asset Index (`Jpalmer95/cc0-asset-index`)
MIT-licensed **indexer tool**, not a bundled asset library — 35KB, all
Python. Contains real indexers for three well-known, independently
CC0-licensed asset sources: Kenney.nl, PolyHaven.com, Quaternius.com.
`indexers/quaternius.py` was executed for real (see
`catalog/sources/cc0_asset_index.py`); it emits pack **metadata**
(name/tags/description/URL), not downloaded geometry — there is no
vendored downloader for actual pack contents in this repo. Created
2026-07-26 (~4 weeks before this audit), 0 GitHub stars: unproven,
no community track record, but its own code and license are legitimate
and were read in full, not assumed.

### 2. Gobkit Free Assets (`Ariescar/gobkit-free-assets`)
The GitHub identifier in the brief (`ariescar0326-sketch/gobkit-free-assets`)
redirects — the account was renamed to `Ariescar`. Genuinely bundles 60
real `.glb` files (10 animals, 8 rigged "minion" humanoid characters, 42
nature props). LICENSE file is the full CC0 1.0 Universal legal text plus
an explicit grant: *"These 3D assets are provided by Gobkit / Alsomind
Tech Co., Ltd. No rights reserved."* Public domain, no attribution
required. Created 2026-07-25, 1 star: also unproven, but license and
content are both verified real.

### 3. CC0Tree (`SkywolfGameStudios/CC0Tree`)
CC0-1.0 per GitHub's own detection (a clean match this time). Despite the
name and the brief's description ("Buildings, props and environment
assets"), the actual content is 15 `.fbx` files — a small misc-props pack
(tools, a computer tower, sports equipment, one tree), **not** a
buildings/environment library. Useful for prop dressing only.

### 4. Procedural City Generation (`josauder/procedural_city_generation`)
Real, respected (594 stars), MPL-2.0. MPL-2.0 is weak/file-level
copyleft: using it (even importing its modules directly) only obligates
sharing modifications to MPL-covered files themselves, not K70's own
codebase — licensing is not the blocker here. The blocker is that
`visualization/blenderize.py`, the module that actually talks to `bpy`,
is a **function library** (`try: import bpy ... except: pass` at module
scope, no CLI, no `if __name__ == "__main__"`) with no shipped driver
script. Last pushed 2023-01-12. **Not wired** in this session — see
`blender/procedural_city.py::generate_city()`, which raises
`NotImplementedError` rather than pretending to work.

### 5. Procgen Maps (`Beneking102/bene-proggen-maps`)
GPL-3.0-or-later. Its LICENSE file states directly: *"This program
(procgen_maps) is a Blender addon that uses Blender's Python API (bpy)
and is therefore licensed under [GPLv3]... consistent with Blender's own
GPL licensing terms."* GPL restricts redistributing/modifying the addon's
own source; it does not make renders produced with it GPL (same
principle as artwork made in GPL-licensed Blender/GIMP not being GPL
itself). K70 invokes it only as an external Blender subprocess
(`blender/procedural_city.py::generate_map()`, calling the real, verified
`bpy.ops.procgen_maps.generate_city` operator with
`context.scene.procgen_maps.seed` set first) — never vendors or imports
its Python modules into K70's own code, keeping the two works from
combining under GPL terms. Targets Blender 4.2 (its own `bl_info`) —
current, not stale. Wired to a real operator; end-to-end render not yet
exercised (Blender was still installing).

### 6. Minecraft Voxel Loader (`carl-vbn/minecraft-voxel-loader`)
MIT-licensed, but the brief's one-line summary ("Technical
voxelization/block-style rendering experiments") undersells what it
actually is: **a Minecraft Fabric mod (Java) plus a standalone Blender
script**, not a general-purpose voxel renderer. Only
`Scripts/blender_voxelizer.py` — pure `bpy`/`bmesh`/`numpy`, zero
Minecraft/Fabric/Mojang dependency — was vendored. The Fabric mod,
Gradle build, and everything that talks to an actual Minecraft client
were deliberately **not** vendored and will never be installed or
invoked: doing so would require a licensed Minecraft copy and would
render inside Mojang's own client/renderer, directly conflicting with the
brief's explicit ban on Minecraft/Mojang assets and branding.
`blender/_voxelize_script.py` adapts the original's core vertex-bucketing
algorithm (credited in its own docstring) but replaces the
Minecraft-block-placement output entirely with original cube-primitive
mesh geometry rendered by Blender's own engine.

## Exclusions

None of the six sources were excluded outright. The one asset-class risk
worth naming explicitly: `quaternius:*` pointer entries in the catalog
(`catalog/sources/cc0_asset_index.py::seed_pointers()`) are
`clarity=claimed`, not `clarity=verified` — the pack pages themselves
were not re-fetched and re-read in this session, only cc0-asset-index's
own seed metadata (which says CC0) was consulted. They are marked
`integration_mode="index_pointer"` and carry `local_path=""` — nothing
has actually been downloaded, so nothing from that pointer set can enter
a render until a human (or a future automated step) re-verifies the live
pack page and re-registers it as `vendored`.
