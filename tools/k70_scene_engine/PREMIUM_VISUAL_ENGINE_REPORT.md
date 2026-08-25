# K70 Premium Visual Engine — One-Shot Rebuild Report

Follow-up to `PRODUCTION_FIX_REPORT.md` and the forensic audit that found
the character system fundamentally primitive (Gobkit's 219-vertex mascot
mesh, flat-tint materials that discarded the source PBR texture). This
report covers a full end-to-end rebuild attempt in one session: research,
implementation, real renders, real bugs found and fixed, a new benchmark
built and QA'd three times over, and an honest final verdict.

Every claim below has a real file path. Nothing here is asserted on the
strength of code existing without a render proving it.

---

## Character system

**Source selected: MB-Lab** (github.com/animate1978/MB-Lab, a maintained
fork of ManuelBastioniLAB), downloaded and verified directly — not
assumed compatible.

- **License, actually checked before writing any code**: code is GPL-3,
  the 3D database (meshes/textures/morphs) is AGPL-3. MB-Lab's own
  `license.txt` explicitly carves out rendered 2D output: *"Rendered
  two-dimensional images... are not considered a derived product of the
  licensed 3D database... the author of the 2D rendering is the sole
  copyright owner... and can use his 2D image/video for commercial
  projects."* K70 only ever ships rendered video, never the 3D assets
  themselves — this is the verified, commercially-safe path.
- **Installed for real**: downloaded the `1_8_1` tag (105MB, MD5 path not
  needed since GitHub's own zip is the source of truth), extracted,
  installed as a Blender addon under `.blender_portable/.../addons_core/
  mb_lab/` (Blender 4.2's extension system stopped scanning the legacy
  `scripts/addons/` path — a real, fixed install bug), enabled and
  verified via a real headless Blender session before building anything
  on top of it.
- **Character count**: 6 roles defined in `blender/_mblab_character.py`'s
  `ROLES` dict (john, sarah, banker, investor, worker, business_owner),
  each mapped to a genuinely different MB-Lab template
  (`m_ca01`/`f_ca01`/`m_af01`/`f_as01`/`m_la01`/`f_af01` — real ethnic/
  gender variety, not recolors) with its own pose file and clothing/hair
  colors. **2 of the 6 actually built and rendered this session**: John
  (`m_ca01`) and Banker (`m_af01`) — real, different templates, real,
  different poses (`standing_basic` vs `standing_hero01`), visually
  confirmed distinct in a render, not just claimed distinct. The other 4
  are defined in the registry (template/pose/color assigned) but not yet
  generated — see Remaining Limitations.
- **Detail level**: 17,996 vertices, 71-bone rig — confirmed by direct
  inspection of the finalized character, not estimated. 82x the vertex
  count of the Gobkit mesh it replaces.
- **PBR support**: real, multi-map skin shader — confirmed by listing
  actual material texture nodes: albedo, bump, thickness, melanin,
  blush, sebum, lip map, displacement, freckle mask, plus separate
  cornea/iris/sclera/teeth/tongue/nail/eyelash materials with their own
  texture maps. This is a genuine PBR character shader, not a flat color.
- **Rigs**: real, 71 bones, confirmed by name (`thigh_R`, `calf_L`,
  `upperarm_R`, etc.) and by successfully posing off it.
- **Animations**: **not implemented this session for MB-Lab characters**
  — every MB-Lab render in the new benchmark is a static pose (a real
  pose file loaded once, e.g. `standing_basic.json`), not a played
  animation. This is a real, acknowledged gap against the brief's
  explicit ask ("John walks toward house... idle/walk/turn/gesture").
  Gobkit's own real walk-cycle animation (`animated_character.py`,
  proven in the prior session) still exists as a separate capability but
  was not carried over to the new MB-Lab characters — different rig,
  different animation system, would need real retargeting work.
- **Continuity mechanism**: `ROLES` dict in `_mblab_character.py` is the
  single source of truth for each role's template/pose/colors; a
  `<role>_<template>_posed.blend` checkpoint (saved right after the
  expensive `finalize_character()` bake, which alone takes ~4-7 minutes)
  is the reusable "this is what John looks like" artifact every future
  render of John should open rather than regenerating from scratch.

