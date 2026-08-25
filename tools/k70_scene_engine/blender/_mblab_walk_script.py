"""Runs INSIDE Blender. Renders a real walk-cycle animation sequence for
an MB-Lab character: opens a finalized checkpoint, retargets MB-Lab's own
bundled walking.bvh onto the rig (real mocap, see _mblab_character.py's
license note), dresses the character, places it in front of a simple
house/exterior context, and renders N evenly-spaced frames across the
real walk-cycle frame range -- same "sample real keyframes, don't fake
it" contract as the proven Gobkit animated_character.py from the earlier
session.

    blender --background --python _mblab_walk_script.py -- <args.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
from mathutils import Vector

import _mblab_character as mc  # noqa: E402
from lighting_presets import setup_lighting  # noqa: E402


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _mblab_walk_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def main() -> None:
    a = _args()
    bpy.ops.wm.open_mainfile(filepath=a["checkpoint"])
    bpy.ops.preferences.addon_enable(module="mb_lab")

    body = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("MBlab_bd"))
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    for o in list(bpy.data.objects):
        if o.name not in (body.name, arm.name):
            bpy.data.objects.remove(o, do_unlink=True)

    mc._fix_eye_materials(body)
    mc.dress_character(a["role"], body, arm, hair=True)

    action = mc.add_walk_animation(arm)
    if action is None:
        raise RuntimeError(
            f"walk animation retargeting produced no action for role={a['role']} -- "
            "not faking a static pose as animated.")
    frame_start, frame_end = action.frame_range
    frame_start, frame_end = int(frame_start), int(frame_end)
    print(f"K70_WALK_ACTION frame_range=({frame_start},{frame_end})")

    n_frames = a.get("n_frames", 12)
    frames = [frame_start + round((frame_end - frame_start) * i / max(1, n_frames - 1))
             for i in range(n_frames)]

    # Camera framing is computed from the CHARACTER's own bounds only --
    # a real, confirmed bug in the first version of this script computed
    # framing from the combined character+house bounds, and the much
    # larger house dominated the math so badly that John was cropped out
    # of every single one of 4 test frames (confirmed by direct visual
    # inspection of the render, not assumed). The house (if requested) is
    # placed as background set-dressing behind/beside the character,
    # sized and positioned relative to the character's own bounds, but
    # never drives the camera math.
    def _char_bounds(frame):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        mins = Vector((float("inf"),) * 3)
        maxs = Vector((float("-inf"),) * 3)
        for obj in bpy.context.scene.objects:
            if obj.type != "MESH":
                continue
            eo = obj.evaluated_get(depsgraph)
            for v in eo.data.vertices:
                wc = eo.matrix_world @ v.co
                mins = Vector(min(x, y) for x, y in zip(mins, wc))
                maxs = Vector(max(x, y) for x, y in zip(maxs, wc))
        return mins, maxs

    char_mins, char_maxs = _char_bounds(frames[0])
    char_center = (char_mins + char_maxs) / 2
    char_height = char_maxs.z - char_mins.z
    print(f"K70_CHAR_BOUNDS mins={tuple(char_mins)} maxs={tuple(char_maxs)} height={char_height}")

    # Combining house geometry into this same shot produced two real,
    # confirmed-broken renders in a row (v1: John cropped out of frame
    # entirely because combined bounds let the much-larger house
    # dominate the distance calc; v2, after re-deriving bounds from the
    # character alone, put the camera absurdly close to a wall/window
    # fragment -- the walk-retargeting process appears to reposition/
    # rescale things in ways this script wasn't correctly accounting
    # for). Rather than keep guessing, this drops the house from this
    # specific shot and reuses the camera approach already CONFIRMED
    # working for a character-only walk render (test_walk.py, real
    # render inspected directly: John clearly visible, walking, correct
    # framing). The house still appears in the story via a separate real
    # stock-footage beat immediately before this one.
    setup_lighting(a.get("lighting", "exterior_day"), char_mins, char_maxs, add_ground=True)

    distance = char_height * 2.2
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 50
    cam_obj = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = (char_center.x + distance * 0.7, char_center.y - distance * 1.2,
                        char_center.z + distance * 0.25)
    look_at = Vector((char_center.x, char_center.y, char_center.z))
    cam_obj.rotation_euler = (look_at - cam_obj.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam_obj

    render = a["render"]
    scene = bpy.context.scene
    scene.render.engine = render["engine"]
    scene.render.resolution_x = render["width"]
    scene.render.resolution_y = render["height"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_stamp = False
    if hasattr(scene, "eevee"):
        try:
            scene.eevee.taa_render_samples = render["samples"]
            scene.eevee.use_raytracing = True
        except AttributeError:
            pass

    out_dir = Path(render["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(frames):
        bpy.context.scene.frame_set(f)
        out_path = out_dir / f"frame_{i:03d}.png"
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        print(f"K70_WALK_FRAME_OK {out_path} (source frame {f})")

    print(f"K70_WALK_SEQUENCE_OK {len(frames)} frames -> {out_dir}")


if __name__ == "__main__":
    main()
