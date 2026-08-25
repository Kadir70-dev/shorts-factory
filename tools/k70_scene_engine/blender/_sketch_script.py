"""K70 Visual Engine V2 -- Style 7: Hand-Drawn / Sketch Documentary. Runs
inside Blender.

Integration note: Pencil2D (GPL-2.0, weakest automation surface of the
sketch candidates per V2_LICENSE_MANIFEST.md), OpenToonz (BSD-3-Clause
core but a real thirdparty-brush license caveat found in its own LICENSE
file), and Krita (GUI-first, no headless render loop) were all evaluated
in the license audit. Per the brief's own instruction ("choose the
smallest reliable automation stack, not all four") AND this session's
explicit style-over-repository priority, this uses Blender's own Grease
Pencil system directly -- Blender's dedicated, well-documented 2D-in-3D
drawing/NPR toolset, not a fallback approximation. Real text is converted
to Grease Pencil strokes (`object.convert(target='GPENCIL')`, confirmed
working this session) and revealed progressively via GP's native Build
modifier (`GP_BUILD`, confirmed working), which is the exact mechanism
for "animate as if it is being drawn progressively" -- not simulated any
other way.

    blender --background --python _sketch_script.py -- <args.json>
"""
import json
import math
import sys
from pathlib import Path

import bpy


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _sketch_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def _gp_ink_material(name, color=(0.08, 0.08, 0.10)):
    """Stroke-only (no fill) -- real bug found and fixed during testing:
    with fill enabled AND a thick stroke width, converted letterforms
    rendered as undifferentiated black blobs (fill doesn't correctly
    subtract inner counter-shapes like the hole in '0' via this
    conversion path). Stroke-only line art is also simply the more
    correct look for a hand-drawn sketch anyway."""
    mat = bpy.data.materials.new(name)
    bpy.data.materials.create_gpencil_data(mat)
    mat.grease_pencil.show_stroke = True
    mat.grease_pencil.show_fill = False
    mat.grease_pencil.color = (*color, 1.0)
    return mat


def build_sketch_line(text, location, size, f_start, f_end, name):
    """Real text -> Grease Pencil strokes -> progressive Build reveal.
    Returns the GP object.

    Real bug found and fixed: Blender text objects are authored in the
    XY plane (reading direction +X, letter height +Y). Every other flat
    shape this session (vector/paper/2.5D styles) uses the convention
    "shapes face the camera in the XZ plane, camera looks along +Y" via a
    90deg X rotation at creation -- applying that SAME convention to text
    is required, and was missing at first: without it, the camera looked
    straight down the text's own height axis, viewing it exactly edge-on
    and collapsing every letter into a flat horizontal line (confirmed via
    a render showing only thin horizontal segments, no readable glyphs).
    Fixed by rotating the text object 90deg at creation, same as every
    other primitive in this codebase."""
    bpy.ops.object.text_add(location=location, rotation=(math.radians(90), 0, 0))
    txt = bpy.context.active_object
    txt.data.body = text
    txt.data.size = size
    txt.data.extrude = 0.0
    txt.data.align_x = 'CENTER'
    bpy.context.view_layer.update()

    bpy.ops.object.select_all(action='DESELECT')
    txt.select_set(True)
    bpy.context.view_layer.objects.active = txt
    bpy.ops.object.convert(target='GPENCIL')
    gp = bpy.context.active_object
    gp.name = name

    ink = _gp_ink_material(f"{name}_ink")
    gp.data.materials.append(ink)
    for layer in gp.data.layers:
        for frame in layer.frames:
            for stroke in frame.strokes:
                stroke.material_index = 0
                stroke.line_width = 14

    build = gp.grease_pencil_modifiers.new("build", type='GP_BUILD')
    build.mode = 'ADDITIVE'
    build.transition = 'GROW'
    build.frame_start = f_start
    build.frame_end = f_end
    build.speed_factor = 1.0
    return gp


def key(obj, frame, loc=None, scale=None):
    bpy.context.scene.frame_set(frame)
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert(data_path="location", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)


def main() -> None:
    a = _args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    render = a["render"]
    scene.render.engine = render["engine"]
    scene.render.resolution_x = render["width"]
    scene.render.resolution_y = render["height"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_stamp = False
    if hasattr(scene, "eevee"):
        try:
            scene.eevee.taa_render_samples = render["samples"]
        except AttributeError:
            pass

    world = bpy.data.worlds.new("sketch_world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.97, 0.96, 0.93, 1.0)  # paper white
    bg.inputs["Strength"].default_value = 1.0

    lines = a["lines"]  # [{text, y, f_start, f_end, size}]
    for i, ln in enumerate(lines):
        build_sketch_line(ln["text"], (0, 0, ln["y"]), ln.get("size", 0.6),
                          ln["f_start"], ln["f_end"], f"line_{i}")

    # A simple hand-drawn underline/arrow beneath the final answer, drawn
    # in on its own delayed beat, reusing the same text->GP->Build path
    # (an underscore string renders as a clean horizontal stroke).
    if a.get("underline"):
        u = a["underline"]
        build_sketch_line(u["text"], (0, 0, u["y"]), u.get("size", 0.6), u["f_start"], u["f_end"], "underline")

    frame_range = a.get("frame_range")
    if frame_range:
        scene.frame_start, scene.frame_end = frame_range

    sun = bpy.data.lights.new("sketch_sun", type="SUN")
    sun.energy = 2.5
    sun_obj = bpy.data.objects.new("sketch_sun", sun)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = (0.6, 0, 0.4)

    cam_data = bpy.data.cameras.new("sketch_cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = a.get("ortho_scale", 6.0)
    cam_obj = bpy.data.objects.new("sketch_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = (0, -5.0, 0)
    cam_obj.rotation_euler = (math.radians(90), 0, 0)
    scene.camera = cam_obj

    out_dir = Path(render["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    n_frames = a.get("n_frames", 1)
    fs, fe = scene.frame_start, scene.frame_end
    for i in range(n_frames):
        t = fs + (fe - fs) * i / max(n_frames - 1, 1)
        scene.frame_set(int(round(t)))
        scene.render.filepath = str(out_dir / f"frame_{i:03d}.png")
        bpy.ops.render.render(write_still=True)
    print(f"K70_SKETCH_RENDER_OK {out_dir} frames={n_frames}")


if __name__ == "__main__":
    main()
