"""K70 VOXEL V4 -- hero frame scene. Runs inside Blender.

ONE hand-composed cinematic frame proving the CC0-asset + K70-adapter
architecture, before anything gets animated. Reuses, unmodified:
  - _voxel_human_v3_script.py's character builder (John + NPCs, same rig)
  - k70_asset_adapter.py (Kenney CC0 geometry, flat-shaded + nearest-
    neighbor textured + floor-origin-corrected)
  - _k70_block_kit.py (K70's own signage/sidewalk/distant-skyline pieces,
    used to fill gaps and guarantee full-horizon block-world coverage)
  - lighting_presets.setup_block_world_v31 (flat sky, no HDRI photo)

    blender --background --python _voxel_v4_hero_scene.py -- <args.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
from mathutils import Vector

import _voxel_human_v3_script as vh
import _k70_block_kit as bk
import k70_asset_adapter as ka
import lighting_presets as lp


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _voxel_v4_hero_scene.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def stack_kenney_building(name, floor_files, location, floors_glob="city-kit-commercial",
                          floor_height=1.29, rotation_z_deg=0.0, scale=1.0):
    """NOT USED for actual stacking anymore -- verified via an isolated
    render that 'building-a.glb' etc. are already COMPLETE small buildings
    (base+windows+roof cap baked in), not bare floor slices. Stacking
    copies produced 3 separate gapped mini-buildings, not one seamless
    tower (root-caused via a dedicated isolation test, not guessed).
    Kept only as a single-instance passthrough; see row_of_buildings()
    for the actual hero-building approach."""
    obj = ka.import_cc0_asset("kenney", floors_glob, floor_files[0], f"{name}_b0",
                              location=location, rotation_z_deg=rotation_z_deg, scale=scale,
                              pack_url="https://kenney.nl/assets/city-kit-commercial")
    return [obj]


def row_of_buildings(name, letters, start, step, rotation_z_deg=0.0, scale=1.0):
    """A row of DIFFERENT complete Kenney building instances side by side
    -- reads as a real commercial block (varied 1-3 story shopfronts),
    the way an actual street looks, instead of one artificially-stacked
    tower."""
    objs = []
    for i, letter in enumerate(letters):
        loc = (start[0] + step[0] * i, start[1] + step[1] * i, start[2])
        obj = ka.import_cc0_asset("kenney", "city-kit-commercial", f"building-{letter}.glb", f"{name}_{i}",
                                  location=loc, rotation_z_deg=rotation_z_deg, scale=scale,
                                  pack_url="https://kenney.nl/assets/city-kit-commercial")
        objs.append(obj)
    return objs


def main():
    a = _args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    W, H = a["width"], a["height"]
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = W
    scene.render.resolution_y = H
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_stamp = False
    scene.eevee.taa_render_samples = a.get("samples", 64)
    scene.eevee.use_raytracing = True

    # ---- ground ---- #
    bk.build_distant_ground("ground", (0, 3, 0), size=40, material="concrete")

    # ---- street: real Kenney road tiles (1m grid, confirmed via bbox check) ---- #
    for i, y in enumerate([-2, -1, 0, 1, 2, 3, 4, 5, 6, 7]):
        fname = "road-crossing.glb" if y == 1 else "road-straight.glb"
        ka.import_cc0_asset("kenney", "city-kit-roads", fname, f"road_{i}",
                            location=(0.0, y, 0.001), rotation_z_deg=90,
                            pack_url="https://kenney.nl/assets/city-kit-roads")
    # sidewalks either side (K70's own concrete strip -- no Kenney sidewalk tile in this kit)
    bk.build_sidewalk_segment("sw_l", (-1.35, 2.5, 0), length=11.0, width=0.9)
    bk.build_sidewalk_segment("sw_r", (1.35, 2.5, 0), length=11.0, width=0.9)

    # ---- HERO row (left, midground) -- 2 varied complete Kenney buildings + shopfront ---- #
    row_of_buildings("heroL", ["a", "e"], (-2.55, 1.9, 0), (0.0, 1.9, 0), rotation_z_deg=0, scale=2.6)
    ka.import_cc0_asset("kenney", "city-kit-commercial", "detail-awning-wide.glb", "awningL",
                        location=(-1.55, 1.35, 1.7), rotation_z_deg=90, scale=1.4,
                        pack_url="https://kenney.nl/assets/city-kit-commercial")
    bk.build_signboard("signL", (-1.55, 1.32, 2.4), "sign_cafe", w=0.7, h=0.3)

    # ---- second row (right, midground) -- 2 more varied buildings ---- #
    row_of_buildings("heroR", ["b", "h"], (2.55, 2.6, 0), (0.0, 2.0, 0), rotation_z_deg=180, scale=2.6)
    ka.import_cc0_asset("kenney", "city-kit-commercial", "detail-overhang.glb", "overhangR",
                        location=(1.55, 2.0, 1.75), rotation_z_deg=-90, scale=1.4,
                        pack_url="https://kenney.nl/assets/city-kit-commercial")
    bk.build_signboard("signR", (1.55, 2.03, 2.45), "sign_k70bank", w=0.75, h=0.3)

    # ---- background skyscraper (genuinely tall single-piece tower) + low-detail skyline fill ---- #
    ka.import_cc0_asset("kenney", "city-kit-commercial", "building-skyscraper-a.glb", "skyA",
                        location=(-0.9, 7.5, 0), scale=1.8,
                        pack_url="https://kenney.nl/assets/city-kit-commercial")
    ka.import_cc0_asset("kenney", "city-kit-commercial", "building-skyscraper-c.glb", "skyB",
                        location=(0.9, 8.0, 0), scale=1.6,
                        pack_url="https://kenney.nl/assets/city-kit-commercial")
    for i, (dx, dy, s) in enumerate([(-3.2, 7.0, 2.4), (-2.0, 9.5, 2.0), (1.5, 8.0, 2.6),
                                     (3.0, 9.0, 2.2), (0.5, 10.5, 2.8)]):
        letter = "abcdefghijklmn"[i % 14]
        ka.import_cc0_asset("kenney", "city-kit-commercial", f"low-detail-building-{letter}.glb", f"skyline{i}",
                            location=(dx, dy, 0), scale=s,
                            pack_url="https://kenney.nl/assets/city-kit-commercial")
    bk.build_distant_skyline("far_sky", (0, 14, 0), n_buildings=6, spread=12, seed=5)

    # ---- street furniture: real Kenney lamp/traffic-light/bin + K70 planter/fence ---- #
    ka.import_cc0_asset("kenney", "city-kit-roads", "light-curved.glb", "lamp1",
                        location=(-1.35, 0.4, 0), rotation_z_deg=90,
                        pack_url="https://kenney.nl/assets/city-kit-roads")
    ka.import_cc0_asset("kenney", "city-kit-roads", "traffic-light.glb", "tlight1",
                        location=(1.35, 0.6, 0), rotation_z_deg=-90,
                        pack_url="https://kenney.nl/assets/city-kit-roads")
    ka.import_cc0_asset("kenney", "city-kit-roads", "dumpster.glb", "bin1",
                        location=(1.35, 5.6, 0), rotation_z_deg=0,
                        pack_url="https://kenney.nl/assets/city-kit-roads")
    bk.build_planter("planter1", (-1.35, -1.3, 0))

    # ---- vehicles: TWO, clearly visible (foreground + midground) ---- #
    ka.import_cc0_asset("kenney", "car-kit", "taxi.glb", "taxi_fg",
                        location=(1.9, -1.6, 0), rotation_z_deg=100, scale=1.3,
                        pack_url="https://kenney.nl/assets/car-kit")
    ka.import_cc0_asset("kenney", "car-kit", "delivery.glb", "van_mg",
                        location=(2.6, -1.15, 0), rotation_z_deg=100, scale=0.85,
                        pack_url="https://kenney.nl/assets/car-kit")

    # ---- tree (single -- a second tree kept occluding the CAFE building at
    # every position tried; simplified per anti-bug-loop rather than
    # continuing to chase it) ---- #
    ka.import_cc0_asset("kenney", "nature-kit", "tree_blocks.glb", "tree1",
                        location=(-1.5, 1.5, 0), scale=1.8,
                        pack_url="https://kenney.nl/assets/nature-kit")

    # ---- characters: John (hero) + 3 NPCs ---- #
    root, joints = vh.build_voxel_human_v3("john", root_location=(0.45, 0.7, 0), root_rotation_z=vh.deg(-15))
    vh.animate_idle(root, joints, start=0, length=10)

    npc_specs = [
        ("sarah", (-0.95, 2.6, 0), 40, "idle"),
        ("worker", (0.85, 1.7, 0), -150, "walk"),
        ("banker", (1.15, 3.6, 0), 190, "idle"),
    ]
    for role, loc, rot, anim in npc_specs:
        r, j = vh.build_voxel_human_v3(role, root_location=loc, root_rotation_z=vh.deg(rot))
        if anim == "walk":
            vh.animate_walk(r, j, start=0, length=22, n_cycles=1, stride_deg=22, forward_dist=0.3)
        else:
            vh.animate_idle(r, j, start=0, length=10)

    scene.frame_set(5)

    # ---- lighting: golden-hour block_world_v31 + a couple of warm practicals ---- #
    lp.setup_block_world_v31(sun_rotation=[1.2, 0, 0.85], sun_energy=4.2,
                             sky_color=[0.55, 0.60, 0.72], sun_color=[1.0, 0.86, 0.62],
                             fill_color=[0.5, 0.55, 0.78])
    for name, loc in [("glow1", (-1.15, 1.35, 1.1)), ("glow2", (0.1, 3.05, 1.35))]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        o = bpy.context.active_object
        o.name = name
        o.scale = (0.18, 0.02, 0.12)
        bpy.ops.object.transform_apply(scale=True)
        mat = bpy.data.materials.new(f"{name}_mat")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (1.0, 0.82, 0.5, 1.0)
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (1.0, 0.8, 0.45, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 2.2
        o.data.materials.append(mat)

    # ---- camera ---- #
    cam_data = bpy.data.cameras.new("hero_cam")
    cam_data.lens = a.get("lens", 38)
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = a.get("fstop", 3.2)
    cam_obj = bpy.data.objects.new("hero_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    focus = bpy.data.objects.new("focus", None)
    bpy.context.collection.objects.link(focus)
    cam_data.dof.focus_object = focus

    cam_loc = Vector(a["camera_location"])
    look_at = Vector(a["camera_look_at"])
    cam_obj.location = cam_loc
    cam_obj.rotation_euler = (look_at - cam_loc).to_track_quat("-Z", "Y").to_euler()
    focus.location = Vector(a.get("focus_at", a["camera_look_at"]))

    out_path = Path(a["output_path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(out_path)
    bpy.ops.render.render(write_still=True)

    provenance_path = Path(a["provenance_path"])
    provenance_path.write_text(json.dumps(ka.dump_provenance(), indent=2), encoding="utf-8")

    print(f"K70_V4_HERO_RENDER_OK {out_path}")


if __name__ == "__main__":
    main()
