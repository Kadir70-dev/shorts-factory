# K70 Voxel V2 -- World System Status (repo inspection pass)

All four world-system components the brief asked about are already
vendored and wired into the existing K70 pipeline. This is a status
check, not new integration work.

## Poly Haven / CC0 Asset Index
- `tools/k70_scene_engine/vendor/cc0-asset-index/` -- real project, CC0-only
  index (Poly Haven, Kenney, Quaternius adapters), CLI (`cc0a search/info/download/reindex`).
- Bridge already in the main codebase: `catalog/sources/polyhaven.py`,
  `catalog/sources/cc0_asset_index.py`.
- **Not yet populated**: `data/assets.jsonl` doesn't exist -- needs one
  `cc0a reindex` run (network metadata fetch only, no asset downloads,
  cheap) before it's actually queryable. Not run yet this session to
  avoid any resource contention with the longform video render.

## CC0Tree
- `tools/k70_scene_engine/vendor/CC0Tree/` -- real, populated: 15 FBX
  props under `Assets/` (one actual tree, `SM_Tree_1.fbx`, plus general
  CC0 props: baseball bat, bowling pin, crowbar, etc.). Small library,
  genuinely usable for environment dressing today.
- Bridge: `catalog/sources/cc0tree.py`.

## Procgen Maps
- `tools/k70_scene_engine/vendor/bene-proggen-maps/procgen_maps/` --
  substantial real codebase: `generators/city/` (streets, buildings,
  parking, signage, special_buildings), `generators/terrain.py`,
  `generators/dungeon.py`, materials, glTF exporter, tests. This is a
  full Blender addon, not a stub.
- Already used in production: `k70_scene_engine/.test_renders/proof_e_procgen/city_render_final.png`
  is the exact procedural-city image reused across EP03/EP04/the
  longform video's `procedural_city` beat right now.

## K70 Voxelizer (existing)
- `blender/voxelizer.py` + `_voxelize_script.py` -- voxelizes an
  arbitrary CC0 mesh into blocks (MIT-derived algorithm, zero Minecraft
  code).
- `blender/voxel_story.py` + `_voxel_story_script.py` -- purpose-built
  recognizable objects (house/bank/dollar-sign/car), voxelized. Proven
  working, in active use for the longform video's bank/dollar beats.
- **New this session**: `blender/voxel_human.py` + `_voxel_human_script.py`
  -- the K70-original beveled-box voxel CHARACTER system (not a true
  voxel grid, deliberately "premium stylized", per the approved
  direction change away from MB-Lab). This is the CURRENT primary
  character system, already producing the running longform video.
  This is the baseline Thomas Rig / Ice Cube get compared against.

## Net effect
World-asset infrastructure needs no new integration work -- only (a)
one cheap `cc0a reindex` run when it's safe to do so, and (b) actually
pulling specific assets in for a given scene as needed. The real open
question for V2 is purely on the CHARACTER side: does Thomas Rig or
Ice Cube beat the current custom voxel_human system enough to justify
a switch, given real render-reliability and licensing constraints.
