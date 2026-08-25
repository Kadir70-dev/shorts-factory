"""Runs INSIDE Blender. Renders one recurring K70 character (see
_character_roster.py for the real per-role geometric differentiation),
optionally standing beside a procedural environment for an
interaction/continuity proof shot.

    blender --background --python _character_roster_script.py -- <args.json>

args.json: {"role": "banker", "angle": "three_quarter", "environment":
null|"house"|"bank"|"office"|"store", "width":1280, "height":720,
"output": "..."}

Camera/ground bounds use `evaluated_world_bounds()` (depsgraph-evaluated,
post-armature-deformation), NOT the shared scene_builder_script.py
bound_box-based helpers -- those under-measure a rigged/skinned character
because `obj.bound_box` is the mesh DATA's own undeformed rest-pose box,
not where the posed geometry actually ends up. Confirmed by a real render
during this fix: the ground-fit math said "bottom at z=0" while the
render clearly showed the character floating above the ground plane.
_build_studio() itself is still reused (it just paints a ground/world/
lights around whatever mins/maxs/span it's given), only the bounds
computation is replaced.
"""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).parent))
from _character_roster import ROLES, build_character, evaluated_world_bounds  # noqa: E402
from _procedural_building_script import BUILDERS as BUILDING_BUILDERS  # noqa: E402
from scene_builder_script import _build_studio  # noqa: E402


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _character_roster_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def _all_scene_meshes():
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def _frame_camera(mins: Vector, maxs: Vector, distance_multiplier: float, angle: str):
    center = (mins + maxs) / 2
    span = max((maxs - mins).x, (maxs - mins).y, (maxs - mins).z, 0.5)
    distance = span * distance_multiplier
    offsets = {
        "front": Vector((0, -distance * 1.4, distance * 0.35)),
        "three_quarter": Vector((distance * 0.85, -distance * 1.1, distance * 0.45)),
        "left": Vector((-distance * 1.1, -distance * 0.7, distance * 0.4)),
        "right": Vector((distance * 1.1, -distance * 0.7, distance * 0.4)),
    }
    cam_data = bpy.data.cameras.new("k70_cam")
    cam_data.lens = 50
    cam_obj = bpy.data.objects.new("k70_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = center + offsets.get(angle, offsets["three_quarter"])
    direction = center - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam_obj
    return cam_obj, span


def main() -> None:
    a = _args()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    role_key = a["role"]
    if role_key not in ROLES:
        raise ValueError(f"unknown role '{role_key}', expected one of {list(ROLES)}")

    env = a.get("environment")
    if env:
        builder = BUILDING_BUILDERS.get(env)
        if builder is None:
            raise ValueError(f"unknown environment '{env}', expected one of {list(BUILDING_BUILDERS)}")
        env_objs = builder()
        for o in env_objs:
            o.location.x -= 4.5

    root, mesh_objects = build_character(role_key, pose_frame=a.get("pose_frame"))
    if env:
        root.location.x += 2.2
        root.location.y -= 2.0
        bpy.context.view_layer.update()
        mins, _ = evaluated_world_bounds(root.children_recursive)
        root.location.z -= mins.z
        bpy.context.view_layer.update()

    bpy.context.view_layer.update()
    mins, maxs = evaluated_world_bounds(_all_scene_meshes())
    cam_obj, span = _frame_camera(mins, maxs, a.get("distance_multiplier", 1.3), a.get("angle", "three_quarter"))
    _build_studio(mins, maxs, span, tuple(a.get("world_color", (0.035, 0.045, 0.07))))

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = a.get("width", 1280)
    scene.render.resolution_y = a.get("height", 720)
    scene.render.filepath = a["output"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_stamp = False
    if hasattr(scene, "eevee"):
        try:
            scene.eevee.taa_render_samples = a.get("samples", 48)
        except AttributeError:
            pass

    bpy.ops.render.render(write_still=True)
    print(f"K70_ROSTER_RENDER_OK {a['output']}")


if __name__ == "__main__":
    main()
