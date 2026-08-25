# Thomas Rig Legacy -- Final Status (this session)

**Decision: not adopted. Reverted to the K70 custom voxel_human system.**

## What was proven working
- License: GPL-3.0-or-later, independently confirmed by reading the
  addon's own `blender_manifest.toml` directly (not just the webpage).
  Doesn't bundle Mojang assets by default (opt-in .jar texture path).
- Headless install/enable: confirmed working (`bpy.ops.extensions.
  package_install_files` + `addon_enable` succeed under `--background`).
- Headless mesh-build: `bpy.ops.thomasriglegacy.appendbasemesh()`
  returns `{'FINISHED'}` cleanly, no exceptions.
- Real render quality when it partially works: visibly higher-fidelity
  textures (iris/pupil detail, eyebrow shading, real hair volume) than
  the K70 custom system.
- Root cause of the visual defect identified with certainty: confirmed
  directly by the addon developer (BlueEvilGFX) in the extension's own
  review thread that `appendbasemesh()` intentionally creates 2-3
  non-render "extrusion helper" duplicate meshes per body part, meant
  for manual armor/hat modeling in the interactive UI -- other
  interactive (non-scripted) users report the identical "why does it
  have 2-3 heads" symptom. This is NOT a headless-scripting bug.

## What could not be resolved
Despite 15 real test/render iterations using rigorous, evidence-based
methods -- diagnostic position dumps, collection/visibility checks,
deform-bone-binding checks, camera ray-casting to identify the exact
object at the visible duplicate's screen position (replicating an
interactive viewport click without a GUI), and a sanity check that
proved the render pipeline correctly reflects scene changes -- the
exact combination of objects to hide/delete for a clean single-instance
render was not found. Deleting confirmed, ray-cast-verified duplicate
objects (`2_Layer_Extrusion`, `1_Layer_Extrusion`, `Head_Layer`) did
not visibly change the rendered output, which remains unexplained.

## Why this wasn't pushed further
The addon's own developer describes the fix as an interactive, visual
step ("hide them in the render") -- click the object in the outliner,
see it highlighted, hide it. That's a fundamentally different
operation from identifying it blind via script, and there's a real
chance further script-only attempts would continue hitting the same
wall. Given the K70 custom voxel_human system is proven, reliable, and
already the system that produced the actual longform video and EP01
benchmark, continuing to sink time into this specific addon's
undocumented internals stopped being a good trade.

## If revisited later
The fastest path to actually resolving this would be a human opening
`assets/rigs/Thomas Rig Legacy.blend` in Blender's interactive GUI,
running `appendbasemesh()` via the addon's own UI panel, and reading
off the exact object name(s) to hide directly from the outliner/3D
viewport selection -- the visual, interactive step the developer
himself describes as the intended workflow, which no amount of
headless scripting fully replicated here.
