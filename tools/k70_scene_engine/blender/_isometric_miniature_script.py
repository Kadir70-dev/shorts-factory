"""K70 Visual Engine V2 -- Style 6: Isometric Miniature World. Runs inside
Blender.

Integration note (real, not a shortcut taken lightly): BuildingNodes
(Durman/BuildingNodes, license-clear per V2_LICENSE_MANIFEST.md) was
downloaded and inspected first. Its own README requires three manual GUI
steps (hand-model a "panel," hand-build a "building style" in its custom
node editor, hand-model a "base mesh") with NO bundled example .blend/
preset shipped in the release zip -- there is no scriptable one-liner to
generate a building from it, only a ~3200-line custom NodeTree/Node/Socket
type system meant to be driven interactively. Building a minimal working
node graph blind, from source alone, risked exactly the kind of open-ended
undocumented-internals debugging the brief explicitly forbids (the Thomas
Rig precedent). Per the brief's own 10-minute anti-bug-loop rule, this was
recognized early and NOT pursued -- falling back to the same reliable
beveled-box construction technique already proven across every other style
this project, applied to a real isometric camera + a small money-flow
economy instead.

    blender --background --python _isometric_miniature_script.py -- <args.json>
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _isometric_miniature_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def _material(name, color, roughness=0.55, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def _beveled_box(name, size, location, material, bevel=0.03, segments=3):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(scale=True)
    bev = obj.modifiers.new("bevel", type="BEVEL")
    bev.width = bevel
    bev.segments = segments
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.materials.append(material)
    # Real bug found and fixed during this style's testing: transform_apply
    # bakes the object's CREATION location into the mesh's absolute vertex
    # data and resets matrix_basis to identity -- so the object's pivot for
    # any FUTURE scale keyframe sits at WORLD ORIGIN, not its own visual
    # center. A money-flow block scaled 0.2 for its pop-in/out beat was
    # visibly yanked toward world (0,0,0) instead of squashing in place
    # (confirmed via a bound-box-center diagnostic: center == creation_loc
    # * scale_factor). Re-centering the origin to the mesh's own geometry
    # fixes scale AND location keyframes to behave as expected for every
    # future animated use of this helper.
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
    bpy.ops.object.select_all(action='DESELECT')
    return obj


def build_entity(name, kind, location, palette):
    """A small labeled miniature building for one economic entity. Each
    kind gets a distinct silhouette (roof shape / accent block) so the
    miniature world reads at a glance even from a fixed isometric angle,
    without needing readable text labels baked into the 3D scene."""
    wall = _material(f"{name}_wall", palette["wall"], roughness=0.75)
    accent = _material(f"{name}_accent", palette["accent"], roughness=0.4, metallic=0.25)

    w, d, h = palette.get("size", (0.9, 0.9, 0.7))
    body = _beveled_box(f"{name}_body", (w, d, h), (location[0], location[1], location[2] + h / 2), wall)
    objs = [body]

    if kind == "bank":  # columned facade + pediment, same language as the voxel bank
        ped = _beveled_box(f"{name}_ped", (w * 1.08, d * 1.08, h * 0.18),
                           (location[0], location[1], location[2] + h + h * 0.09), accent)
        objs.append(ped)
    elif kind == "house":  # peaked roof accent block
        roof = _beveled_box(f"{name}_roof", (w * 0.95, d * 0.95, h * 0.35),
                            (location[0], location[1], location[2] + h + h * 0.175), accent, bevel=0.05)
        objs.append(roof)
    elif kind == "employer":  # tall office block, flat accent cap
        cap = _beveled_box(f"{name}_cap", (w * 0.5, d * 0.5, h * 0.12),
                           (location[0], location[1], location[2] + h + h * 0.06), accent)
        objs.append(cap)
    elif kind == "business":  # storefront awning accent
        awning = _beveled_box(f"{name}_awning", (w * 1.15, d * 0.35, h * 0.1),
                              (location[0], location[1] - d * 0.5, location[2] + h * 0.7), accent)
        objs.append(awning)
    elif kind == "investor":  # small tower + spire accent
        spire = _beveled_box(f"{name}_spire", (w * 0.18, d * 0.18, h * 0.5),
                             (location[0], location[1], location[2] + h + h * 0.25), accent, bevel=0.02)
        objs.append(spire)
    elif kind == "worker":  # small house, chimney accent
        chim = _beveled_box(f"{name}_chim", (w * 0.15, d * 0.15, h * 0.35),
                            (location[0] + w * 0.3, location[1], location[2] + h + h * 0.175), accent, bevel=0.015)
        objs.append(chim)
    return objs


def build_money_block(name, location, color):
    mat = _material(f"{name}_mat", color, roughness=0.3, metallic=0.5)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.6  # small readable "pop" against the muted palette
    return _beveled_box(name, (0.14, 0.14, 0.10), location, mat, bevel=0.02, segments=3)


def key(obj, frame, loc=None, scale=None):
    bpy.context.scene.frame_set(frame)
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert(data_path="location", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)


def animate_money_flow(flows):
    """Each flow: {from: [x,y,z], to: [x,y,z], f_start, f_end, color}.
    A small money block pops in at the source, travels a gentle arc to
    the destination, and pops out -- the brief's 'show money physically
    moving between entities' requirement.

    Real bug found and fixed during testing: _beveled_box used to leave the
    object's origin at world (0,0,0) after transform_apply (creation
    location baked straight into the mesh's absolute vertex data), so any
    later SCALE keyframe pivoted around world origin instead of the
    object's own center -- confirmed via a bound-box-center diagnostic
    (center == creation_loc * scale_factor): a 0.2-scale pop-in keyframe
    visibly yanked the block toward world (0,0,0) instead of squashing in
    place. Fixed at the root in _beveled_box itself (ORIGIN_GEOMETRY
    re-centering), so this function can now use plain ABSOLUTE world
    locations for its keyframes, as originally intended."""
    for i, flow in enumerate(flows):
        m = build_money_block(f"flow_{i}", flow["from"], flow.get("color", (0.75, 0.6, 0.2)))
        f0, f1 = flow["f_start"], flow["f_end"]
        mid_z = max(flow["from"][2], flow["to"][2]) + 0.35
        mid = ((flow["from"][0] + flow["to"][0]) / 2, (flow["from"][1] + flow["to"][1]) / 2, mid_z)
        key(m, f0, loc=tuple(flow["from"]), scale=(0.2, 0.2, 0.2))
        key(m, f0 + 3, loc=tuple(flow["from"]), scale=(1, 1, 1))
        key(m, (f0 + f1) // 2, loc=mid, scale=(1, 1, 1))
        key(m, f1 - 3, loc=tuple(flow["to"]), scale=(1, 1, 1))
        key(m, f1, loc=tuple(flow["to"]), scale=(0.2, 0.2, 0.2))


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
            scene.eevee.use_raytracing = render.get("raytracing", True)
        except AttributeError:
            pass

    ground_mat = _material("iso_ground", (0.42, 0.55, 0.38), roughness=0.85)
    bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.data.materials.append(ground_mat)

    road_mat = _material("iso_road", (0.35, 0.34, 0.33), roughness=0.8)
    for x0, y0, x1, y1 in a.get("roads", []):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        length = max(abs(x1 - x0), abs(y1 - y0), 0.3)
        width = 0.35
        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, 0.005))
        r = bpy.context.active_object
        if abs(x1 - x0) >= abs(y1 - y0):
            r.scale = (length, width, 0.01)
        else:
            r.scale = (width, length, 0.01)
        bpy.ops.object.transform_apply(scale=True)
        r.data.materials.append(road_mat)

    PALETTES = {
        "employer":  {"wall": (0.55, 0.60, 0.68), "accent": (0.20, 0.24, 0.32), "size": (0.9, 0.9, 1.1)},
        "worker":    {"wall": (0.85, 0.78, 0.62), "accent": (0.55, 0.30, 0.22), "size": (0.6, 0.6, 0.45)},
        "bank":      {"wall": (0.82, 0.80, 0.74), "accent": (0.60, 0.50, 0.20), "size": (1.1, 0.9, 0.75)},
        "business":  {"wall": (0.70, 0.35, 0.30), "accent": (0.85, 0.75, 0.40), "size": (0.8, 0.7, 0.55)},
        "investor":  {"wall": (0.30, 0.32, 0.38), "accent": (0.70, 0.72, 0.78), "size": (0.55, 0.55, 1.3)},
        "house":     {"wall": (0.88, 0.85, 0.78), "accent": (0.55, 0.24, 0.20), "size": (0.7, 0.65, 0.55)},
    }

    for ent in a["entities"]:
        build_entity(ent["name"], ent["kind"], ent["location"], PALETTES[ent["kind"]])

    animate_money_flow(a.get("flows", []))

    frame_range = a.get("frame_range")
    if frame_range:
        scene.frame_start, scene.frame_end = frame_range

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lighting_presets import apply_hdri_world
    apply_hdri_world(a.get("lighting_preset", "exterior_day"), rotation_z=math.radians(a.get("hdri_rotation_deg", 25)),
                     strength_override=a.get("hdri_strength", 1.0))

    # TRUE isometric camera: orthographic projection at the classic
    # 35.264deg down-tilt / 45deg yaw, not a perspective approximation.
    cam_data = bpy.data.cameras.new("iso_cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = a.get("ortho_scale", 5.5)
    cam_obj = bpy.data.objects.new("iso_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    dist = 8.0
    yaw = math.radians(a.get("yaw_deg", 45))
    pitch = math.radians(35.264)
    cam_obj.location = (dist * math.cos(pitch) * math.cos(yaw),
                        dist * math.cos(pitch) * math.sin(yaw) * -1,
                        dist * math.sin(pitch))
    look_at = Vector(a.get("look_at", [0, 0, 0.3]))
    cam_obj.rotation_euler = (Vector(cam_obj.location) - look_at).to_track_quat("Z", "Y").to_euler()
    scene.camera = cam_obj

    if a.get("orbit_deg"):
        orbit = a["orbit_deg"]
        f0, f1 = frame_range
        for frac, frame in ((0.0, f0), (1.0, f1)):
            yaw_i = math.radians(a.get("yaw_deg", 45) + orbit * frac)
            loc = (dist * math.cos(pitch) * math.cos(yaw_i),
                  dist * math.cos(pitch) * math.sin(yaw_i) * -1,
                  dist * math.sin(pitch))
            scene.frame_set(frame)
            cam_obj.location = loc
            cam_obj.rotation_euler = (Vector(loc) - look_at).to_track_quat("Z", "Y").to_euler()
            cam_obj.keyframe_insert(data_path="location", frame=frame)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
        for fc in cam_obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'BEZIER'
                kp.handle_left_type = 'AUTO_CLAMPED'
                kp.handle_right_type = 'AUTO_CLAMPED'

    out_dir = Path(render["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    n_frames = a.get("n_frames", 1)
    def _done(p: Path) -> bool:
        return p.exists() and p.stat().st_size > 1024
    fs, fe = scene.frame_start, scene.frame_end
    for i in range(n_frames):
        out_path = out_dir / f"frame_{i:03d}.png"
        if _done(out_path):
            print(f"  [resume] frame_{i:03d} already present, skipping")
            continue
        t = fs + (fe - fs) * i / max(n_frames - 1, 1)
        scene.frame_set(int(round(t)))
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
    print(f"K70_ISOMETRIC_RENDER_OK {out_dir} frames={n_frames}")


if __name__ == "__main__":
    main()