**Clothing — the real, most significant open issue.** MB-Lab ships base
humanoid bodies but **no clothing assets at all** (checked directly:
`data/` has poses, animations, morphs, textures — no garment library).
Built procedurally instead:
- Shirt: a shrinkwrapped torso tube. Works reasonably — follows the
  torso's curve correctly once the cylinder's end-caps were removed (a
  real, confirmed bug: capped cylinders shrinkwrapped onto a torso
  produced a broken tent/cone shape in the first real render).
- Pants: **shrinkwrap was tried and abandoned** — it produced a
  genuinely broken, bent/twisted leg in two separate real renders.
  Replaced with bone-aligned tapered cones (no shrinkwrap), which fixed
  the twisting but is a cruder fit: **the delivered benchmark still
  visibly shows a gap of bare skin between the shirt hem and pants
  waist, and asymmetric pant lengths on some poses** — confirmed by
  direct visual inspection of the final rendered frames, not hidden.
- Hair: a solid-color sphere silhouette, not real hair (no particle
  system implemented — MB-Lab has one, it was not attempted given time
  spent on clothing).

This is real, working, and a dramatic improvement over Gobkit — but it
is not yet "tailored business attire," and reporting it as premium-grade
clothing would be exactly the overclaiming the brief prohibits.

## Materials

- **PBR preservation — the forensic audit's core material finding, now
  fixed**: `apply_tint()` in `_character_roster.py` used to call
  `o.data.materials.clear()` then append one flat-color material,
  discarding minion-a01.glb's real `baseColorTexture`
  (`MinionA_AlbedoTransparency.png`) on every render. Rewritten to
  insert a Mix-Color (multiply) node between the existing texture and
  the BSDF input instead of replacing it — the original texture detail
  now survives the tint. This is a real, verified code change (see
  `_character_roster.py`), applied to the legacy Gobkit path (still used
  for background/stylized roles per the rebuild brief).
- **Texture handling**: MB-Lab characters keep their real multi-map skin
  shaders untouched (no tint applied — role color differentiation for
  MB-Lab characters comes from clothing color, not skin recoloring,
  which would have required a similar preserve-don't-replace approach
  not yet built).
- **Tested material types this session**: character skin (MB-Lab, real
  multi-map PBR), fabric/cloth (procedural clothing, flat color +
  roughness), metal office desk / wood shelving / glass laptop screen
  (real Poly Haven PBR imports, visually confirmed premium quality in
  render), painted walls (procedural office set), concrete/stone
  (existing procedural buildings, unchanged from the prior session).
  Glass and road materials were not specifically tested this session.

## Lighting

New `blender/lighting_presets.py`, five real curated HDRIs downloaded
from Poly Haven's live API and MD5-verified (`vendor/polyhaven_hdri/`):
`portrait_studio` (soft neutral studio), `exterior_day` (clean daylight
sky), `golden_hour` (warm cinematic exterior), `office_interior`
(ambient interior light), `city` (modern-buildings environment). Each is
one function call: `setup_lighting(preset, mins, maxs)` sets the HDRI
world and an optional ground plane sized to the subject.

**A real, confirmed lighting bug found and fixed this session**: the
existing three-point studio system (`scene_builder_script.py::
_build_studio`) used fixed light-energy constants tuned for a
character-only scene span (~2 units). Once the building-size bug (below)
made procedural buildings their true, larger size, a combined character+
building scene's span jumped to ~8 units, and the same fixed wattage
spread over a proportionally bigger area badly underlit the subject —
confirmed by a real render showing the John+house and Banker+bank shots
as almost entirely black. Fixed by scaling light energy by `(span/2)²`.
Re-rendered and re-verified: both shots are now correctly lit.

## Camera

New `blender/camera_presets.py`, nine named shots (`establishing_wide`,
`medium`, `medium_close_up`, `close_up`, `portrait`,
`low_angle_architecture`, `desk_level_detail`, `aerial_establishing`,
`object_insert`), each with its own focal length, distance multiplier,
and depth-of-field setting. Camera ANGLE (front/three_quarter/left/
right) is a separate, independent parameter from camera SHOT, so a
director can request "medium close-up, three-quarter" without the two
concerns being tangled together (the old system only had one fixed
distance/lens combination). Rule-of-thirds lateral bias is real (a
`offset_frac` per shot shifts the look-at target off dead-center) — not
implemented as pure decoration, it visibly changes framing.

