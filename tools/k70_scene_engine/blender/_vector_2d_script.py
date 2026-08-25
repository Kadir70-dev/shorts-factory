"""K70 Visual Engine V2 -- Style 2: Premium 2D Vector. Runs inside Blender.

Integration note: Synfig (real standalone CLI renderer, GPL-3.0, license-
clear per V2_LICENSE_MANIFEST.md) is the brief's named candidate, but
building an actual character rig means hand-authoring/scripting Synfig's
.sif XML format from scratch with zero prior track record in this session
-- a real unknown-depth risk under the 10-minute anti-bug-loop rule. Per
this session's explicit instruction ("the STYLE must work; a particular
repository does not have to"), this style is instead built with Blender's
own well-documented, engine-agnostic NPR technique: flat-color fill meshes
+ an "inverted hull" outline (a slightly-larger, flipped-normal, unlit-
black duplicate rendered behind each shape) -- the standard non-Freestyle
way to get crisp cel/vector-style outlines that works identically on
EEVEE/EEVEE_NEXT/Cycles. Orthographic camera, flat lighting, no PBR/HDRI
-- deliberately NOT the voxel style's 3D-lit look.

    blender --background --python _vector_2d_script.py -- <args.json>
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
        raise SystemExit("usage: blender --background --python _vector_2d_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def flat_material(name, color):
    """Pure flat fill -- emission-only (shadeless), the signature look of
    premium 2D vector/explainer graphics: no specular, no shadow falloff,
    just clean flat color."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*color, 1.0)
    emit.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def build_label(text, location, size=0.12, color=(0.15, 0.15, 0.18)):
    """Real readable text label -- reuses the SAME text-rotation fix
    root-caused for the Sketch style (Blender text is authored in the XY
    plane; every flat shape here faces the camera in the XZ plane via a
    90deg X rotation, so the text object needs that same rotation or it
    renders edge-on as an invisible line)."""
    bpy.ops.object.text_add(location=location, rotation=(math.radians(90), 0, 0))
    txt = bpy.context.active_object
    txt.name = f"label_{text[:12]}"
    txt.data.body = text
    txt.data.size = size
    txt.data.align_x = 'CENTER'
    txt.data.extrude = 0.0
    txt.data.materials.append(flat_material(f"label_{text[:12]}_mat", color))
    return txt


_OUTLINE_MAT = None


def _outline_material():
    global _OUTLINE_MAT
    if _OUTLINE_MAT is None:
        _OUTLINE_MAT = flat_material("vec_outline", (0.06, 0.06, 0.08))
    return _OUTLINE_MAT


def flat_shape(name, kind, size, location, color, rotation_z=0.0, outline_width=0.02):
    """A single flat vector shape (circle or rounded rect) facing the
    camera on the XZ plane (Y is depth). The "vector outline" is a
    slightly-larger flat duplicate of the SAME shape, in the outline
    color, placed a touch FURTHER from the camera (real bug found and
    fixed here: the camera looks toward +Y from a negative-Y position, so
    "further away" means LARGER y, not smaller -- an earlier version had
    this sign backwards, which put a giant dark outline shape IN FRONT of
    every fill, hiding all color entirely, confirmed via a smoke-test
    render before this fix). This flat-duplicate approach was also
    simpler and more predictable than the solidify/inverted-hull 3D trick
    it replaced, with no normal-flipping/thickness-direction ambiguity."""
    bpy.ops.object.select_all(action='DESELECT')

    def _make(scale_mult, y_offset, mat, obj_name):
        # Real bug found and fixed: primitive_circle_add's NGON face,
        # combined with the (90deg,0,rotation_z) orientation used to face
        # every flat shape at the camera, rendered completely invisible
        # (confirmed via a pixel-color sweep of a full test render -- the
        # skin-tone color was NOWHERE in the frame despite the mesh object
        # existing with correct geometry/location/material). Root cause is
        # almost certainly a flipped face normal from that combination
        # (planes and circles get opposite winding from primitive_add).
        # Fixed by building "circle" heads from the SAME beveled-plane
        # path already proven to render correctly for every rect shape,
        # with a bevel width near half the size for a rounded silhouette
        # instead of using primitive_circle_add at all.
        bpy.ops.mesh.primitive_plane_add(
            size=1, location=(location[0], location[1] + y_offset, location[2]),
            rotation=(math.radians(90), 0, rotation_z))
        o = bpy.context.active_object
        o.scale = (size[0] * scale_mult, size[1] * scale_mult, 1)
        bpy.ops.object.transform_apply(scale=True)
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bev = o.modifiers.new("bevel", type="BEVEL")
        bev.width = min(size) * scale_mult * (0.48 if kind == "circle" else 0.12)
        bev.segments = 16 if kind == "circle" else 4
        bpy.ops.object.modifier_apply(modifier="bevel")
        o.name = obj_name
        o.data.materials.append(mat)
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
        bpy.ops.object.select_all(action='DESELECT')
        return o

    outline = _make(1.0 + outline_width, 0.003, _outline_material(), f"{name}_outline")
    obj = _make(1.0, 0.0, flat_material(f"{name}_mat", color), name)
    return obj, outline


