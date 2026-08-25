"""K70 AUTO SCENE DIRECTOR -- Blender-side scene builder + REAL visibility/
occlusion testing. Runs inside Blender.

Takes a scene_plan JSON (from director/composition.py), builds it by
reusing, UNMODIFIED:
  - _voxel_human_v3_script.py (hero + NPCs, same rig)
  - k70_asset_adapter.py (Kenney CC0 geometry)
  - _k70_block_kit.py (K70 signage/sidewalk/ground pieces)
  - lighting_presets.setup_block_world_v31

Then computes, using Blender's OWN camera-projection and ray-casting APIs
(bpy_extras.object_utils.world_to_camera_view + scene.ray_cast) -- not
guessed/hand-tuned coordinates -- a visibility_report per required entity:
in-frame bounds, screen coverage, and occlusion. This report is written to
JSON. Optionally (mode=="render") also renders a real image; mode==
"check" only builds geometry and runs the projection/raycast pass (no
shading needed, much faster than a real render) -- this is what makes it
cheap to test many candidates.

    blender --background --python _director_build_and_check.py -- <args.json>
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

import _voxel_human_v3_script as vh
import _k70_block_kit as bk
import k70_asset_adapter as ka
import lighting_presets as lp

TRACKED = {}  # name -> {"kind":..., "mesh_objs":[bpy objects], "point": Vector (key point, e.g. face/center)}


def _args():
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def _track(name, kind, mesh_objs, key_point):
    if mesh_objs:
        TRACKED[name] = {"kind": kind, "mesh_objs": mesh_objs, "point": Vector(key_point)}


def _collect_meshes(obj):
    out = []
    if obj.type == "MESH":
        out.append(obj)
    for c in obj.children:
        out.extend(_collect_meshes(c))
    return out


def build_hero(plan):
    h = plan["hero"]
    root, joints = vh.build_voxel_human_v3(h["role"], root_location=tuple(h["location"]),
                                          root_rotation_z=vh.deg(h["rotation_z_deg"]))
    vh.animate_idle(root, joints, start=0, length=10)
    bpy.context.scene.frame_set(5)
    meshes = _collect_meshes(root)
    face_pt = joints["head"].matrix_world.translation
    _track("hero", "hero", meshes, face_pt)
    return root


def build_npcs(plan):
    for i, npc in enumerate(plan.get("npcs", [])):
        root, joints = vh.build_voxel_human_v3(npc["role"], root_location=tuple(npc["location"]),
                                               root_rotation_z=vh.deg(npc["rotation_z_deg"]))
        if npc.get("animation") == "walk":
            vh.animate_walk(root, joints, start=0, length=20, n_cycles=1, stride_deg=20, forward_dist=0.2)
        else:
            vh.animate_idle(root, joints, start=0, length=10)
        bpy.context.scene.frame_set(5)
        meshes = _collect_meshes(root)
        _track(f"npc_{i}_{npc['role']}", "npc", meshes, root.matrix_world.translation + Vector((0, 0, 1.4)))


def build_vehicles(plan):
    for i, v in enumerate(plan.get("vehicles", [])):
        anchor = ka.import_cc0_asset("kenney", "car-kit", v["file"], f"veh_{i}",
                                     location=tuple(v["location"]), rotation_z_deg=v["rotation_z_deg"],
                                     scale=v.get("scale", 1.0), pack_url="https://kenney.nl/assets/car-kit")
        if v.get("color"):
            for name in anchor.get("k70_mesh_names", []):
                o = bpy.data.objects.get(name)
                if o and o.data.materials:
                    bsdf = o.data.materials[0].node_tree.nodes.get("Principled BSDF")
                    if bsdf and "body" in name.lower():
                        bsdf.inputs["Base Color"].default_value = (*v["color"], 1.0)
        meshes = [bpy.data.objects[n] for n in anchor.get("k70_mesh_names", []) if n in bpy.data.objects]
        _track(f"vehicle_{i}", "vehicle", meshes, Vector(v["location"]) + Vector((0, 0, 0.5)))


def build_buildings(plan):
    for i, b in enumerate(plan.get("buildings", [])):
        # Atmospheric depth: the "far" band gets a cool, slightly
        # desaturated tint (aerial perspective) so background separation
        # reads even without real volumetric fog -- reuses
        # k70_asset_adapter's existing palette_tint/saturation hook, no
        # new material system needed.
        tint, sat = (None, 1.0)
        if b.get("depth_band") == "far":
            tint, sat = (0.55, 0.62, 0.78), 0.55
        elif b.get("depth_band") == "mid":
            tint, sat = (0.65, 0.68, 0.78), 0.75
        anchor = ka.import_cc0_asset("kenney", "city-kit-commercial", f"building-{b['letter']}.glb", f"bld_{i}",
                                     location=tuple(b["location"]), rotation_z_deg=b["rotation_z_deg"],
                                     scale=b.get("scale", 2.2), pack_url="https://kenney.nl/assets/city-kit-commercial",
                                     palette_tint=tint, saturation=sat)
        meshes = [bpy.data.objects[n] for n in anchor.get("k70_mesh_names", []) if n in bpy.data.objects]
        _track(f"building_{i}", "building", meshes, Vector(b["location"]) + Vector((0, 0, 1.5)))
    for i, sign in enumerate(plan.get("signage", [])):
        sign_loc = tuple(sign["location"])
        sign_obj = bk.build_signboard(f"sign_{i}", sign_loc, sign["sign_key"], w=0.75, h=0.3)
        _track(f"signage_{i}", "signage", [sign_obj], Vector(sign_loc))


def build_skyline(plan):
    for i, s in enumerate(plan.get("skyscrapers", [])):
        ka.import_cc0_asset("kenney", "city-kit-commercial", f"building-skyscraper-{s['letter']}.glb", f"sky_{i}",
                            location=tuple(s["location"]), scale=s.get("scale", 1.7),
                            pack_url="https://kenney.nl/assets/city-kit-commercial",
                            palette_tint=(0.55, 0.64, 0.80), saturation=0.6)
    for i, s in enumerate(plan.get("skyline", [])):
        ka.import_cc0_asset("kenney", "city-kit-commercial", f"low-detail-building-{s['letter']}.glb", f"far_{i}",
                            location=tuple(s["location"]), scale=s.get("scale", 2.5),
                            pack_url="https://kenney.nl/assets/city-kit-commercial",
                            palette_tint=(0.5, 0.6, 0.78), saturation=0.45)


def build_props(plan):
    # V5 never tracked street props at all -- the scorer had zero
    # visibility into them despite "street props" being a named quality
    # requirement. Tracked now (kind="prop") for environment-readability/
    # foreground-framing scoring.
    for i, p in enumerate(plan.get("props", [])):
        loc = tuple(p["location"])
        kind = p["kind"]
        anchor = None
        if kind == "streetlamp":
            anchor = ka.import_cc0_asset("kenney", "city-kit-roads", "light-curved.glb", f"prop_{i}", location=loc,
                                         pack_url="https://kenney.nl/assets/city-kit-roads")
        elif kind == "traffic_light":
            anchor = ka.import_cc0_asset("kenney", "city-kit-roads", "traffic-light.glb", f"prop_{i}", location=loc,
                                         pack_url="https://kenney.nl/assets/city-kit-roads")
        elif kind == "bin":
            anchor = ka.import_cc0_asset("kenney", "city-kit-roads", "dumpster.glb", f"prop_{i}", location=loc,
                                         pack_url="https://kenney.nl/assets/city-kit-roads")
        elif kind == "planter":
            objs = bk.build_planter(f"prop_{i}", loc)  # returns a list (box + bush)
            _track(f"prop_{i}", "prop", objs, Vector(loc) + Vector((0, 0, 0.3)))
            continue
        if anchor is not None:
            meshes = [bpy.data.objects[n] for n in anchor.get("k70_mesh_names", []) if n in bpy.data.objects]
            _track(f"prop_{i}", "prop", meshes, Vector(loc) + Vector((0, 0, 0.3)))
    for i, veg in enumerate(plan.get("vegetation", [])):
        # tree_blocks.glb's "leafsGreen" material color bug is fixed
        # generally inside k70_asset_adapter._force_flat_and_crisp (keyed
        # by material name, since this mesh also has a "woodBark"
        # material that must NOT be recolored) -- no per-call tint needed.
        anchor = ka.import_cc0_asset("kenney", "nature-kit", "tree_blocks.glb", f"tree_{i}",
                                     location=tuple(veg["location"]), scale=veg.get("scale", 2.0),
                                     pack_url="https://kenney.nl/assets/nature-kit")
        meshes = [bpy.data.objects[n] for n in anchor.get("k70_mesh_names", []) if n in bpy.data.objects]
        _track(f"vegetation_{i}", "vegetation", meshes, Vector(veg["location"]) + Vector((0, 0, 1.0)))


def build_ground_and_road(plan):
    bk.build_distant_ground("ground", (0, 3, 0), size=40, material="concrete")
    cam = plan["camera"]
    fwd = cam["forward_dir"]
    for i in range(10):
        f = 0.5 + i * 1.0
        p = (cam["location"][0] + fwd[0] * f, cam["location"][1] + fwd[1] * f, 0.001)
        ka.import_cc0_asset("kenney", "city-kit-roads",
                            "road-crossing.glb" if i == 4 else "road-straight.glb", f"road_{i}",
                            location=p, rotation_z_deg=90, pack_url="https://kenney.nl/assets/city-kit-roads")


def setup_camera(plan):
    scene = bpy.context.scene
    cam = plan["camera"]
    cam_data = bpy.data.cameras.new("director_cam")
    cam_data.lens = cam["lens"]
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = cam["fstop"]
    cam_obj = bpy.data.objects.new("director_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    focus = bpy.data.objects.new("focus", None)
    bpy.context.collection.objects.link(focus)
    cam_data.dof.focus_object = focus
    loc, look_at = Vector(cam["location"]), Vector(cam["look_at"])
    cam_obj.location = loc
    cam_obj.rotation_euler = (look_at - loc).to_track_quat("-Z", "Y").to_euler()
    focus.location = Vector(cam["focus_at"])
    return cam_obj


def visibility_report(cam_obj, scene):
    """The REAL visibility/occlusion pass -- world_to_camera_view for
    in-frame projection, scene.ray_cast for occlusion. No image render
    required for this, which is what makes candidate exploration cheap."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    report = {}
    for name, info in TRACKED.items():
        meshes = info["mesh_objs"]
        if not meshes:
            continue
        # screen-space bbox from all mesh vertices' world positions
        xs, ys, zs_front = [], [], []
        for o in meshes:
            for corner in _bbox_corners_world(o):
                sx, sy, sz = world_to_camera_view(scene, cam_obj, corner)
                xs.append(sx); ys.append(sy); zs_front.append(sz)
        if not xs:
            continue
        in_front = any(z > 0 for z in zs_front)
        xmin, xmax = max(0.0, min(xs)), min(1.0, max(xs))
        ymin, ymax = max(0.0, min(ys)), min(1.0, max(ys))
        raw_xmin, raw_xmax = min(xs), max(xs)
        raw_ymin, raw_ymax = min(ys), max(ys)
        in_frame = in_front and raw_xmax > 0 and raw_xmin < 1 and raw_ymax > 0 and raw_ymin < 1
        cropped = in_frame and (raw_xmin < 0 or raw_xmax > 1 or raw_ymin < 0 or raw_ymax > 1)
        coverage = max(0.0, xmax - xmin) * max(0.0, ymax - ymin) if in_frame else 0.0

        # occlusion: ray-cast from camera to the key point; occluded if the
        # first thing hit is NOT one of this entity's own meshes.
        key_pt = info["point"]
        origin = cam_obj.matrix_world.translation
        direction = (key_pt - origin)
        dist_to_target = direction.length
        direction.normalize()
        occluded = False
        if dist_to_target > 0.001:
            hit, loc, nrm, idx, hit_obj, mat = scene.ray_cast(depsgraph, origin, direction, distance=dist_to_target - 0.03)
            if hit and hit_obj is not None and hit_obj not in meshes:
                occluded = True

        report[name] = {
            "kind": info["kind"], "in_frame": bool(in_frame), "cropped": bool(cropped),
            "screen_bbox": [round(xmin, 3), round(ymin, 3), round(xmax, 3), round(ymax, 3)],
            "coverage": round(coverage, 4), "occluded": bool(occluded),
        }
    return report


