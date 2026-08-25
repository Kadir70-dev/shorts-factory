# K70 Local Character Animation Stack

Audit and benchmark date: 2026-08-25. This is an additive helper layer, not a
tenth visual mode. No existing visual director or mode registry is changed.

## Phase 1 audit

- Blender: vendored portable Blender **4.2.4 LTS**, already used through
  `blender/bpy_bridge.py` and background Python entry points.
- Rigify: bundled with this Blender and successfully enabled headlessly. It was
  not imposed on Voxel John.
- Voxel John: `blender/_voxel_human_v3_script.py` already builds 14 separate
  mesh pieces parented to Empty pivots. Existing idle, walk, point, sit, and
  sit-point functions directly keyframe those pivots. There is no skinning.
- Earlier voxel implementation: `blender/_voxel_human_script.py` has the same
  rigid Empty architecture plus idle/walk/point/sit functions.
- Normal humanoids: MB-Lab is frozen for production style reasons, but its
  working BVH walk retarget path remains in `_mblab_walk_script.py` and
  `mblab_animation.py`.
- Rigged GLB playback: `animated_character.py` and
  `_animated_character_script.py` already import and render embedded GLB
  actions.
- Clay and isometric modes currently animate props/camera with object
  keyframes; neither has a reusable humanoid skeleton.
- Asset import: `k70_asset_adapter.py` already provides deterministic CC0 GLB
  import, flat shading, crisp textures, pivot correction, and provenance.
- Missing before this task: common action taxonomy, semantic bone aliases,
  reusable retarget-plan cache, deterministic action sequencing, rigid-adapter
  validation, and shared isolated benchmarks.

## Mesh2Motion audit and installation

Official repositories installed unchanged:

- `vendor/mesh2motion-app` — MIT application code
- `vendor/mesh2motion-assets` — Blender source assets

The official documentation states that model input and export currently use
GLB/GLTF, the application runs locally with Node (the repository recommends
Node 24), and code is MIT while supplied art/rigs/animations are CC0:
https://github.com/Mesh2Motion/mesh2motion-app

The local machine has Node 24.18.0. `npm install` and the Vite production build
completed, producing `vendor/mesh2motion-app/dist/index.html`. The build audit
reported four upstream npm vulnerabilities (two moderate, two high); no
automatic `npm audit fix` was applied because that would modify upstream lock
resolution without review.

Mesh2Motion is useful as an offline authoring and CC0 motion source. It is not a
supported batch CLI. K70 normal production therefore does not drive its UI:
the adapter inventories its fixed GLB outputs, while Blender imports cached GLB
actions directly. Normal renders require neither Mesh2Motion server nor network.

Blender imported the human base GLB successfully and found **88 actions**,
including Idle A, folded-arm/talking/phone idles, Walk, Formal Walk, Jog,
Sprint, Sitting Enter/Idle/Talking/Exit, Interact, and Dance Simple.

## Implemented architecture

- `animation/catalog.py`: provenance-backed semantic motion catalog.
- `animation/retarget.py`: semantic aliases for root/hips/spine/chest/neck/head,
  bilateral arms/hands/legs/feet; proportion scale, FPS and forward-axis plan;
  content-addressed JSON cache.
- `animation/rigid_adapter.py`: maps semantic joints to John's Empty pivots and
  rejects vertex groups or Armature modifiers on rigid parts.
- `animation/director.py`: `get_motion`, `apply_motion`, and deterministic
  `sequence_actions` without an LLM.
- `animation/qa.py`: sample checks for ground penetration/floating, extreme
  rotations, and root discontinuities.
- `animation/mesh2motion_adapter.py`: local installation/status and fixed GLB
  location; no upstream modification.
- `data/assets/motions/motion_manifest.json`: 16 initial semantic actions with
  source action and license. The complete 88-action source pack is retained in
  the vendor checkout rather than duplicated.

Retarget-plan timing on an 18-joint map: first construction **3.6133 ms**;
100 cached lookups averaged **0.8022 ms**. Blender action application/render
timing is recorded per benchmark; the first low-resolution renders were about
295 s (A), 284 s (B), and 312 s (C), dominated by rendering and GLB import.

## Isolated benchmark evidence

Outputs live under `data/benchmarks/local_animation_stack/`.

### Test A — normal humanoid: idle → walk → turn → point

**FAIL quality gate.** The Mesh2Motion mannequin imports and all four action
segments execute, but visual inspection of the rerendered contact sheet shows
the final aiming action does not read clearly enough as a screen-point gesture.
The sequence is technically animated but not director-ready.

### Test B — Voxel John: idle → walk → turn → point

**PASS for rigid animation.** The walk, turn, and raised-arm point are visible.
All 14 mesh vertex hashes remain unchanged; no mesh has vertex groups or an
Armature modifier. Textured pieces remain solid and rotate around Empty pivots.

### Test C — normal humanoid: walk → sit → explain → stand

**FAIL quality gate.** All four real Mesh2Motion actions execute, but after a
corrective render with a visible chair, the source rest/root pose still does not
align the pelvis with the seat. It reads as crouching in front of a chair, not a
valid seated performance.

Representative contact sheets and the actual MP4 clips were generated for all
three tests. The sheets were inspected after the corrective rerender. Because A
and C fail visually, the full shared stack is **NOT READY**.

## Current limitations

1. Rest-pose/pelvis offsets need Blender-side bind-pose correction and foot IK;
   semantic name mapping alone is insufficient for production retargeting.
2. Mesh2Motion supplies broad game motions but K70-specific business gestures
   such as precise screen pointing, document handoff, typing, and handshakes
   still need verified CC0 clips or carefully authored reusable actions.
3. Automated QA does not yet measure planted-foot velocity, self-intersection,
   or chair/contact constraints from evaluated Blender world-space samples.

No K70 V5.x, nine-mode selection, Day 06, production video, Synfig, Krita,
Pencil2D, or reference-dataset code was modified by this task.
