"""K70 VFX Director -- Blender compositor stage. Runs inside Blender.

Operates on an ALREADY-RENDERED frame sequence from any compatible K70
visual mode (a HELPER LAYER, not a re-render of the 3D scene) using
Blender's own native 2D compositor nodes -- confirmed-real node types/
properties via live introspection against this actual Blender 4.2.4
install (see _check_comp_nodes probe), not guessed:

  CompositorNodeImage       -- loads the input PNG sequence
  CompositorNodeColorBalance (LIFT_GAMMA_GAIN, gain only) -- base warm/cool push
  CompositorNodeGlare (FOG_GLOW / STREAKS / BLOOM)        -- atmosphere/glow/sparkle
  CompositorNodeSunBeams                                   -- light rays / god rays
  CompositorNodeEllipseMask + ValToRGB + MixRGB(MULTIPLY)  -- vignette (Blender has
                                                              no single Vignette node)

Does NOT touch the 3D scene/rig/camera of whatever produced the input
frames -- pure 2D post-process on already-rendered pixels.

    blender --background --python _vfx_blender_pass.py -- <args.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy


def _args():
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def main():
    a = _args()
    input_dir = Path(a["input_dir"])
    output_dir = Path(a["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_start = a.get("frame_start", 0)
    frame_count = a["frame_count"]
    width, height = a.get("width", 1080), a.get("height", 1920)
    cfg = a["blender_cfg"]

    first_frame_path = input_dir / f"frame_{frame_start:04d}.png"

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.image_settings.file_format = "PNG"
    scene.use_nodes = True
    # Factory-default view_transform is AgX (Blender 4.2), a scene-referred
    # HDR tone-map. This pass's Image input is already-encoded 8-bit sRGB
    # PNGs being passed straight through the compositor, not a linear
    # scene render -- applying AgX on top of that double-transforms it and
    # can crush bright/pale source frames toward black (confirmed via a
    # real isolated test: a bright apartment-interior frame, RGB mean
    # ~166/255 as loaded, rendered out at RGB mean ~0.4/255 -- effectively
    # solid black -- with AgX active; forcing Standard here fixed it,
    # verified same input then rendered at RGB mean ~167/255).
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    nt = scene.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)

    img = bpy.data.images.load(str(first_frame_path))
    img_node = nt.nodes.new("CompositorNodeImage")
    img_node.image = img
    # Deliberately NOT using img.source="SEQUENCE" + frame_start/duration/
    # offset + a single animation-render call. That mechanism has a real,
    # reproducible bug on this build: with frame_count source files
    # available, only the first (frame_count - 1) sequence positions read
    # correctly -- the source frame at index (frame_count - 1) onward
    # rendered solid black (RGB mean ~0.4/255 vs ~167/255 for the correct
    # frames), reproduced identically regardless of frame_duration padding
    # (tested +1 and +3), color management, or the scale/resolution
    # pipeline (all ruled out first). Explicitly setting img.filepath to
    # the exact frame and calling img.reload() before each single-frame
    # render -- the same "explicit, not implicit" fix already applied to
    # this project's Natron stage for an analogous bug -- sidesteps
    # Blender's sequence-position bookkeeping entirely: verified all N
    # frames render correctly (RGB mean ~167/255 each, no black frame)
    # with this approach on the exact input that broke the sequence path.

    last_output = img_node.outputs["Image"]

    # NOTE: frames are pre-scaled to the exact render resolution by the
    # DIRECTOR (vfx_director.py::_prescale_frames_if_needed, PIL-based)
    # before this script ever runs -- NOT via a Blender CompositorNodeScale
    # node. That node was tried first (space="RENDER_SIZE", frame_method=
    # "FIT") and confirmed to have a real, reproducible bug on this build:
    # downscaling a landscape (width>height) source frame produced a
    # solid-black composite regardless of scale mode (RENDER_SIZE/FIT or
    # RELATIVE with an explicit factor), while the identical portrait case
    # worked fine. A PIL-prescaled frame loaded at 1:1 rendered perfectly
    # on the exact same input, isolating the bug to Blender's Scale node
    # itself. Since frames now always arrive at the correct size, no
    # Blender-side scaling step is needed here at all.

    # ---- base warm/cool color push ---- #
    gain = cfg["color_balance_gain"]
    # args arrive via JSON, so gain is always a list here even when the
    # caller passed a tuple -- compare element-wise, not list-vs-tuple
    # (which is always unequal in Python and was silently adding a
    # no-op ColorBalance node on every neutral-gain call).
    if tuple(gain) != (1.0, 1.0, 1.0):
        cb = nt.nodes.new("CompositorNodeColorBalance")
        cb.correction_method = "LIFT_GAMMA_GAIN"
        cb.gain = (gain[0], gain[1], gain[2])
        nt.links.new(last_output, cb.inputs["Image"])
        last_output = cb.outputs["Image"]

    # ---- glare (atmosphere/glow/sparkle) ---- #
    if cfg["glare_mode"] and cfg["glare_strength"] > 0.001:
        glare = nt.nodes.new("CompositorNodeGlare")
        glare.glare_type = cfg["glare_mode"]
        glare.quality = "MEDIUM"
        glare.threshold = 0.55
        # mix: -1 = original only, 0 = 50/50, +1 = glare only -- scale
        # strength into a subtle additive range so this never overpowers
        # the source image (per "do not blindly stack every effect").
        glare.mix = -1.0 + min(1.0, cfg["glare_strength"])
        if cfg["glare_mode"] == "STREAKS":
            glare.streaks = 4
            glare.angle_offset = 0.3
        nt.links.new(last_output, glare.inputs["Image"])
        last_output = glare.outputs["Image"]

    # ---- sun beams (light rays / god rays) ---- #
    if cfg["sun_beams"] and cfg["sun_beams_strength"] > 0.001:
        pre_beams = last_output
        beams = nt.nodes.new("CompositorNodeSunBeams")
        beams.source = (0.5, 0.85)  # upper-frame source, a plausible sky/window direction
        beams.ray_length = 0.15 + 0.35 * cfg["sun_beams_strength"]
        nt.links.new(pre_beams, beams.inputs["Image"])
        mix = nt.nodes.new("CompositorNodeMixRGB")
        mix.blend_type = "SCREEN"
        mix.inputs["Fac"].default_value = min(1.0, cfg["sun_beams_strength"])
        nt.links.new(pre_beams, mix.inputs[1])
        nt.links.new(beams.outputs["Image"], mix.inputs[2])
        last_output = mix.outputs["Image"]

    # ---- vignette (built from primitives -- Blender has no single Vignette node) ---- #
    if cfg["vignette"] > 0.001:
        pre_vignette = last_output
        ellipse = nt.nodes.new("CompositorNodeEllipseMask")
        ellipse.x, ellipse.y = 0.5, 0.5
        ellipse.mask_width = 1.15 - 0.35 * cfg["vignette"]
        ellipse.mask_height = 1.15 - 0.35 * cfg["vignette"]
        ramp = nt.nodes.new("CompositorNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.0
        ramp.color_ramp.elements[0].color = (1 - cfg["vignette"], 1 - cfg["vignette"], 1 - cfg["vignette"], 1.0)
        ramp.color_ramp.elements[1].position = 1.0
        ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
        nt.links.new(ellipse.outputs["Mask"], ramp.inputs["Fac"])
        vmix = nt.nodes.new("CompositorNodeMixRGB")
        vmix.blend_type = "MULTIPLY"
        vmix.inputs["Fac"].default_value = 1.0
        nt.links.new(pre_vignette, vmix.inputs[1])
        nt.links.new(ramp.outputs["Image"], vmix.inputs[2])
        last_output = vmix.outputs["Image"]

    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(last_output, comp.inputs["Image"])

    # Resume-safety: skip whole stage if every expected frame already
    # exists, matching the same granularity used elsewhere in this
    # pipeline (e.g. preview/final renders).
    expected = [output_dir / f"frame_{f:04d}.png" for f in range(frame_count)]
    if not all(p.exists() for p in expected):
        for f in range(frame_start, frame_start + frame_count):
            img.filepath = str(input_dir / f"frame_{f:04d}.png")
            img.reload()
            out_idx = f - frame_start
            scene.render.filepath = str(output_dir / f"frame_{out_idx:04d}.png")
            bpy.ops.render.render(write_still=True)

    print("K70_VFX_BLENDER_PASS_OK")


if __name__ == "__main__":
    main()
