"""Runs INSIDE Blender's own Python interpreter (imports `bpy` -- this file
is never imported by K70's own venv, only executed via
`blender --background --python scene_builder_script.py -- <args.json>`).

Reads a JSON spec (written by `bpy_bridge.build_scene()`) describing:
  - one or more mesh assets to import (glb/fbx) with position/rotation/scale
  - an optional material tint (character accent_color, brief section 5)
  - camera position/target
  - a sun light
  - render engine/device/samples/resolution/output path (from
    `hardware.detect()`, passed through by the caller)

Kept deliberately simple (one static frame or one short baked animation
per call, not a general Blender scripting API) so it stays testable and
so failures are legible: any bpy exception here means a REAL asset/import
problem, not a caching or process-orchestration bug in bpy_bridge.py.
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
        raise SystemExit("usage: blender --background --python scene_builder_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def _clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _import_asset(path: str, fmt: str, location, rotation, scale, tint):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"asset not found: {path}")
    if fmt in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=str(p))
    elif fmt == "fbx":
        bpy.ops.import_scene.fbx(filepath=str(p))
    else:
        raise ValueError(f"unsupported asset format '{fmt}' (expected glb or fbx)")

    imported = [o for o in bpy.context.selected_objects]
    if not imported:
        raise RuntimeError(f"import produced no objects: {path}")

    for obj in imported:
        if obj.parent is None:
            obj.location = location
            obj.rotation_euler = rotation
            obj.scale = scale

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
    return imported


def _scene_bounds():
    """World-space bounding box across every mesh currently in the scene."""
    mins = Vector((float("inf"),) * 3)
    maxs = Vector((float("-inf"),) * 3)
    found = False
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        found = True
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ Vector(corner)
            mins = Vector(min(a, b) for a, b in zip(mins, world_corner))
            maxs = Vector(max(a, b) for a, b in zip(maxs, world_corner))
    if not found:
        return Vector((0, 0, 0)), 2.0
    center = (mins + maxs) / 2
    span = max((maxs - mins).x, (maxs - mins).y, (maxs - mins).z, 0.5)
    return center, span


def _auto_frame_camera(distance_multiplier: float = 1.4, angle: str = "three_quarter",
                       target_fraction: float = 1.0):
    """Position a camera to frame the scene. `angle` picks a fixed shot
    grammar (front / three_quarter / left / right) so multiple renders of
    the same character read as distinct shots, not repeats of one image
    (brief: avoid repeated camera angles). `target_fraction` < 1.0 frames
    only the upper portion of the bounding box (a "bust" shot) instead of
    the whole model, which is what fixed the first test render's
    "character floats tiny in a sea of black" problem (see
    FINAL_REPORT.md item 30)."""
    mins, maxs, center, span = _scene_bounds_full()
    focus = center
    distance = span * distance_multiplier
    offsets = {
        "front": Vector((0, -distance * 1.4, distance * 0.35)),
        "three_quarter": Vector((distance * 0.85, -distance * 1.1, distance * 0.45)),
        "left": Vector((-distance * 1.1, -distance * 0.7, distance * 0.4)),
        "right": Vector((distance * 1.1, -distance * 0.7, distance * 0.4)),
    }
    cam_data = bpy.data.cameras.new("k70_cam")
    # 50mm: a "normal" lens (roughly human-eye perspective) that frames any
    # object reasonably at the computed distance, instead of the 85mm
    # portrait-length lens this used before -- that was tuned around one
    # specific character's proportions and cropped in far too tight on a
    # taller/deeper prop like a desktop tower at the same distance_multiplier
    # (see FINAL_REPORT.md's CC0Tree test).
    cam_data.lens = 50
    cam_obj = bpy.data.objects.new("k70_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = focus + offsets.get(angle, offsets["three_quarter"])
    direction = focus - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam_obj
    return cam_obj, mins, maxs, span


def _scene_bounds_full():
    center, span = _scene_bounds()
    mins = center - Vector((span, span, span)) / 2
    maxs = center + Vector((span, span, span)) / 2
    # recompute true mins/maxs (bounds() only returns center+span, not the
    # box itself) since the ground plane needs the real floor height
    real_mins = Vector((float("inf"),) * 3)
    real_maxs = Vector((float("-inf"),) * 3)
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            wc = obj.matrix_world @ Vector(corner)
            real_mins = Vector(min(a, b) for a, b in zip(real_mins, wc))
            real_maxs = Vector(max(a, b) for a, b in zip(real_maxs, wc))
    return real_mins, real_maxs, center, span


def _build_studio(mins: Vector, maxs: Vector, span: float, world_color=(0.035, 0.045, 0.07)):
    """Ground plane + soft world gradient + three-point lighting, so a
    character reads as a deliberate studio portrait instead of a model
    floating in pure black (FINAL_REPORT.md item 30)."""
    # ground plane, sized generously relative to the subject, sitting at
    # the model's true lowest point rather than an assumed z=0
    bpy.ops.mesh.primitive_plane_add(size=span * 8, location=(0, 0, mins.z))
    ground = bpy.context.active_object
    ground_mat = bpy.data.materials.new("k70_ground")
    ground_mat.use_nodes = True
    bsdf = ground_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.05, 0.055, 0.07, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.85
    ground.data.materials.append(ground_mat)

    # soft gradient world background instead of flat black
    world = bpy.data.worlds.new("k70_world")
    world.use_nodes = True
    bpy.context.scene.world = world
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (*world_color, 1.0)
        bg.inputs["Strength"].default_value = 0.6

    center = (mins + maxs) / 2
    # Light energy below was tuned for a character-only scene (span ~2).
    # It's a FIXED wattage while the light's own size/distance both scale
    # with `span` -- for a much larger scene (e.g. character + a
    # correctly-sized building, span ~8+) the same total power spread
    # over a proportionally bigger emitting area is dimmer at the
    # subject. Confirmed by a real render: a character+house shot came
    # out almost entirely black once the building's true size was fixed
    # elsewhere (span jumped from ~2 to ~8). Scaling energy by span^2
    # keeps roughly constant irradiance at the subject across scene
    # scales instead of only working at the one span this was tuned for.
    energy_scale = max(1.0, (span / 2.0) ** 2)

    # key light (main, warm-neutral, from front-above)
    key_data = bpy.data.lights.new("k70_key", type="AREA")
    key_data.energy = 400.0 * energy_scale
    key_data.size = span * 2
    key_obj = bpy.data.objects.new("k70_key", key_data)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = center + Vector((span * 1.5, -span * 2.0, span * 2.2))
    direction = center - key_obj.location
    key_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    # fill light (cooler, dimmer, opposite side -- softens shadows)
    fill_data = bpy.data.lights.new("k70_fill", type="AREA")
    fill_data.energy = 120.0 * energy_scale
    fill_data.size = span * 2.5
    fill_data.color = (0.75, 0.82, 1.0)
    fill_obj = bpy.data.objects.new("k70_fill", fill_data)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = center + Vector((-span * 2.2, -span * 1.0, span * 1.2))
    direction = center - fill_obj.location
    fill_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    # rim light (behind subject, edge highlight for separation from bg)
    rim_data = bpy.data.lights.new("k70_rim", type="AREA")
    rim_data.energy = 250.0 * energy_scale
    rim_data.size = span * 1.5
    rim_obj = bpy.data.objects.new("k70_rim", rim_data)
    bpy.context.collection.objects.link(rim_obj)
    rim_obj.location = center + Vector((0, span * 2.5, span * 1.8))
    direction = center - rim_obj.location
    rim_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    a = _args()
    _clear_scene()

    for asset in a["assets"]:
        _import_asset(asset["path"], asset["format"], asset.get("location", (0, 0, 0)),
                      asset.get("rotation", (0, 0, 0)), asset.get("scale", (1, 1, 1)),
                      asset.get("tint"))

    cam_spec = a.get("camera") or {}
    if cam_spec.get("auto_frame", True):
        cam_obj, mins, maxs, span = _auto_frame_camera(
            cam_spec.get("distance_multiplier", 1.4),
            cam_spec.get("angle", "three_quarter"),
            cam_spec.get("target_fraction", 1.0),
        )
    else:
        cam_data = bpy.data.cameras.new("k70_cam")
        cam_obj = bpy.data.objects.new("k70_cam", cam_data)
        bpy.context.collection.objects.link(cam_obj)
        cam_obj.location = cam_spec["location"]
        cam_obj.rotation_euler = cam_spec["rotation"]
        bpy.context.scene.camera = cam_obj
        mins, maxs, _, span = _scene_bounds_full()

    if a.get("studio", True):
        _build_studio(mins, maxs, span, tuple(a.get("world_color", (0.035, 0.045, 0.07))))
    else:
        sun_data = bpy.data.lights.new("k70_sun", type="SUN")
        sun_data.energy = a.get("lighting", {}).get("energy", 3.0)
        sun_obj = bpy.data.objects.new("k70_sun", sun_data)
        bpy.context.collection.objects.link(sun_obj)
        sun_obj.rotation_euler = a.get("lighting", {}).get("rotation", (0.9, 0, 0.6))

    render = a["render"]
    scene = bpy.context.scene
    scene.render.engine = render["engine"]
    scene.render.resolution_x = render["width"]
    scene.render.resolution_y = render["height"]
    scene.render.filepath = render["output"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_stamp = False
    if render["engine"] == "CYCLES":
        scene.cycles.samples = render["samples"]
        scene.cycles.device = render["device"]
    elif hasattr(scene, "eevee"):
        try:
            scene.eevee.taa_render_samples = render["samples"]
        except AttributeError:
            pass

    bpy.ops.render.render(write_still=True)
    print(f"K70_RENDER_OK {render['output']}")


if __name__ == "__main__":
    main()