def _bbox_corners_world(obj):
    return [obj.matrix_world @ Vector(c) for c in obj.bound_box]


def sky_occupancy(cam_obj, scene, samples=12):
    """Approximate empty-sky fraction in the upper half of frame by
    sampling rays through a grid and checking hit/no-hit via ray_cast --
    real geometry-based measurement, not a guess."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    cam_data = cam_obj.data
    frame = cam_data.view_frame(scene=scene)  # 4 corners in camera-local space
    frame_world = [cam_obj.matrix_world @ Vector(c) for c in frame]
    # Blender's Camera.view_frame() returns 4 points on the near/frame plane
    # in camera-local space: local X = horizontal (varies), local Y =
    # vertical (varies), local Z = depth along the view axis (CONSTANT
    # across all 4 corners). The previous version read the vertical range
    # from Z (near-constant -> a degenerate ~0 range) and pinned every
    # sample's real vertical coordinate to a single corner's Y value,
    # collapsing all samples onto one line -- which is why sky_occupancy
    # came back as exactly 1.0 for every candidate. Fixed: X/Y vary, Z is
    # fixed (any corner's Z, they're all equal).
    local = list(frame)
    xs = sorted(set(round(c.x, 4) for c in local))
    ys = sorted(set(round(c.y, 4) for c in local))
    x_lo, x_hi = xs[0], xs[-1]
    y_lo, y_hi = ys[0], ys[-1]

    origin = cam_obj.matrix_world.translation
    empty = 0
    total = 0
    for iy in range(samples):
        v = 0.55 + 0.45 * (iy / max(samples - 1, 1))  # upper ~45% of frame (v: 0=mid, 1=top)
        for ix in range(samples):
            u = ix / max(samples - 1, 1)
            local_pt = Vector((x_lo + (x_hi - x_lo) * u, y_lo + (y_hi - y_lo) * v, local[0].z))
            world_pt = cam_obj.matrix_world @ local_pt
            direction = (world_pt - origin)
            direction.normalize()
            hit, *_ = scene.ray_cast(depsgraph, origin, direction, distance=60.0)
            total += 1
            if not hit:
                empty += 1
    return empty / max(total, 1)


def main():
    a = _args()
    plan = a["plan"]
    mode = a.get("mode", "check")  # "check" (geometry+visibility only) or "render"

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    W, H = a.get("width", 360), a.get("height", 640)
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = W
    scene.render.resolution_y = H
    scene.render.image_settings.file_format = "PNG"
    scene.eevee.taa_render_samples = a.get("samples", 8) if mode == "render" else 4
    scene.eevee.use_raytracing = mode == "render"

    build_ground_and_road(plan)
    build_hero(plan)
    build_npcs(plan)
    build_vehicles(plan)
    build_buildings(plan)
    build_skyline(plan)
    build_props(plan)

    _lighting_params = {k: v for k, v in plan["lighting"].items() if k != "mode"}
    if plan["lighting"].get("mode") == "golden_hour_v2":
        lp.setup_golden_hour_v2(plan["camera"]["forward_dir"], plan["camera"]["right_dir"], **_lighting_params)
    else:
        lp.setup_block_world_v31(**_lighting_params)

    if plan.get("practical_light"):
        loc = plan["practical_light"]["location"]
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        o = bpy.context.active_object
        o.scale = (0.16, 0.02, 0.10)
        bpy.ops.object.transform_apply(scale=True)
        mat = bpy.data.materials.new("practical_glow")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (1.0, 0.8, 0.45, 1.0)
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (1.0, 0.78, 0.4, 1.0)
            bsdf.inputs["Emission Strength"].default_value = a.get("practical_emission", 2.3)
        o.data.materials.append(mat)
        _track("practical_light", "light", [o], Vector(loc))

    cam_obj = setup_camera(plan)
    bpy.context.view_layer.update()

    vis = visibility_report(cam_obj, scene)
    sky_frac = sky_occupancy(cam_obj, scene, samples=a.get("sky_samples", 10))

    out = {"visibility": vis, "sky_occupancy": round(sky_frac, 3)}
    Path(a["report_path"]).write_text(json.dumps(out, indent=2), encoding="utf-8")

    if mode == "render":
        out_path = Path(a["output_path"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)

    print("K70_DIRECTOR_CHECK_OK" if mode == "check" else "K70_DIRECTOR_RENDER_OK")


if __name__ == "__main__":
    main()
