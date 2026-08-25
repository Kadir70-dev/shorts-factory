# K70 Voxel V2 -- Character System Comparison

Scored /10. Tested under real constraints: must run fully headless
(`blender --background --python`, no interactive clicks), must not
carry commercial-use licensing risk, must not require hours of further
debugging.

| Criterion | K70 Custom Voxel (current) | Thomas Rig Legacy | Ice Cube |
|---|---|---|---|
| Character appearance | 5 | 8 (real eye/eyebrow/hair texture detail, confirmed by render) | untested |
| Animation | 6 (idle/walk/point proven, object-parented keyframes, no armature) | unscored -- has IK/FK, facial rig, but not animated in this test | untested |
| Expressions | 2 (none) | unscored -- has a dedicated facial rig (mouth/eyes/eyebrows) per its docs | untested |
| Customization | 5 (color/hair-shape per role, code-level only) | unscored -- has an armor/skin system, but skin-download path pulls from Mojang's API (avoid) | untested |
| Render quality | 5 (flat beveled boxes, clean but simple) | 8 (real materials/texture read in the one render obtained) | untested |
| Reliability | 6 (proven: it's rendering the actual longform video right now) | 5 -- REAL blocker found: bundled rig .blend was saved with Blender 4.5.88; our local install is 4.2.4. Mesh-build operator worked fine, but this version gap is a legitimate compatibility risk for a stable pipeline. | untested |
| Performance | 6 (12-14 frame clips, ~2-4 min each locally) | 6 (one still frame render took ~1m25s -- comparable order of magnitude, single data point only) | untested |
| Automation difficulty | 9 (built from scratch specifically for `--background`) | 7 -- confirmed automatable: open file -> enable addon -> `bpy.ops.thomasriglegacy.appendbasemesh()` -> render, all worked with zero interactive UI, including under a real headless run. Real risk: an internal Blender extension-cache bug threw a traceback during addon-enable (non-fatal here, but a fragile edge). | not attempted (blocked below) |
| Commercial-production practicality | 8 (zero licensing risk, K70-owned, already shipping) | 6 -- real, explicit GPL-3.0-or-later license (independently confirmed straight from `blender_manifest.toml`, not just the marketing page), doesn't bundle Mojang assets by default. GPL obligations attach to redistributing the *rig/addon files*, not to rendered video output -- get real legal sign-off before committing, but this is a workable license, not a dead end. | 1 -- **no LICENSE file found anywhere** (GitHub repo, carrd site, wiki) despite "open source" branding; asset library bundles Minecraft "sounds" alongside blocks/items/mobs, an unverified Mojang-IP risk. Not cleared for commercial use without the maintainer's explicit written terms. |
| **Total (where scored)** | **52/90** | **48/70 possible so far (Expressions/Animation/Customization not exercised)** | **1/10 (licensing alone)** |

## What was actually tested (not just researched)

1. **Ice Cube: not installed, not tested.** The licensing finding alone
   (no LICENSE file, unresolved Mojang-sound-asset risk) is disqualifying
   for a commercial channel on its own -- spending setup/render time to
   test animation quality wouldn't change that verdict, and the brief
   explicitly said not to spend hours on either system.

2. **Thomas Rig Legacy: real headless pipeline confirmed working.**
   - Downloaded the real .zip from its official Blender Extensions
     page (URL and sha256-addressed download independently verified
     by a research pass, then actually fetched: 10.6MB, valid zip).
   - License independently re-verified by reading the addon's own
     `blender_manifest.toml` directly (not trusting the webpage):
     `license = ["SPDX:GPL-3.0-or-later"]`. Matches research.
   - `bpy.ops.extensions.package_install_files()` +
     `bpy.ops.preferences.addon_enable()` succeeded headless (exit 0).
   - Opened the bundled `Thomas Rig Legacy.blend`, called
     `bpy.ops.thomasriglegacy.appendbasemesh()` -- **`{'FINISHED'}`**,
     produced a full mesh character (100+ mesh objects: body, head,
     arms with Steve/Alex/3x3 variants, eyes, eyebrows, teeth, tongue).
   - Rendered one real preview frame (`renders/thomas_rig_test.png`):
     genuinely more detailed than the K70 custom system -- visible
     iris/pupil, eyebrow shading, real hair volume, real materials.
   - **Real blocker found**: the bundled rig file itself was saved by
     Blender 4.5.88; opening it in our local 4.2.4 portable install
     printed `Warning: File written by newer Blender binary, expect
     loss of data!`. The mesh-build step still worked, but this is a
     genuine version-compatibility gap, not a code bug -- would need a
     newer local Blender install to use reliably, which was NOT
     attempted here (out of scope for a 5-10s smoke test, and risks
     destabilizing the existing MB-Lab/voxel_human pipeline that
     depends on the current 4.2.4 portable install).
   - Not tested (would need more time): actual animation playback
     (idle/walk/gesture), facial expression controls, texturing an
     original (non-Minecraft) design onto the mesh, render time at
     production resolution/samples.

## Recommendation (current, incomplete data)

**Do not switch production over yet.** The custom K70 voxel_human
system is proven, licensing-clean, and is the system actively
producing the real longform video right now -- there is no reason to
touch it mid-production. Thomas Rig Legacy is a genuinely promising
upgrade path (visibly higher character fidelity, real automatable
pipeline, real license) but carries one concrete blocker (Blender
version mismatch) that needs a deliberate decision -- install a newer
Blender locally, specifically for this rig -- not a quick fix. Ice
Cube is out on licensing alone. If K70 wants to pursue Thomas Rig
further, the next real step is: install Blender 4.5+, retest the full
build+animate+texture pipeline properly, and only then decide whether
to migrate.
