"""Runs INSIDE Blender. Renders a genuine multi-frame animation sequence
from a rigged/animated glTF character -- the missing half of "rigged AND
animated" (see FINAL_REPORT.md's audit: the source .glb files carry real
skins + a real "movement" action, but scene_builder_script.py's static
render never samples it). This script imports the character, finds its
armature's actual Action, sets the scene frame range to that action's own
real frame range (queried at runtime, not assumed), and renders N evenly
spaced frames -- real keyframe evaluation, not a single held pose repeated.
"""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _animated_character_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def main() -> None:
    a = _args()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    src = Path(a["source_path"])
    bpy.ops.import_scene.gltf(filepath=str(src))
    imported = list(bpy.context.selected_objects)
    if not imported:
        raise RuntimeError(f"import produced no objects: {src}")

    tint = a.get("tint")
    if tint is not None:
        mat = bpy.data.materials.new(name="k70_accent_tint")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*tint, 1.0)
        for obj in imported:
            if obj.type == "MESH":
                obj.data.materials.clear()
                obj.data.materials.append(mat)

    armature = next((o for o in imported if o.type == "ARMATURE"), None)
    if armature is None or armature.animation_data is None or armature.animation_data.action is None:
        raise RuntimeError(
            f"no armature+action found in {src} -- this asset is not actually "
            "animated (do not fake it); reported honestly as a RuntimeError "
            "rather than silently rendering a static frame.")
    action = armature.animation_data.action
    frame_start, frame_end = action.frame_range
    frame_start, frame_end = int(frame_start), int(frame_end)
    print(f"K70_ANIM_INFO action={action.name!r} frame_range=({frame_start},{frame_end})")

    n_frames = a.get("n_frames", 8)
    frames = [frame_start + round((frame_end - frame_start) * i / max(1, n_frames - 1))
             for i in range(n_frames)]

    mins = Vector((float("inf"),) * 3)
    maxs = Vector((float("-inf"),) * 3)
    bpy.context.scene.frame_set(frame_start)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        eval_obj = obj.evaluated_get(depsgraph)
        for corner in eval_obj.bound_box:
            wc = eval_obj.matrix_world @ Vector(corner)
            mins = Vector(min(x, y) for x, y in zip(mins, wc))
            maxs = Vector(max(x, y) for x, y in zip(maxs, wc))
    center = (mins + maxs) / 2
    span = max((maxs - mins).x, (maxs - mins).y, (maxs - mins).z, 0.5)

    bpy.ops.mesh.primitive_plane_add(size=span * 8, location=(0, 0, mins.z))
    ground = bpy.context.active_object
    ground_mat = bpy.data.materials.new("k70_ground")
    ground_mat.use_nodes = True
    bsdf = ground_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.05, 0.055, 0.07, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.85
    ground.data.materials.append(ground_mat)

    world = bpy.data.worlds.new("k70_world")
    world.use_nodes = True
    bpy.context.scene.world = world
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.035, 0.045, 0.07, 1.0)
        bg.inputs["Strength"].default_value = 0.6

    key_data = bpy.data.lights.new("k70_key", type="AREA")
    key_data.energy = 400.0
    key_data.size = span * 2
    key_obj = bpy.data.objects.new("k70_key", key_data)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = center + Vector((span * 1.5, -span * 2.0, span * 2.2))
    key_obj.rotation_euler = (center - key_obj.location).to_track_quat("-Z", "Y").to_euler()

    distance = span * 1.8
    cam_data = bpy.data.cameras.new("k70_cam")
    cam_data.lens = 85
    cam_obj = bpy.data.objects.new("k70_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = center + Vector((distance * 0.85, -distance * 1.1, distance * 0.45))
    cam_obj.rotation_euler = (center - cam_obj.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam_obj

    render = a["render"]
    scene = bpy.context.scene
    scene.render.engine = render["engine"]
    scene.render.resolution_x = render["width"]
    scene.render.resolution_y = render["height"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_stamp = False
    if render["engine"] == "CYCLES":
        scene.cycles.samples = render["samples"]
    elif hasattr(scene, "eevee"):
        try:
            scene.eevee.taa_render_samples = render["samples"]
        except AttributeError:
            pass

    out_dir = Path(render["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered = []
    for i, frame in enumerate(frames):
        bpy.context.scene.frame_set(frame)
        out_path = out_dir / f"frame_{i:03d}.png"
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        rendered.append(str(out_path))
        print(f"K70_ANIM_FRAME_OK {out_path} (source frame {frame})")

    print(f"K70_ANIM_SEQUENCE_OK {len(rendered)} frames -> {out_dir}")


if __name__ == "__main__":
    main()