def key(obj, frame, loc=None, euler=None, scale=None):
    bpy.context.scene.frame_set(frame)
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert(data_path="location", frame=frame)
    if euler is not None:
        obj.rotation_euler = euler
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)


def sync_outline(fill, outline, frame, loc=None, euler=None, scale=None):
    """Outline meshes are separate objects (for the inverted-hull trick),
    so any fill-object animation must be mirrored onto its outline twin
    to keep them visually locked together."""
    key(fill, frame, loc=loc, euler=euler, scale=scale)
    ol_loc = None
    if loc is not None:
        ol_loc = (loc[0], loc[1] + 0.003, loc[2])  # further from camera than the fill -- see flat_shape()
    key(outline, frame, loc=ol_loc, euler=euler, scale=scale)


ROLE_PALETTE = {
    # Locked to the K70 canonical John identity (same skin/shirt/hair
    # values as ROLE_STYLES["john"] in _voxel_human_script.py) for cross-
    # style character continuity -- see K70_VISUAL_ENGINE_V2_REPORT.md.
    "john": {"skin": (0.82, 0.62, 0.48), "shirt": (0.18, 0.35, 0.62), "hair": (0.25, 0.16, 0.10)},
}


def build_vector_character(role, root_location=(0, 0, 0)):
    """Simplified flat 2D vector character: head/torso/arms as separate
    flat shapes so the arm can be independently animated for a gesture --
    same 'separated reusable components' spirit as the brief's component
    list (head/hair/eyes/torso/arms), scoped down for one gold benchmark."""
    p = ROLE_PALETTE[role]
    x, y, z = root_location
    parts = {}

    torso_fill, torso_outline = flat_shape(f"{role}_torso", "rect", (0.55, 0.75), (x, y, z + 0.55), p["shirt"])
    head_fill, head_outline = flat_shape(f"{role}_head", "circle", (0.42, 0.42), (x, y, z + 1.15), p["skin"])
    hair_fill, hair_outline = flat_shape(f"{role}_hair", "rect", (0.46, 0.20), (x, y - 0.001, z + 1.32), p["hair"])

    arm_fill, arm_outline = flat_shape(f"{role}_arm_r", "rect", (0.16, 0.55), (x + 0.35, y, z + 0.7), p["skin"])
    # Move the arm's origin to its SHOULDER end (top) so rotation reads as
    # a natural shoulder pivot, not a spin around the arm's own center --
    # origin_set(ORIGIN_CURSOR) moves the PIVOT only, geometry stays put.
    bpy.context.scene.cursor.location = (x + 0.35, y, z + 0.98)
    for o in (arm_fill, arm_outline):
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

    parts["torso"] = (torso_fill, torso_outline)
    parts["head"] = (head_fill, head_outline)
    parts["hair"] = (hair_fill, hair_outline)
    parts["arm_r"] = (arm_fill, arm_outline)
    return parts


