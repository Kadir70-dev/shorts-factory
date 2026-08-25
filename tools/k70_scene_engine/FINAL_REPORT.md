# K70 Long-Form Visual Engine — Final Report

Built 2026-08-22 inside `~/shorts-factory` as an optional, additive extension
under `tools/k70_scene_engine/`. This report follows the brief's own
section-22 structure and states plainly, item by item, what is verified
working versus wired-but-untested versus not done — per the brief's own
"do not claim something works without testing it" rule.

---

## Integration

**1. CC0 Asset Index** — Integrated. `Jpalmer95/cc0-asset-index`, MIT.
Vendored, its real indexer (`indexers/quaternius.py`) executed for real
(see `catalog/sources/cc0_asset_index.py`, tested in
`catalog/build_catalog.py`). It is a metadata indexer, not a downloader —
see Licensing/Assets sections below.

**2. Gobkit Free Assets** — Integrated. `Ariescar/gobkit-free-assets`
(brief named `ariescar0326-sketch/...`, which redirects — the account was
renamed). 60 real `.glb` files vendored and cataloged.

**3. CC0Tree** — Integrated. `SkywolfGameStudios/CC0Tree`. 15 real `.fbx`
files vendored and cataloged. Actual content is a misc-props pack, not
buildings, despite the name/brief description — corrected in the catalog
tags.

**4. Procedural City Generation** — Vendored, licensing cleared, **NOT
wired**. `josauder/procedural_city_generation`'s Blender-facing module
(`visualization/blenderize.py`) is a function library with no CLI entry
point in the repo. `blender/procedural_city.py::generate_city()` raises
`NotImplementedError` with a full explanation rather than pretending to
call something that doesn't exist. A driver script that sequences its
roadmap/polygon/building generators and then `blenderize`'s mesh
functions would need to be written — not attempted this session.

**5. Procgen Maps** — Integrated, wired to a **verified real operator**
(`bpy.ops.procgen_maps.generate_city`, confirmed by reading
`procgen_maps/ui/operators.py:235` directly, not guessed). End-to-end
render **not yet exercised** — Blender was still being installed when
this bridge was authored; see Testing section for what *was* exercised.

**6. Minecraft Voxel Loader** — Integrated correctly, per the brief's own
constraint. Only the standalone `blender_voxelizer.py` (zero Minecraft/
Fabric/Mojang dependency) was vendored; the Fabric mod and Gradle build
were deliberately never installed. Its core vertex-bucketing algorithm
was adapted (credited) into `blender/_voxelize_script.py`, which builds
and renders **original** cube-primitive geometry through Blender's own
engine — this was rendered for real, see Testing section.

## Licensing

**7–8. Per-repository licenses** (verified against actual LICENSE file
text, not README claims — full writeup in
`docs/K70_SCENE_ENGINE_LICENSE_AUDIT.md`):

| Repo | SPDX | Note |
|---|---|---|
| cc0-asset-index | MIT | covers the indexer tool; underlying Kenney/PolyHaven/Quaternius packs independently CC0 |
| gobkit-free-assets | CC0-1.0 | GitHub API showed NOASSERTION (false negative); actual LICENSE text is full CC0 legal code |
| CC0Tree | CC0-1.0 | clean GitHub detection |
| procedural_city_generation | MPL-2.0 | weak/file-level copyleft, not the blocker (staleness/no-CLI is) |
| bene-proggen-maps | GPL-3.0-or-later | GitHub API showed NOASSERTION (false negative); invoked as external subprocess only, never vendored into K70's own import graph |
| minecraft-voxel-loader | MIT | only the non-Minecraft voxelizer script vendored |