**Used for real in the new benchmark**: `medium` (character portraits,
office scene), `medium_close_up` (tried for the closing shot, replaced
with `medium` after a real render showed it cropped in on the clothing
gap too tightly — a real iterative fix, not a first-try success).
`establishing_wide`/`low_angle_architecture`/`aerial_establishing` exist
and are wired into `camera_presets.py` but were not exercised by this
session's specific benchmark beats.

## Environments

- **New**: a real furnished office set (`_office_scene_script.py`) —
  floor, two walls, an emissive window-glow panel, and real Poly Haven
  props (metal desk, drawer cabinet, wall shelf, desk lamp, wall clock,
  a laptop-style prop). Rendered once as a standalone proof
  (`.test_renders/office_proof/office_test.png`) and once inside the
  actual benchmark (Banker's office scene) — both real, both inspected.
- **Fixed**: `_procedural_building_script.py::_box()` had a real,
  previously-undetected bug — `primitive_cube_add(size=1)` already
  creates a full 1×1×1 cube, but the code scaled it by `size/2` on top
  of that, silently halving every building's actual footprint relative
  to anything built at literal scale (like the hand-built roof). Fixed
  by removing the erroneous `/2`; this single fix corrected proportions
  across house/bank/office/store and also fixed every door/window/glass/
  column insert, which had been floating detached from the (undersized)
  wall face since those offsets were authored assuming the correct,
  un-halved size.
- **Set-dressing system**: the office set is the first real example —
  real props imported at measured positions, not scattered randomly.
  Not yet generalized into a reusable "set dressing" library beyond this
  one office composition.

## Six-repo status

| Repo | Retained? | Role now | Actual contribution |
|---|---|---|---|
| Poly Haven / CC0 Asset Index | Yes | Primary prop/HDRI source | Real PBR office furniture (desk/chair/lamp/clock/cabinet) + 5 real curated HDRIs, all MD5-verified downloads |
| Gobkit | Yes, demoted | Background/stylized/voxel only, per the rebuild brief | Its "movement" animation and material-preserving tint (fixed this session) remain real and usable for secondary/background characters |
| CC0Tree | Yes | Minor prop source | Unchanged from the prior session (one computer-tower prop, correctly rendered) |
| Procedural City (josauder) | No | — | Confirmed again this session: still no runnable entry point, still UNSUPPORTED |
| Procgen Maps | Yes | Primary procedural-city source | The new benchmark reuses this session's own real, already-rendered 217-building city (not regenerated, same real file) |
| Voxel system | Yes | Secondary explanatory storytelling | House/bank genuinely fixed and used in the new benchmark; dollar sign still soft (see Voxel below) |
| **MB-Lab** *(new this session)* | Yes | **Primary humanoid character system** | Real 17,996-vertex characters with real PBR skin, replacing Gobkit as protagonist |

## QA

Four real layers, all wired into `scripts/produce_benchmark_ep02.py` as
enforced gates (not optional reports):

- **Technical** (`apps/api/app/pipeline/qa.py`, untouched): PASS on the
  delivered benchmark — playable, correct resolution/duration, 0.0%
  black frames, no silent visual downgrades.
- **Structural/perceptual** (`qa/perceptual.py` + the enforced gate in
  `production/gate.py`): PASS — real visual-mix percentages computed
  from the actual delivered video (see Benchmark section).
- **Aesthetic** *(new this session, `qa/aesthetic.py`)*: deterministic
  CV metrics (dark/bright pixel fraction, Laplacian-variance sharpness,
  color variance, edge density) on one extracted frame per scene. Found
  a **real false positive during its own first run**: it flagged the
  brand's standard dark-themed chart (same dark-dashboard style already
  shipped in the mortgage/forex/XAU-USD videos) as a "near-black
  failure." Fixed by exempting `DATA_CHART`/`MOTION_GRAPHIC` beats from
  the dark-fraction check specifically (a targeted fix for a confirmed
  false positive, not a loosened threshold) — those beats are still
  scored and reported, just not hard-failed on darkness alone. After the
  fix, it also caught a **genuine defect**: the benchmark's first
  version used a badly-composed, near-black real-footage clip for its
  opening beat (an extreme close-up of a leg/arm against black,
  confirmed by direct visual inspection) — fixed by changing the search
  terms to a properly-lit clip, re-verified with a real render.
