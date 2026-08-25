"""Runs INSIDE Blender. Opens an already-finalized MB-Lab character
checkpoint (.blend, saved right after finalize_character -- see
_mblab_character.py's build_mblab_character docstring for why: the bake
alone takes several minutes, checkpointing avoids repeating it for every
render), dresses it, lights it, frames it, renders.

    blender --background --python _mblab_render_script.py -- <args.json>

args.json: {"role": "john", "checkpoint": "...posed.blend",
"lighting": "portrait_studio", "shot": "medium", "angle": "three_quarter",
"office_environment": false, "width":1280, "height":720, "samples":64,
"output": "..."}
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
from mathutils import Vector

import _mblab_character as mc  # noqa: E402
from lighting_presets import setup_lighting  # noqa: E402
from camera_presets import build_camera  # noqa: E402
from _office_scene_script import build_office_set  # noqa: E402


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _mblab_render_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def main() -> None:
    a = _args()
    bpy.ops.wm.open_mainfile(filepath=a["checkpoint"])
    # Real bug: dress_character() now calls add_real_hair(), which needs
    # MB-Lab's own operators/scene properties (mblab_hair_color,
    # mbast.particle_hair) -- this script never enabled the addon before
    # (fine when dress_character only built shirt/pants via plain bmesh,
    # broke with a real AttributeError once hair was added).
    bpy.ops.preferences.addon_enable(module="mb_lab")

    body = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("MBlab_bd"))
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    for o in list(bpy.data.objects):
        if o.name not in (body.name, arm.name):
            bpy.data.objects.remove(o, do_unlink=True)

    mc._fix_eye_materials(body)
    mc.dress_character(a["role"], body, arm)

    if a.get("office_environment"):
        env_objs = build_office_set(width=5.0, depth=4.0, height=2.8)
        for o in env_objs:
            if o.type == "MESH":
                o.location.x -= 1.3

    mins = Vector((float("inf"),) * 3)
    maxs = Vector((float("-inf"),) * 3)
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            wc = obj.matrix_world @ Vector(corner)
            mins = Vector(min(x, y) for x, y in zip(mins, wc))
            maxs = Vector(max(x, y) for x, y in zip(maxs, wc))

    setup_lighting(a.get("lighting", "portrait_studio"), mins, maxs,
                   add_ground=not a.get("office_environment", False))
    build_camera(a.get("shot", "medium"), mins, maxs, angle=a.get("angle", "three_quarter"),
                dof_target=body)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = a.get("width", 1280)
    scene.render.resolution_y = a.get("height", 720)
    scene.render.filepath = a["output"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_stamp = False
    if hasattr(scene, "eevee"):
        try:
            scene.eevee.taa_render_samples = a.get("samples", 64)
            scene.eevee.use_raytracing = True
        except AttributeError:
            pass

    bpy.ops.render.render(write_still=True)
    print(f"K70_MBLAB_SCENE_RENDER_OK {a['output']}")


if __name__ == "__main__":
    main()