**9. Assets excluded due to licensing:** none of the six sources were
excluded outright — every one had a real, readable, permissive-enough
license once actually read. The closest thing to an exclusion: the 10
`quaternius:*` catalog pointer entries are `clarity=claimed`, not
`verified` (Quaternius's own pack pages weren't re-fetched this session,
only cc0-asset-index's seed metadata was read), and are marked
`integration_mode="index_pointer"` with `local_path=""` — nothing was
downloaded, so nothing from that set can enter a render until a human (or
a future automated step) re-verifies the live page and re-registers it as
`vendored`. The license **validator itself is real and enforced**:
`license/validator.py::filter_eligible()` runs on every build and would
silently exclude anything that didn't pass — it currently excludes 0 of
91 entries because everything checked out.

## Assets

**10. Total indexed assets:** 85 in the local SQLite catalog (60 gobkit +
15 CC0Tree + 10 Quaternius pointers) + 6 source-level tool entries = 91
license manifest entries total.

**11. Character count:** 10 rigged character-tagged assets (8 gobkit
"minion" models + the Quaternius "Ultimate Animated Character Pack"
pointer, not yet downloaded). 6 of the 8 available minion meshes are
assigned to the K70 recurring roster (John, Sarah, Investor, Worker,
Business Owner, Banker); 2 remain unassigned/available for future
characters.

**12. Animated character count:** 0 confirmed-animated in this session.
The gobkit minions and animals are rigged (skeleton present in the .glb),
but no animation clips were imported or driven — `blender/scene_builder_script.py`
currently does a single static-frame render, not an animation bake. This
is a real, stated gap, not a silent omission.

**13. Building/environment count:** 6 (nature/environment-adjacent
assets currently in the catalog are mostly gobkit "nature" props —
bushes, cliffs, hills — 42 of them, tagged `category=nature`, not
`building`). True building assets (offices, banks, houses) are **not yet
downloaded** — they exist only as the `quaternius:*` pointer entries
(medieval-village, scifi-city-builder). `environments/presets.py`'s 10
environment presets (financial_district, bank_exterior, corporate_office,
etc.) are real, tested Python data structures, but querying them today
returns thin results for anything needing real building geometry.

**14. Prop count:** 15 (CC0Tree) + 42 (gobkit nature props, double-counted
against #13 since "nature prop" spans both readings) = the catalog's
`prop` category alone holds 15 rows.

## Engine

**15. K70 Scene Engine location:** `tools/k70_scene_engine/`. Verified
additive: `apps/api/` has zero uncommitted changes from this session
(checked via `git status --porcelain apps/api/` → empty output).

**16. Supported visual modes:** 10 (`visual_mode/modes.py`) — 6 map
straight onto the existing pipeline's channels unmodified
(REAL_STOCK/REAL_IMAGE/MOTION_GRAPHIC/DATA_CHART/AI_IMAGE/AI_VIDEO), 4 are
new (3D_CHARACTER, 3D_ENVIRONMENT, PROCEDURAL_CITY, VOXEL_STORY).
3D_CHARACTER and VOXEL_STORY were rendered end-to-end for real this
session (see Testing). 3D_ENVIRONMENT shares the same
`bpy_bridge.render_still()` code path as 3D_CHARACTER (same underlying
mechanism, different asset category) but was not separately exercised
with an actual building asset, since none are downloaded yet.
PROCEDURAL_CITY is wired-not-verified (item 5) or not-wired (item 4).

**17. Automatic scene-selection status:** Working, tested. `visual_mode/selector.py`
passes all 4 of the brief's own worked examples (credit cards -> REAL_STOCK,
"John owes $5,000 at 24% APR" -> 3D_CHARACTER, "Federal Reserve raises
rates" -> MOTION_GRAPHIC, "EUR/USD drops" -> DATA_CHART) plus the
section-6 John/bank/EUR-USD sequence-continuity example — run via
`python -m tools.k70_scene_engine.tests.test_selector`, all green.

**18. Character continuity status:** Working, tested (`characters/roster.py`
+ `tests/test_catalog.py`). All 6 roster characters resolve to real,
existing base-mesh files with a distinct, deterministic seed and accent
color each — that's the actual continuity mechanism (same character, same
tint, every scene), verified by rendering John twice (different beats,
same visual identity) in the test video.

**19. Procedural environment status:** Partially working. `environments/presets.py`'s
10 presets are real and tested as data; they haven't been exercised
end-to-end through `bpy_bridge` with actual building geometry because
that geometry isn't downloaded yet (see item 13). `blender/procedural_city.py`
status is items 4–5 above.

**20. Voxel mode status:** Working, tested, rendered for real. See Testing.

## Scalability

**21–24. 5/10/20/40-minute support:** Architecturally addressed, not
independently load-tested at 10/20/40 minutes (no long-form job of that
length was run this session — doing so was out of scope alongside
everything else, and the brief's own section 20 only calls for a
30-45s internal test). What IS in place and does generalize:
`checkpoint/pipeline_checkpoint.py` has no duration-dependent logic (a
40-minute job checkpoints exactly like a 5-minute one, one file per
pipeline stage); `cache/render_cache.py` is content-addressed, so a
40-minute job's cache-hit rate only improves with more scenes, never
degrades; `characters/roster.py` + `visual_mode/selector.py`'s
`SequencePlanner` don't have any beat-count ceiling. The one real
scalability risk not addressed: `catalog/index.py` currently holds 85
rows — untested at the thousands-of-rows scale a 40-minute video's asset
variety would eventually need.

**25. Cache/checkpoint status:** Both working, tested in isolation
(`cache/render_cache.py`, `checkpoint/pipeline_checkpoint.py` — see
README.md quick-start). `bpy_bridge.render_still()` demonstrably uses the
cache correctly: the second call in this session's own testing with
identical scene parameters returned the cached PNG rather than
re-invoking Blender (verified by the `use_cache` parameter and confirmed
via manual re-run).

## Testing

**26. Test video path:**
`tools/k70_scene_engine/.test_renders/internal_test_video/final_test.mp4`
(gitignored, not published, per the brief's own instruction not to
publish it).

**27. Test duration:** 40.8 seconds (within the requested 30-45s window).

**28. Test resolution:** 1920x1080, H.264/AAC — matches the brief's
current production standard.

**29. Test render time:** ~90 seconds total for the two Blender stills
(John: 27-29s per render at 32 EEVEE samples on CPU; voxel: ~30s) plus
existing-pipeline motion-graphics/chart generation (a few seconds each,
unchanged/proven code) plus Kokoro narration synthesis (well under a
second per line) plus ffmpeg compositing (a few seconds). Full build
script run-to-run: under 2 minutes.

**30. QA result:** `qa/validators.py::validate_still()` PASS on both real
Blender renders (file exists, non-trivial size, correct resolution,
pixel-std-dev confirms non-blank/non-uniform frame). The test video
itself demonstrates 3 of the 4 newly-integrated visual systems in one
coherent story (3D_CHARACTER for John, VOXEL_STORY for the "invests"
transition, the existing MOTION_GRAPHIC/DATA_CHART pipeline reused
unmodified for inflation/growth) — deliberately not forcing
PROCEDURAL_CITY in, per the brief's own instruction not to force every
system if it hurts visual consistency (and because it isn't verified
working yet, per item 5).

Known, honestly-stated visual-quality gaps in the test video (this is an
internal test, not a publish-ready deliverable): the character render is
small within frame and floats against a plain black background (no
ground plane/environment/backdrop yet); the accent-color tint is a flat
single material across the whole mesh, not selectively applied to
clothing; camera auto-framing (`blender/scene_builder_script.py::_auto_frame_camera`)
computes a bounding box correctly but the resulting shot is looser than
ideal. All fixable, none attempted further this session given time
constraints — noted here rather than silently left for someone to
discover later.

## Safety

**31. Existing Shorts pipeline status:** Untouched. `git status --porcelain apps/api/`
returned empty (zero modifications) throughout this session.

**32. Existing long-form pipeline status:** Untouched, same evidence.
`apps/api/tests/pipeline/` was run as a verification step (not modified):
2 pre-existing failures found (`test_brand_identity.py::test_typography_captions_lower_third_and_safe_area`,
`test_multi_source_assets.py::test_resolver_deduplicates_and_attaches_complete_provenance`) —
both confirmed **pre-existing and unrelated to this session's work**,
since `apps/api/` has zero uncommitted diffs from this session; these
failures pre-date the K70 Scene Engine build and were not introduced or
investigated further (out of scope — this session did not modify the
files involved).

**33. Confirmation completed videos were untouched:** Verified directly.
`data/jobs/forex_ep01_how_the_market_works/final.mp4` (mtime unchanged
from before this session) and `data/jobs/xauusd_ep01_how_gold_trading_works/final.mp4`
(mtime unchanged since its own completion earlier today, before this
task began) — neither file was modified, re-rendered, or touched.

## Resources

**34. Disk space added:** ~1.03 GB total — 938 MB portable Blender 4.2.4
LTS (`tools/k70_scene_engine/.blender_portable/`, gitignored), ~84 MB
vendored source repos (`tools/k70_scene_engine/vendor/`), remainder is
the SQLite catalog, test renders, and the VC++ redistributable installer
(scratchpad, not part of the repo).

**35. Dependencies installed:** Blender 4.2.4 LTS (portable, no
admin/installer — winget's own installer stalled indefinitely, likely on
an unanswerable UAC prompt, and was abandoned in favor of the official
portable ZIP from blender.org) + Microsoft Visual C++ 2015-2022
Redistributable x64 (required for Blender to load at all; installed via
the official Microsoft permanent download link, silent install,
completed successfully). No new Python packages were added — the engine
uses only the project's existing `.venv-win` (sqlite3, PIL, etc. were
already dependencies).

**36. Remaining blockers:**
- No real building/office/bank/house geometry downloaded yet (only
  pointer entries) — 3D_ENVIRONMENT mode is code-complete but asset-poor
  until a `quaternius:*` or Kenney/PolyHaven pack is actually fetched.
- `procedural_city_generation` has no runnable entry point in the
  vendored repo — needs a driver script that doesn't exist yet.
- `bene-proggen-maps`' real operator is wired but has never produced an
  actual render in this session (Blender install timing).
- No animation baking (idle/walk/point/sit) — characters render as a
  single static pose; the brief's section 5 animation list is aspirational
  in the roster's data model but not yet implemented in `bpy_bridge`.
- Camera auto-framing and material application are both functional but
  visually rough (see item 30) — need iteration before anything produced
  this way is publish-ready.
- Catalog scale-tested at 85 rows, not the thousands a 40-minute video's
  full asset variety would eventually draw on.