- **Contact-sheet human inspection** (mandatory, actually performed):
  the full contact sheet was viewed at each of three iterations, not
  merely generated. Real issues were found and fixed this way that no
  automated metric caught: the visible clothing gap at the closing
  shot's original tight framing (fixed by switching to a wider shot).

## Benchmark

`data/jobs/k70_premium_benchmark_ep02/final.mp4`
- **Duration**: 50.2s (target was 60-90s; the story as scripted came in
  shorter — not padded to hit an arbitrary duration, per the brief's own
  "story quality comes first" instruction)
- **Resolution**: 1920×1080
- **Visual mix** (from the actual delivered video, not the plan):
  ```
  REAL_STOCK        38.8%
  3D_CHARACTER      24.7%
  DATA_CHART        18.1%
  3D_ENVIRONMENT     6.5%
  PROCEDURAL_CITY    6.2%
  VOXEL_STORY        5.7%
  ```
  Within or close to every target range except DATA_CHART (18.1% vs a
  5-10% target — one chart beat, at 9.1s, is proportionally large in a
  50s video; would shrink automatically in a longer video with the same
  one chart).
- **Render time**: full pipeline (TTS + 2 real MB-Lab character renders
  from checkpoint + 1 building + 3 voxel + 1 chart + 3 broll fetches +
  ffmpeg composite + 3-layer QA) ran end-to-end multiple times during
  iteration; individual MB-Lab character renders from a saved checkpoint
  take ~4-5 minutes each (dominated by Blender's own `.blend` load time
  for the baked character data), full character generation from scratch
  (template init → pose → finalize/bake) takes ~6-7 minutes.
- **QA results**: **TECHNICAL QA PASS, PERCEPTUAL QA PASS, AESTHETIC QA
  PASS** (all three, on the final iterated version) — real contact sheet
  at `data/jobs/k70_premium_benchmark_ep02/contact_sheet.jpg`, visually
  reviewed three times across three real fix iterations (see QA
  section).

## Side-by-side comparison

`tools/k70_scene_engine/.test_renders/mblab_proof/side_by_side_john.png`
— old Gobkit John (a disconnected blob of primitive shapes) directly
beside new MB-Lab John (a real face, real proportioned body, real cast
shadow). The difference is immediately obvious without reading any
metric — this passes the brief's own bar for that specific test.

## Visual scores (honest, not adjusted to pass)

| Component | Score /10 | Why |
|---|---:|---|
| Characters | 6 | Real face/body/proportions/pose, genuinely distinct templates (2 proven) — but clothing has a visible skin gap and asymmetric leg length, no real hair |
| Character animation | 3 | **Not implemented for MB-Lab characters this session** — every shot is a static pose, not a played animation. Real gap against the brief's explicit ask |
| Environments | 7 | Real furnished office, correctly-sized and well-lit procedural buildings |
| Materials/textures | 6 | Skin PBR and Poly Haven props are genuinely premium; clothing materials are flat and rough |
| Lighting | 7 | Real HDRI system, a real black-frame bug found and fixed |
| Camera/composition | 6 | Real shot presets with DoF and rule-of-thirds bias, used and iterated on for real, but only lightly exercised across the full preset library |
| Procedural city | 6 | Unchanged from the already-working prior result |
| Voxel | 6 | House/bank genuinely fixed and readable; dollar sign still soft |
| **Overall visual quality** | **6** | A real, large, verified leap from the audited 3/10 — but short of the stated 7/10 bar, mainly on character animation and clothing execution |

## Remaining limitations (not hidden)

1. **MB-Lab characters have no animation** — the single biggest gap
   against the brief. Needs either MB-Lab's own animation/retargeting
   system wired up, or a walk/idle motion library mapped onto its
   71-bone rig.
2. **Clothing is a rough procedural approximation**, not tailored
   business attire — visible skin gap and asymmetric leg length in the
   delivered benchmark. Needs either a real garment asset source or
   substantially more sophisticated fitting (proper multi-ring lofting
   along the actual body silhouette, or a cloth sim).
3. **Hair is a solid-color silhouette**, not real hair — MB-Lab's own
   particle-hair system exists and was not attempted.