def animate_gesture(parts, start=0, length=60):
    arm_fill, arm_outline = parts["arm_r"]
    for f, ang in ((start, 0.0), (start + int(length * 0.3), -95.0),
                  (start + int(length * 0.7), -80.0), (start + length, 0.0)):
        sync_outline(arm_fill, arm_outline, f, euler=(math.radians(ang), 0, 0))
    head_fill, head_outline = parts["head"]
    for f, ang in ((start, 0.0), (start + length // 2, 6.0), (start + length, 0.0)):
        sync_outline(head_fill, head_outline, f, euler=(0, 0, math.radians(ang)))


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
    scene.render.film_transparent = False
    if hasattr(scene, "eevee"):
        try:
            scene.eevee.taa_render_samples = render["samples"]
        except AttributeError:
            pass

    bg = a.get("bg_color", [0.96, 0.94, 0.90])
    world = bpy.data.worlds.new("vec_world")
    scene.world = world
    world.use_nodes = True
    bgn = world.node_tree.nodes.get("Background")
    bgn.inputs["Color"].default_value = (*bg, 1.0)
    bgn.inputs["Strength"].default_value = 1.0

    # Flat "financial explainer" set dressing: a card + a labeled bar
    # waterfall (income -> expense categories -> remainder) so the shot
    # reads as premium editorial design, not an isolated character on a
    # blank card. Bar list is spec-driven so the same script covers both
    # the standalone gold benchmark's simple 3-bar demo and the master
    # story's full income/expense breakdown.
    default_bars = [
        {"label": "", "h": 0.25, "color": [0.22, 0.55, 0.82]},
        {"label": "", "h": 0.43, "color": [0.20, 0.68, 0.55]},
        {"label": "", "h": 0.61, "color": [0.85, 0.60, 0.20]},
    ]
    bar_specs = a.get("bars", default_bars)
    card_w = max(2.6, 0.55 * len(bar_specs) + 1.0)
    card_fill, card_outline = flat_shape("card", "rect", (card_w, 1.9), (0, 0.15, 1.0), (1.0, 1.0, 1.0),
                                         outline_width=0.02)
    n = len(bar_specs)
    bars = []
    for i, spec in enumerate(bar_specs):
        h = spec["h"]
        x = -(0.42 * (n - 1)) + i * 0.84
        bf, bo = flat_shape(f"bar_{i}", "rect", (0.34, h), (x, 0.1, 0.35 + h / 2), tuple(spec["color"]))
        bars.append((bf, bo, h, i))
        if spec.get("label"):
            build_label(spec["label"], (x, 0.09, 0.24), size=0.11)

    # The character sits at world-center (0,0,0), the same spot the bars and
    # their labels occupy -- fine for the original illustrated-explainer use
    # of this script, but it hides bar labels when the shot is a pure data
    # chart (no host character wanted). Opt out via show_character=False.
    if a.get("show_character", True):
        root = (0, 0.05, 0)
        parts = build_vector_character("john", root_location=root)
        animate_gesture(parts, start=a.get("gesture_start", 8), length=a.get("gesture_length", 48))

    for bf, bo, h, i in bars:
        f0 = 4 + i * 8
        sync_outline(bf, bo, max(0, f0 - 4), scale=(1, 1, 0.05))
        sync_outline(bf, bo, f0, scale=(1, 1, 1))

    frame_range = a.get("frame_range")
    if frame_range:
        scene.frame_start, scene.frame_end = frame_range

    cam_data = bpy.data.cameras.new("vec_cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = a.get("ortho_scale", 3.6)
    cam_obj = bpy.data.objects.new("vec_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = (0, -4.0, 0.95)
    cam_obj.rotation_euler = (math.radians(90), 0, 0)
    scene.camera = cam_obj

    if a.get("push_in"):
        f0, f1 = frame_range
        key(cam_obj, f0, loc=(0, -4.0, 0.95))
        key(cam_obj, f1, loc=(0, -3.4, 0.95))

    out_dir = Path(render["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    n_frames = a.get("n_frames", 1)
    fs, fe = scene.frame_start, scene.frame_end
    for i in range(n_frames):
        t = fs + (fe - fs) * i / max(n_frames - 1, 1)
        scene.frame_set(int(round(t)))
        scene.render.filepath = str(out_dir / f"frame_{i:03d}.png")
        bpy.ops.render.render(write_still=True)
    print(f"K70_VECTOR2D_RENDER_OK {out_dir} frames={n_frames}")


if __name__ == "__main__":
    main()
