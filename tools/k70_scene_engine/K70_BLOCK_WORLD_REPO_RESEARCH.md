<!-- Title: K70 Block-World Repo Research -->
# K70 Premium Block-World — Open-Source Research Report

Research only. Nothing in K70 V3/V3.1 was modified, rendered, or hand-built as
part of this task. Findings below are sourced from live GitHub API queries
(license, last-push date, star/fork counts) and README/site fetches performed
during this research pass.

---

## 1. Ranked table

| Repo / Tool | Purpose | Quality Potential /10 | Automation /10 | Blender 4.2 Compat | Code License | Asset License | Commercial Safety | Integration Difficulty | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **MCprep** (Moo-Ack-Productions/MCprep) | Blender addon: Minecraft world-import, material prep, mesh-swap, mob/player spawner, sky/animation utilities | 3/10 *for K70* (8/10 if you actually used Minecraft assets) | 3/10 — GUI-operator addon, no documented Python/headless API | Claims 2.80–4.0 explicitly; 4.2 unconfirmed but actively maintained (pushed Jul 2026) | GPL-3.0 | Own bundled assets: **CC-BY** (attribution required). Its *flagship* features (world import, mob/player spawning) require **actual Minecraft assets → Mojang ToS applies** | CONDITIONAL — safe only if you never touch the Minecraft-asset features, which is most of its value | Medium-high (GPL code, GUI-first design fights automation) | **REJECT** for integration |
| **jMc2Obj** (jmc2obj/j-mc-2-obj) | Java tool: exports an existing Minecraft world save to OBJ | 2/10 *for K70* | Limited — Java GUI, no CLI found | N/A (exports plain OBJ; Blender-agnostic) | GPL-2.0 | Requires a real Minecraft world save → **Mojang-derived textures/geometry** | **UNSUITABLE** for monetized use without real Minecraft ownership + redistribution rights | High (wrong input entirely for K70's "original assets" mandate) | **REJECT** |
| **Mineways** (erich666/Mineways) | C++/Windows GUI: exports Minecraft world saves to OBJ/USD/3D-print formats | 2/10 *for K70* | None — interactive GUI only, no scripted export path found | N/A | `NOASSERTION` (non-standard license file, unclear terms) | Same as above — **requires a real Minecraft world**, Mojang ToS applies | **UNSUITABLE/UNCLEAR** | High | **REJECT** |
| **VoxCity** (kunifujiwara/VoxCity) | Python framework: real-world geospatial 3D city reconstruction (solar/microclimate simulation) from GIS data | 2/10 — **wrong domain entirely**, not a stylized city builder | 9/10 (pure Python API, headless, Jupyter-friendly) — but solving the wrong problem | Blender only as an OBJ *export target*, not a plugin | MIT | Bundled data from OSM/ESA/USGS — mixed, source-by-source, not asset-license-clean for arbitrary reuse | CONDITIONAL/UNCLEAR (depends which geodata source) | High (repurposing a climate-simulation tool for cinematic city dressing is the wrong tool for the job) | **REJECT** |
| **procedural_city_generation** (josauder) | Python + Blender-visualized procedural road-network/building-layout generator | 6/10 for the *layout algorithm* only — visual output is not block/pixel styled | 7/10 (script-driven, no GUI dependency apparent) | **Unconfirmed, likely stale** — no push since Jan 2023 (3.5+ yrs), pre-dates several Blender API changes | MPL-2.0 | N/A (procedural geometry, no bundled art) | SAFE (permissive code, no third-party art) | Medium-high (porting a 3.5-year-stale codebase to 4.2) | **CONDITIONAL** — worth mining for the *layout algorithm idea* only, not the code/visuals directly |
| **Block-On** (BrendanParmer/Block-On) | Blender add-on: procedurally voxelizes an *existing* mesh into a blocky form | 5/10 — could auto-blockify CC0 low-poly geometry | 5/10 (addon operators, likely `bpy.ops`-callable, unverified headless) | **Unconfirmed, stale** — no push since Jan 2023 | MIT | N/A (a tool, not an asset pack) | SAFE | Medium (stale, single-maintainer, unverified on 4.2 — same fragility profile the user wants to avoid repeating) | **CONDITIONAL** — small isolated prototype only, don't depend on it blind |
| **Kenney.nl** (City Kit, Car Kit, Factory Kit, etc.) | CC0 low-poly asset library — modular buildings, roads, vehicles, props | 8/10 — excellent variety, actively maintained | 10/10 — plain static FBX/OBJ/glTF files, trivially scriptable via `bpy.ops.import_scene.*`, zero addon/GUI dependency | Fully compatible (format-agnostic mesh files) | N/A (assets, not code) | **CC0**, explicitly no commercial restriction, no attribution required (verified directly on kenney.nl asset page) | **SAFE** | Low-medium (geometry is smooth/low-poly, not literally cubic/pixel — needs retexturing to match K70's pixel-art language) | **STRONGLY RECOMMEND** (as geometry source, paired with K70 textures) |
| **Quaternius** (LowPoly Buildings Pack, Modular Street Pack) | CC0 low-poly asset library — modular buildings (swappable atlas palettes), street/vehicle pack | 8/10 — same tier as Kenney, complementary variety | 10/10 — same as Kenney (FBX/OBJ/Blend static files) | Fully compatible | N/A | **CC0** (confirmed via multiple listing pages) | **SAFE** | Low-medium (same retexturing consideration as Kenney) | **STRONGLY RECOMMEND** |
| **Mesh2Motion** (Mesh2Motion/mesh2motion-app) | Web app (Node.js): auto-rig arbitrary GLB meshes with human/animal skeletons + Mixamo-style animation export | 2/10 *for K70's rig specifically* — built for skinned/skeletal organic meshes, not Empty-parented rigid boxes | 4/10 — browser app, not a native Blender/Python pipeline step; would need an export/import round-trip | N/A (web tool, GLB in/out) | MIT (code) + **CC0** (art/animations) | SAFE | Medium-high (wrong rig paradigm for K70's architecture) | **REJECT** for character work now; note for a *possible future organic-NPC* need only |

---

## 2. Best combo for K70

```
WORLD/CITY LAYOUT:
  K70 custom (current _k70_block_kit.py placement logic) --
  procedural_city_generation's ROAD/BUILDING-PLACEMENT ALGORITHM is worth
  studying for ideas later, but its code is too stale to adopt directly.

CHARACTERS:
  K70 V3.1 current system (_voxel_human_v3_script.py, Empty-driven rigid
  rig). No open-source alternative found that fits a rigid-block
  character without repeating a fragile "Thomas Rig"-style dependency.
  Mesh2Motion and MPFB2 both target organic/skeletal meshes -- wrong
  paradigm for K70's boxes.

PIXEL MATERIALS:
  K70 custom (gen_k70_skin.py / gen_k70_env_textures.py). This IS K70's
  actual differentiator -- no external tool provides "original K70 pixel
  atlases." MCprep's textures are literal Minecraft-derived and off-limits
  per the project's own no-Minecraft-assets rule.

CITY/PROPS GEOMETRY:
  Kenney.nl (City Kit, Car Kit) + Quaternius (LowPoly Buildings Pack,
  Modular Street Pack) -- CC0, actively maintained, trivially scriptable,
  far more building/vehicle/street-furniture variety than hand-coding more
  primitives in _k70_block_kit.py can practically achieve. Import as
  static geometry, then re-texture/re-material to match K70's pixel-art
  language (see V4 architecture below) -- this is the one area where real
  time savings exist.

ANIMATION:
  K70 custom (animate_walk/idle/point/sit in _voxel_human_v3_script.py).

LIGHTING/RENDER:
  K70 custom (lighting_presets.setup_block_world_v31, Blender EEVEE_NEXT).
  No external tool needed or beneficial here.

K70 CUSTOM CODE (what we should still own ourselves):
  - Character rig + animation functions
  - The textured_box()/simple_textured_box() UV + nearest-neighbor
    technique -- this is the trick that makes ANY geometry (hand-built or
    imported) read as K70 pixel/block-world, so it stays essential even if
    geometry is sourced externally
  - gen_k70_skin.py / gen_k70_env_textures.py (original pixel-art authoring)
  - lighting_presets.py block_world_v31
  - Scene assembly / camera / xfade / narration pipeline (build_*.py scripts)
  - Overall shot composition and creative direction
```

---

## 3. The most important question

**"Are we currently wasting time rebuilding functionality that mature open-source repositories already provide?"**

### PARTIALLY.

Specifically: the **static exterior prop/building/vehicle geometry** hand-coded
in `_k70_block_kit.py` is the one area where mature, actively-maintained,
CC0/commercially-safe libraries (Kenney, Quaternius) already exist with
meaningfully more variety and modeling detail than we can practically
hand-author box-by-box. That part is a real, avoidable time cost.

We are **not** wasting time on:
- the character rig/animation (no viable replacement exists for our rigid,
  Empty-driven architecture without reintroducing Thomas-Rig-class fragility)
- the pixel texture/material system (this is genuinely K70's own asset, and
  no external tool replicates it — MCprep's textures are Minecraft's own and
  off-limits under the project's own rule)
- the lighting/camera/scene-assembly pipeline (Blender-native, already
  working, nothing external solves it better)

### Exactly which functions in `_k70_block_kit.py` to STOP hand-building:

| Function | Replace with | Priority |
|---|---|---|
| `build_building_multistory()` | Kenney City Kit / Quaternius LowPoly Buildings Pack modules | High |
| `build_vehicle()` | Kenney Car Kit / Quaternius Modular Street Pack vehicles | High |
| `build_streetlamp()`, `build_traffic_light()`, `build_bench()`, `build_bin()`, `build_fence_segment()`, `build_planter()` | Kenney/Quaternius street-furniture props (both packs include these prebuilt, in more variety) | Medium-high |
| `build_tree()` | Kenney/Quaternius nature packs (marginal gain — current trunk+canopy already works acceptably) | Low |

### Keep hand-building (unchanged):
`build_house()` (still simple/cheap and already matches K70's style closely),
the character rig, the textured-box UV technique, all texture generators, all
lighting/camera/assembly code.

---

## 4. K70 Voxel V4 architecture (proposal only — NOT implemented)

```
1. GEOMETRY SOURCING layer  (NEW)
   tools/k70_scene_engine/blender/_k70_asset_import.py
   - Pulls pre-vetted, manually-downloaded CC0 GLB/OBJ/FBX files from a
     local cache: vendor/cc0_assets/{kenney,quaternius}/...
   - Pure bpy.ops.import_scene.gltf/obj/fbx calls -- fully scriptable,
     fully headless, no addon/GUI dependency at all.

2. MATERIAL RETEXTURE layer  (NEW)
   - After import, strip the pack's original materials.
   - Reassign K70's own pixel-art atlases via the EXISTING
     simple_textured_box()-style material assignment, OR apply a small
     new "flatten to K70 palette + hard-edge shading" pass.
   - This is the step that keeps the visual identity as "K70 original,"
     even though the underlying mesh geometry came from a CC0 pack --
     satisfies the project's own no-copied-assets intent, since Kenney/
     Quaternius geometry is generic/unbranded (not Minecraft-derived) and
     the surface appearance becomes 100% K70 texture.

3. CHARACTER layer  (UNCHANGED)
   _voxel_human_v3_script.py, gen_k70_skin.py, the rig, the animation
   functions -- exactly as they are today.

4. LIGHTING / CAMERA / ASSEMBLY layer  (UNCHANGED)
   lighting_presets.block_world_v31, camera-keyframe system, xfade/audio
   scripts in scripts/build_*.py.

5. CURATION + LICENSE MANIFEST gate  (NEW, one-time + per-addition)
   A manifest file (e.g. vendor/cc0_assets/MANIFEST.md) logging: asset
   name, source URL, license (CC0), date added -- so legal provenance is
   traceable for every borrowed geometry piece, the same discipline
   already used for the Poly Haven HDRI/furniture credits in V1/V2.

6. FALLBACK rule
   If a needed prop type isn't in the curated CC0 library, fall back to
   hand-building it in _k70_block_kit.py as today -- the hand-built system
   is supplemented, not deleted.
```

**Not implemented.** Awaiting approval of the repo/tool combination above
before any of this is integrated.

---

## Sources

- [MCprep](https://github.com/Moo-Ack-Productions/MCprep)
- [jMc2Obj](https://github.com/jmc2obj/j-mc-2-obj)
- [Mineways](https://github.com/erich666/Mineways)
- [VoxCity](https://github.com/kunifujiwara/VoxCity)
- [procedural_city_generation](https://github.com/josauder/procedural_city_generation)
- [Block-On](https://github.com/BrendanParmer/Block-On)
- [Mesh2Motion](https://github.com/Mesh2Motion/mesh2motion-app)
- [Kenney.nl](https://kenney.nl/)
- [Quaternius](https://quaternius.com/)
- [awesome-cc0 list](https://github.com/madjin/awesome-cc0)