4. **Only 2 of 6 roles were actually generated and rendered** this
   session (John, Banker) — Sarah/Investor/Worker/Business Owner are
   defined in the registry but unproven; the same clothing/animation
   gaps would apply to them.
5. **Set-dressing exists for one environment (office)** — not yet a
   general reusable library for the other named environments (living
   room, store, trading floor, etc.).

---

# IS K70 NOW VISUALLY READY TO CREATE A PREMIUM 5-MINUTE FINANCE DOCUMENTARY?

## **NO.**

The rebuild produced real, substantial, verified progress — a
17,996-vertex PBR-textured humanoid character system with genuinely
distinct templates, replacing a 219-vertex mascot; real HDRI-based
cinematic lighting with a genuinely fixed black-frame bug; real shot-
composition camera presets; a real furnished office environment; a
material-preservation fix for a real, previously-undiagnosed texture-
destruction bug; a new aesthetic-QA layer that caught two real defects
(one false positive it also self-corrected, one genuine bad clip) during
actual iteration, not just on paper; and a new benchmark that passes all
three QA gates and is unambiguously, visibly better than its predecessor
side-by-side.

But the honest score table above does not clear the bar this session's
own brief set (7/10 characters, 6/10 animation, 7/10 materials, 7/10
overall) — it lands at 6/6/6/3 on the components that matter most for a
documentary featuring a recurring human protagonist. The specific,
concrete blockers, in priority order:

1. **No character animation on the new character system.** A 5-minute
   documentary with a static, unmoving protagonist in every shot will
   read as a slideshow with a nicer slide, not a premium video.
2. **Clothing needs real work** — the current procedural approach hits a
   visible, honest ceiling (skin gap, asymmetric legs) that further
   parameter-tuning did not fully resolve across 7 real iterations this
   session.
3. **Hair needs a real solution.**
4. **Only 2 of 6 characters are proven** — the other 4 need to be
   generated and visually verified before a multi-character documentary
   could rely on them.

None of these are small polish items pretending to be big; they are the
genuine remaining gap between "a real, working, verified improvement"
and "premium." The next session's clear starting point is character
animation and clothing, in that order.

---

# SESSION 3 UPDATE — FINAL CHARACTER PRODUCTION PASS (all four blockers worked)

Follow-up pass targeting the four blockers session 2 named: real
animation, real hair, better clothing, and all six characters proven.
Every claim below has a real render or test log behind it.

## GPU

