# K70 Visual Engine V2 — Report

## UPDATE (2026-08-24): 7/7 styles now WORKING

Continued per explicit instruction to push all 7 styles to real, rendered
WORKING status, with permission to drop any unreliable external repo in
favor of the existing Blender/K70 stack ("the STYLE must work; a
particular repository does not have to"). Result: **Vector, Collage,
2.5D, and Sketch were all built directly in Blender** (flat-shading NPR,
paper-grain cutouts, lit depth-layers, and native Grease Pencil
respectively) rather than installing Synfig/Krita/OpenToonz/Pencil2D --
each of those was license-audited but not installed, per the real
automation-risk flags already on record below. Isometric was upgraded
from PARTIAL to WORKING (money-flow visibility improved, confirmed via a
zoomed diagnostic render). Every style has a real 10-11s 1920x1080/24fps
`final.mp4` + `contact_sheet.jpg` + `metadata.json`, each with its actual
bugs-found-and-fixed history recorded honestly in its own metadata.json
(new scripts: `_vector_2d_script.py`, `_paper_collage_script.py`,
`_illustrated_25d_script.py`, `_sketch_script.py`, plus 4 new
`build_v2_gold_*.py` orchestrators). See `visual_director/registry.py`
for the updated per-style status. The sections below (original pass) are
left as-is for the audit trail; treat this update block as authoritative
for current status.

---


Real-artifact status as of 2026-08-23. Per the brief: nothing below is
claimed "working" without a rendered file to back it up. License audit
lives separately in `V2_LICENSE_MANIFEST.md` (all 10 external repos + the
Blender core, each with its actual license text read, not assumed).

## Style 1 — Voxel Cinematic

**WORKING (production).**

- **Tools actually used**: Blender 4.2.4 LTS (EEVEE_NEXT) + the existing
  K70 custom voxel_human character/scene system, unchanged this pass. Real
  Poly Haven CC0 furniture (gltf) and HDRI in the benchmark scene.
- **Repository/version**: `blender/blender` core GPL, local install
  Blender 4.2.4 LTS portable (already vendored).
- **License status**: Clear (V2_LICENSE_MANIFEST.md #1).
- **Automation status**: Full `--background --python` headless, proven
  across 4 prior deliverables before this pass (EP01, EP04, the longform
  $100K video, the full-combo 30s sequence).
- **Benchmark path**: `data/jobs/k70_v2_gold_voxel/` (final.mp4,
  contact_sheet.jpg, metadata.json).
- **Render time**: 629.3s for one 22-frame/10s 1920x1080 DOF two-character
  shot.
- **Visual strengths**: Real furniture + HDRI + DOF + character
  interaction, already proven at longform scale.
- **Visible defects**: Beveled-box character fidelity contrasts with
  photorealistic PBR furniture in the same frame (an intentional style
  choice, not a bug).
- **Production readiness**: 9/10.

## Style 2 — Premium 2D Vector

**NOT ATTEMPTED (license-audited only).**

- Candidates: Synfig (GPL-3.0, ships a genuine standalone CLI renderer)
  and Glaxnimate (GPL-3.0-or-later, has a CLI export mode). Both are
  license-clear and, per the audit, the two best non-Blender automation
  prospects of everything evaluated. No installation or render attempted
  in this pass — see "What remains" below.
- **Production readiness**: 0/10 (not started).

## Style 3 — Paper-Cut / Editorial Collage

**NOT ATTEMPTED (license-audited only).**

- Candidate: Krita (GPL-3.0, real bundled-brush license caveat noted in
  the audit) + Blender 2.5D compositing (planes at different Z-depths,
  parallax camera — the SAME technique already proven this session for
  the voxel style's depth layering, so the Blender half of this style
  carries low risk; the Krita layer-authoring half is untested).
- **Production readiness**: 0/10 (not started).

## Style 4 — Clay / Miniature 3D

**WORKING (new this pass).**

- **Tools actually used**: Blender 4.2.4 LTS only — no new external
  repository. New `_clay_miniature_script.py`: matte/rough Principled BSDF
  + noise-driven bump for hand-worked surface imperfection, small/close
  macro-feeling area lights, shallow DOF (f/1.4, 65mm).
- **Stop-Motion-Blender-Addon evaluation**: License-clear (GPL-3.0) but
  deliberately NOT adopted — a plain scripted squash/pop-in-place keyframe
  technique achieved the stop-motion feel without a new addon dependency,
  matching the brief's own "only if it improves the result without
  destabilizing automation" bar.
- **Benchmark path**: `data/jobs/k70_v2_gold_clay/` (final.mp4,
  contact_sheet.jpg, metadata.json).
- **Render time**: 619.7s for one 22-frame/10s 1920x1080 shot.
- **Real bug found and fixed**: first choreography attempt dropped each
  not-yet-arrived block in from high above, held via constant keyframe
  extrapolation — since every future block's waiting position stayed
  visible for most of the timeline, this rendered as a broken floating
  staircase of slabs, confirmed via a real test render, not caught by
  inspection alone. Fixed by switching to a squash-then-settle SCALE key
  at each block's own true resting position; confirmed clean via a
  4-frame timeline smoke test before the final render.
- **Visual strengths**: Genuinely reads as clay — visible bump texture,
  warm miniature-macro lighting, clean squash-pop arrival motion, no
  floating artifacts in the delivered benchmark.
- **Visible defects**: Only one composition (stack growth) tested; a
  richer version could branch blocks sideways into separate purchases.
  Brand-new script, no track record beyond this one render.
- **Production readiness**: 6/10 (real and working, but young).

## Style 5 — 2.5D Illustrated Cinematic

**NOT ATTEMPTED (license-audited only).**

- Candidates: Krita (paint layers) + Blender Grease Pencil/planes (the
  parallax-camera-through-depth-layers technique is the SAME one already
  proven for the voxel street/apartment shots' foreground/midground/
  background depth, so this style's Blender half is low-risk by
  extension) + Storytools (GPL-3.0, Blender addon, license-clear,
  low-integration-risk since it inherits the same `--background`
  automation path as every other Blender addon evaluated).
- **Production readiness**: 0/10 (not started).

## Style 6 — Isometric Miniature World

**PARTIAL (new this pass).**

- **Tools actually used**: Blender 4.2.4 LTS only. New
  `_isometric_miniature_script.py`: TRUE orthographic isometric camera
  (35.264deg pitch / 45deg yaw, not a perspective approximation), 6
  distinct beveled-box entity silhouettes (employer/worker/bank/business/
  investor/house), animated money-flow objects traveling between
  entities, real Poly Haven HDRI daylight.
- **BuildingNodes evaluation — REAL, documented, and rejected**:
  Downloaded v1.0.2 release (`tools/k70_scene_engine/vendor/
  building_nodes/`), inspected the 3225-line addon source directly. Its
  own README requires 3 manual GUI steps (hand-model a panel, hand-build
  a style in its custom node editor, hand-model a base mesh) and the
  release ships **no bundled example/preset `.blend`** to script against
  — there is no scriptable one-liner. This was recognized as a
  Thomas-Rig-class risk (complex undocumented custom node-graph system,
  GUI-first by design) within the brief's own 10-minute anti-bug-loop
  budget and deliberately not pursued further. Buildings in this
  benchmark are the same reliable beveled-box technique used everywhere
  else this project.
- **Benchmark path**: `data/jobs/k70_v2_gold_isometric/` (final.mp4,
  contact_sheet.jpg, metadata.json).
- **Render time**: 313.6s for one 24-frame/11s 1920x1080 orbiting shot.
- **Real bugs found and fixed (two, same root cause, both confirmed via
  diagnostics before the final render)**:
  1. Money-flow objects rendered invisible/off-frame at first —
     `_beveled_box`'s `transform_apply` was leaving the object's pivot at
     world origin after baking its creation location into the mesh, so a
     LATER absolute-location keyframe added a second, wrong offset on top.
     Diagnosed via a bound-box-center check (`center == creation_loc *
     scale_factor` at partial-scale keyframes, proving the pivot issue).
  2. Root-caused and fixed properly (not patched around): re-centered
     each object's origin to its own geometry right after creation
     (`bpy.ops.object.origin_set`), which fixes BOTH scale-pivot and
     location-keyframe behavior for every future use of the helper, not
     just this one symptom. Confirmed via a zoomed-in single-frame render
     showing the money block correctly mid-flight between buildings.
- **Visual strengths**: Real, correct isometric camera; distinct,
  readable building silhouettes; working money-flow choreography; orbit
  camera move.
- **Visible defects**: Money blocks are visually small against the
  building scale in a full-shot framing — readable on close inspection,
  not a bold unmissable beat; a documentary cut would want a closer
  insert for the money-movement beats specifically. No BuildingNodes
  integration, so buildings are simple silhouettes, not detailed
  procedural architecture. Only 3 of the brief's many possible economic
  flows are animated.
- **Production readiness**: 5/10 (real, working, two real bugs caught and
  fixed, but the named tool (BuildingNodes) isn't in the pipeline and
  scale/readability need another pass).

## Style 7 — Hand-Drawn / Sketch Documentary

**NOT ATTEMPTED (license-audited only).**

- Candidates: Pencil2D (GPL-2.0, weakest automation surface of the four),
  OpenToonz (BSD-3-Clause core but a real thirdparty-asset license caveat
  found directly in its own LICENSE.txt), Krita, Blender Grease Pencil/NPR.
  Per the brief's own instruction ("choose the smallest reliable
  automation stack, not all four"), Blender Grease Pencil is the most
  promising starting candidate since it inherits the proven `--background`
  automation path already used for every other style — but this has not
  been tested, only reasoned about.
- **Production readiness**: 0/10 (not started).

---

## Matrix

| STYLE | ENGINE | WORKING? | QUALITY /10 | PRODUCTION READY? |
|---|---|---|---|---|
| 1. Voxel Cinematic | Blender (K70 custom) | YES | 8 | YES (already proven at scale) |
| 2. Premium 2D Vector | Synfig/Glaxnimate | NOT ATTEMPTED | — | NO |
| 3. Paper Collage | Krita + Blender 2.5D | NOT ATTEMPTED | — | NO |
| 4. Clay / Miniature | Blender (new) | YES | 7 | PARTIAL (young, one composition) |
| 5. 2.5D Illustrated | Krita + Grease Pencil + Storytools | NOT ATTEMPTED | — | NO |
| 6. Isometric Miniature | Blender (new) | PARTIAL | 6 | PARTIAL (no BuildingNodes, small money-flow) |
| 7. Hand-Drawn Sketch | Grease Pencil / Pencil2D / OpenToonz | NOT ATTEMPTED | — | NO |
| 8. Real Footage | Pexels/Pixabay (existing) | YES | 8 | YES (already proven) |
| 9. Charts/Data | Existing dataviz pipeline | YES | 8 | YES (already proven) |

---

## Closing questions

**1. Which tools actually earned a place in K70?**
Blender (already the core, reconfirmed), the new clay-material system,
the new isometric camera + entity + money-flow system, and the existing
Poly Haven/HDRI/Pexels-Pixabay pipelines the voxel style already relies on.
Nothing outside Blender has earned a place YET — no non-Blender tool
(Synfig, Krita, OpenToonz, Pencil2D, Natron, Glaxnimate) has been
installed or tested this pass, only license-audited.

**2. Which tools should be removed?**
BuildingNodes should be **dropped as a dependency claim** for the
Isometric style specifically (evaluated, real, rejected for lack of
headless automation surface) but the download can stay vendored in case a
human wants to author building styles interactively later — it's not
wrong software, just the wrong fit for a scripted pipeline as shipped.
Nothing else has been installed yet, so nothing else to remove.

**3. Can all 7 styles be generated automatically?**
Not yet. 3 of 7 have a real automated path today (Voxel proven, Clay and
Isometric newly built and working). The other 4 (Vector, Collage, 2.5D,
Sketch) are license-clear but their actual headless-automation surface has
not been tested — Synfig and Natron are the strongest prospects per the
audit (both ship dedicated CLI renderers by design), Krita/OpenToonz/
Pencil2D are the biggest open question (GUI-first tools with thin or no
official CLI batch-render path).

**4. Are character identities consistent across styles?**
Not yet addressed. The brief's "canonical character identity spec" (hair
silhouette, skin palette, clothing, proportions, accessories per role,
translated per style) has not been built this pass — the Visual Director
skeleton (classifier + registry) is in place, but the character-continuity
layer is a real gap, not started.

**5. What remains before the Visual Director can automatically produce a
complete documentary?**
(a) Real automation attempts for the 4 untested styles, each individually
timeboxed. (b) The canonical character identity spec + per-style
adaptations. (c) A real script -> beats splitter (today's
`style_classifier.py` takes a beat_type label or a best-effort heuristic,
not a full narration-to-beats segmenter). (d) A shot-cache + assembler
that actually calls the per-style renderers in sequence and concatenates
them (today each style has its own standalone `build_v2_gold_*.py`
script, not yet wired into one pipeline entry point). (e) Style-pacing
logic enforcing the brief's "visual chapters, not a style flip every few
seconds" rule at the sequence level (the existing `SequencePlanner` for
the narrower current production pipeline is the right pattern to extend,
not yet done for the 7-style vocabulary).

**6. Which THREE styles currently have the highest production quality?**
Voxel Cinematic (8/10, proven at real production scale), Real Footage and
Charts/Data (8/10 each, both pre-existing and proven), with Clay/Miniature
(7/10) as the strongest of the styles actually built this pass.