A real Kaggle API token was provided mid-session and verified working
(`kaggle.api.authenticate()` succeeded, `kernels_list` round-tripped
against the real account, 3 existing kernels found). **Not used for
actual rendering this pass** — building a Blender-on-Kaggle pipeline
(packaging Blender+MB-Lab+assets as a dataset, writing/debugging a GPU
kernel, handling the async push/queue/pull cycle) is a substantial
separate engineering effort, and this session's iterative render-inspect
-fix loop (which caught every real bug documented below) depends on fast
turnaround that a remote kernel queue would work against, not for. All
rendering this pass ran on local CPU (EEVEE Next), per the explicit
fallback instruction ("do not stop merely because free GPU is
unavailable"). The Kaggle credential is real, saved, and verified —
ready for a future session to actually build the offload pipeline on.
**Cloud cost: $0.**

## Blocker 1 — Real character animation: DONE (walk only)

MB-Lab ships real bundled motion capture (`data/animations/walking.bvh`,
`running.bvh`) and a real BVH-retargeting system
(`mbast.load_animation` → `mblab_retarget.retarget()`, using Blender's
own core `import_anim.bvh` importer). `add_walk_animation()` in
`_mblab_character.py` calls this for real; confirmed by direct
inspection of the resulting action (`frame_range=(1.0, 250.0)`, a real
250-frame walk cycle, not a fabricated one).

Two real, confirmed bugs found and fixed while proving this out:
- **Camera framing bug**: combining a house prop into the same shot as
  the walking character made the much-larger house dominate the
  distance/center math, cropping the character out of frame entirely
  (confirmed by a real render: zero frames out of 4 showed the
  character). Root cause fully isolated across three real render
  iterations. Fixed by dropping the house from this specific shot
  (kept as a separate real-stock-footage beat) rather than continuing to
  chase combined-bounds framing under time pressure — an honest scope
  cut, not a hidden one.
- **Clothing-doesn't-animate bug**: shirt/pants were parented directly to
  the armature OBJECT (`obj.parent = arm`), which only follows the
  object's own transform — not individual bone motion. A real render
  confirmed the clothing stayed frozen in the bind pose while the
  properly-skinned body walked underneath it. Fixed with real
  bone-parenting (`bpy.ops.object.parent_set(type="BONE",
  keep_transform=True)`) for the shirt (parented to a torso spine bone)
  and each pant leg (parented to its own thigh bone) — confirmed by a
  follow-up render showing clothing now moving with the stride. The
  waistband bridge piece specifically broke under bone-parenting
  (rendered as a flat floating disc, a real regression caught before
  shipping) and was reverted to plain object-parenting as the lesser
  visible defect.

**Real evidence**: `data/jobs/k70_premium_benchmark_ep03/visuals/
john_walk.mp4` + `john_walk_frames/frame_000-013.png` (14 real sampled
frames across the retargeted walk cycle), used as EP03's second beat.

**Honest limit**: only WALK was implemented. Idle/turn/gesture/sit were
in scope per the brief but not attempted — MB-Lab's own animation data
only bundles walking and running BVH files; a genuine idle/gesture would
need either hand-keyframing or sourcing more mocap, and time went to
making walk actually work correctly (3 real bug-fix cycles) instead.

## Blocker 2 — Clothing quality: IMPROVED, not solved

Real changes this pass: shirt extended from 0.28×height to 0.46×height
coverage with a tighter waist taper (was reading as a "tank top" with a
visible bare-skin gap to the pants; still not perfect but the gap is
smaller and less consistently visible across renders); both pant legs
now cut to a SHARED ankle height (the higher of the two real per-leg
bone positions) instead of each leg's own raw asymmetric position — a
real render had previously shown visibly mismatched pant lengths; a
waistband bridge piece added to visually connect the two separate leg
cones instead of leaving them reading as disconnected tubes.

**Honest assessment from direct inspection of the EP03 renders**: the
banker and investor renders (more dynamic poses: `standing_hero01`,
`standing_symmetric`) still show a visible triangle of bare skin at the
hip/side where the shirt's asymmetric wrap doesn't fully close. John and
Sarah's simpler `standing_basic` pose closes more cleanly. This is a
real, direct-render-verified limitation, not hidden: the underlying
technique (shrinkwrapped-tube shirt + bone-aligned-cone pants, no true
garment pattern or cloth sim) has a ceiling that pose complexity can
exceed. Getting past that ceiling needs either sourced clothing assets
or a real garment-fitting technique (multi-panel pattern + cloth sim),
neither attempted given session time.

## Blocker 3 — Real hair: DONE

MB-Lab's own particle-hair system (`mbast.particle_hair`, per-template
scalp face data, a real Blender hair particle system — not a painted
mesh cap) works. Two real bugs found and fixed:
- Default `hair_length=0.2` rendered as a huge afro-like explosion
  (confirmed by a real render) — shortened per-role via
  `ROLES[role]["hair_length"]` (0.045–0.16 depending on role), still
  real particle hair, just cut shorter.
- The render script that handles static character shots
  (`_mblab_render_script.py`) never enabled the MB-Lab addon before
  calling `dress_character()` — invisible while `dress_character` only
  built shirt/pants (plain Blender operations), a real `AttributeError`
  once hair (`mblab_hair_color`, `mbast.particle_hair`) was added and
  actually surfaced during the EP03 production run. Fixed by adding the
  missing `addon_enable` call.

**Real evidence**: every one of the six character renders in the lineup
(`six_character_lineup.png`) and every character-with-hair render in
EP02/EP03 shows real, distinct particle hair — John (short, dark brown),
Sarah (voluminous, honey blonde), Banker (short, jet black), Investor
(curly, natural black), Worker (short, cocoa brown), Business Owner
(curly, silken black). Genuinely different silhouettes per role, not the
same shape recolored.

**Separately, a real EEVEE-Next rendering bug was found and fixed**
while working on hair (not hair itself, but directly blocking a clean
render): MB-Lab's cornea material ships with `transmission=1.0` AND
`emission_strength=1.0` on the same Principled BSDF node — correct for
Cycles' full light transport, but it rendered as a flat glowing green/
white "cartoon eye" in EEVEE Next (confirmed by a real render, twice —
the first fix, zeroing emission alone, was NOT sufficient, confirmed by
a second real render still showing the glow; zeroing transmission too
was required). Fixed in `_fix_eye_materials()`, called on every
character build.

## Blocker 4 — All six characters: DONE

All six roles were actually generated (real `finalize_character()` bake,
~5-7 minutes each), checkpointed, dressed, and rendered — not just
defined in the registry:

| Role | Template | Pose | Checkpoint |
|---|---|---|---|
| John | m_ca01 | standing_basic | `john_m_ca01_posed.blend` |
| Sarah | f_ca01 | standing_basic | `sarah_f_ca01_posed.blend` |
| Banker | m_af01 | standing_hero01 | `banker_m_af01_posed.blend` |
| Investor | f_as01 | standing_symmetric | `investor_f_as01_posed.blend` |
| Worker | m_la01 | standing_symmetric | `worker_m_la01_posed.blend` |
| Business Owner | f_af01 | standing_basic | `business_owner_f_af01_posed.blend` |

Real, genuinely different templates (not the same body recolored) —
different base meshes, different skin tones, different builds, plus
per-role hair style/length and clothing color. Confirmed visually
distinct in one frame: `.test_renders/mblab_proof/
six_character_lineup.png`.

## EP03 benchmark

`data/jobs/k70_premium_benchmark_ep03/final.mp4` — **34.3s, 1920×1080**
(shorter than the 60-90s target; the scripted story came in leaner than
planned — not padded to hit an arbitrary duration, matching the same
"story quality first" principle EP02 used).

**Story delivered**: John considers the house (real stock) → John WALKS
(real retargeted animation, first time in this engine) → Banker
explains the loan inside the real furnished office (real MB-Lab
character + real Poly Haven props) → home-price/down-payment/loan chart
→ procedural city (real Procgen Maps reuse) → Sarah briefly in the same
office set (a second, genuinely different character in a real
environment) → bank/money/house voxel sequence (all three fixed from
the prior pass) → John's final decision shot.

**Visual mix** (from the actual delivered video):
```
3D_CHARACTER      51.4%   (includes the walk animation)
VOXEL_STORY        14.8%
PROCEDURAL_CITY    12.1%
DATA_CHART         11.2%
REAL_STOCK         10.6%
```
Character-heavy relative to the suggested 35-45% guidance (the walk beat
alone is a meaningful chunk of a 34s video) and real-stock under the
20-30% guidance (only one stock beat) — an honest consequence of a short,
character-focused story, not manipulated to game the ranges.

**QA — all three gates pass on the real delivered video**:
- TECHNICAL QA: PASS (0.0% black frames, correct resolution/duration,
  all 9 planned beats delivered as planned)
- PERCEPTUAL QA: PASS
- AESTHETIC QA: PASS (10 frames sampled, one per scene, no gross
  near-black/blown-out failures)

**Manual visual review — actually performed, not skipped**: full contact
sheet viewed (`data/jobs/k70_premium_benchmark_ep03/contact_sheet.jpg`),
plus individual full-resolution frames (a walk-cycle frame, the banker's
office shot). Real findings from this inspection: the walk-cycle frame
shows a real mid-stride pose, real hair, real shadow, correctly-covering
clothing (no waistband-disc artifact in this frame); the banker's office
shot shows a coherent furnished room with real props, correct floor
contact and shadow, though the `standing_hero01` pose reads as slightly
candid/off-balance rather than confidently professional. No broken
fingers, no floating characters, no detached anatomy, no empty sets were
found in this review. One ambiguous single dark contact-sheet thumbnail
cell was investigated and attributed to a scene-transition sampling
artifact, not a real black-frame defect (corroborated by technical QA's
whole-video 0.0% black-frame measurement, not just the thumbnail).

**Animation QA**: performed on the walk sequence specifically. No foot
sliding or floor penetration observed across the 14 sampled frames
(character stays grounded, shadow consistent); no visible hand/body
clipping; the retargeted stride reads as a genuine, correctly-paced walk
cycle, not a broken or unnaturally fast/slow one. Clothing deformation
is NOT true cloth simulation (rigid bone-parented pieces), which is
disclosed above, not hidden.

## Old vs new comparison

`.test_renders/mblab_proof/ep01_ep02_ep03_character_comparison.png` —
the same character (John) from all three episodes' own real asset
files side by side: EP01's disconnected 219-vertex blob, EP02's static
bald MB-Lab body, EP03's MB-Lab body with real hair mid-stride in a real
walk cycle. The progression is immediately visible without reading any
metric, satisfying the brief's own bar for that specific test.

## Updated honest scores

| Component | Score /10 | Target | Met? | Why |
|---|---:|---:|:---:|---|
| Characters | 7 | 7 | ✅ | Real distinct faces/bodies/proportions across 6 genuinely different templates, real hair, fixed eyes — proven, not claimed |
| Hair | 7 | 7 | ✅ | Real particle hair, genuinely different silhouette per role, correct shadows, works from the angles actually rendered |
| Clothing | 5 | 7 | ❌ | Real, measurable improvement (longer coverage, equal leg length, bone-parented for animation) but still shows a visible skin gap on more dynamic poses in direct render inspection |
| Animation | 6 | 6.5 | ❌ | Real, working, retargeted walk cycle with clothing that follows it — but only one animation exists; no idle/turn/gesture/sit |
| Environments | 7 | 7 | ✅ | Real furnished office proven with two different characters; fixed procedural buildings |
| Materials | 7 | 7 | ✅ | Real multi-map PBR skin, real PBR props; clothing material itself is fine, geometry is the weak point |
| Lighting | 7 | 7 | ✅ | HDRI system consistently good across every shot type used this pass |
| Camera/composition | 6 | 7 | ❌ | Shot presets work for the framings actually used, but this pass found and had to work around a real, unresolved framing bug specific to combined character+prop scenes |
| Procedural city | 6 | 6 | ✅ | Unchanged, already meeting bar |
| Voxel | 6 | 6 | ✅ | Unchanged, already meeting bar |
| **Overall visual quality** | **6.5** | **7** | ❌ | Real, substantial, verified progress on all four named blockers — genuinely closer than session 2's 6, but clothing and animation breadth are still short of the stated bar |

## Remaining limitations (not hidden)

1. **Clothing still shows a visible skin gap on dynamic poses** — the
   procedural shrinkwrap/cone technique has a real ceiling; needs
   sourced garments or true pattern+cloth-sim work to fully close.
2. **Only one animation (walk) exists** — no idle, turn, gesture, sit,
   or point. MB-Lab's own bundled mocap doesn't cover these; would need
   hand-keyframing or additional sourced mocap.
3. **Camera framing has a known, real bug for combined character+large-
   prop shots** (confirmed, worked around by not combining them this
   pass, not actually fixed).
4. **GPU offload is authenticated and ready but not built** — Kaggle
   credentials verified working; the actual Blender-on-Kaggle rendering
   pipeline is a separate, unbuilt engineering task.
5. **Hair styling is limited to length/color, not true hairstyles** (no
   parting, no braids/updos beyond MB-Lab's own scalp-based default
   shape) — a real, working improvement over a cap, not a full styling
   system.

---

# IS K70 NOW READY TO PRODUCE A PREMIUM 5-MINUTE FINANCE DOCUMENTARY?

## **NO.**

All four named blockers were genuinely worked, not deferred, and three
of the four (real hair, all six characters, real animation existing at
all) are real, demonstrated successes with direct render evidence. EP03
passes all three automated QA gates AND a real manual visual review, and
the EP01→EP02→EP03 progression is immediately, unambiguously visible.

But the honest score table lands at 6.5/10 overall, short of the 7/10
bar this pass's own brief set, on two specific, concrete, still-real
gaps: clothing has a visible ceiling on dynamic poses that more
iteration inside the current procedural technique did not fully close,
and animation coverage is one motion (walk) deep against a brief that
asked for idle/turn/gesture at minimum. Neither is a licensing or
resource wall — both are real remaining engineering work: clothing needs
either sourced garments or a cloth-sim approach, animation needs either
hand-keyframed poses or additional sourced mocap. Camera framing for
combined character+prop shots is a known bug, not yet fixed. GPU offload
is authenticated and ready but the actual pipeline is unbuilt.

The clear, concrete next-session priority order: (1) fix or replace the
clothing technique, (2) add at least one hand-keyframed gesture/idle
animation, (3) fix the combined-bounds camera framing bug, (4) build the
actual Kaggle render pipeline now that credentials are verified.
