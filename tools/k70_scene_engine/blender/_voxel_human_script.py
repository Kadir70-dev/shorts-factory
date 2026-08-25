"""K70 PREMIUM STYLIZED VOXEL HUMANS -- runs inside Blender.

Direction change (explicit, this session): MB-Lab organic humans are
FROZEN/archived, not deleted -- too uncanny for K70's style. This
builds a NEW, deliberately different character system: beveled-box
"premium blocky" characters (think high-end stylized/low-poly, not a
literal Minecraft voxel grid and not a cube-blob mascot).

Architecture is intentionally the simplest thing that can work well:
every body part is a beveled cube/box MESH, parented directly to a
plain Empty (no armature, no bone retargeting, no skinning weights --
that whole class of bug from tonight's MB-Lab work does not exist
here by construction). Animation is authored directly as object-level
keyframes on the Empties, the same reliable technique that fixed the
MB-Lab conversational-gesture animation earlier tonight.

    blender --background --python _voxel_human_script.py -- <args.json>
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
import bmesh
from mathutils import Vector


def _args() -> dict:
    argv = sys.argv
    idx = argv.index("--") if "--" in argv else -1
    if idx == -1 or idx + 1 >= len(argv):
        raise SystemExit("usage: blender --background --python _voxel_human_script.py -- <args.json>")
    return json.loads(Path(argv[idx + 1]).read_text(encoding="utf-8"))


def _material(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def _beveled_box(name, size, location, material, bevel=0.035):
    # Real bug found (first test render): scattered/disconnected body
    # parts. Root-caused to bpy.ops.object.transform_apply(scale=True)
    # operating on Blender's SELECTED-objects set, not just the newly
    # created one -- without an explicit deselect-all first, objects
    # from earlier _beveled_box calls that were still selected got their
    # scale corrupted too. Explicit deselect + select-only-this-object
    # fixes it. Bevel is left as a live (unapplied) modifier -- renders
    # identically and skips the modifier_apply/active-object juggling
    # that was a second source of the same class of bug.
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # primitive_cube_add(size=1) already makes a unit cube (edge length
    # 1.0), so scale must equal the target size directly -- dividing by
    # 2 here (an earlier version of this line) halved every box, which
    # was the REAL cause of the "scattered disconnected body parts"
    # look in the first test render: joints were correctly spaced but
    # the meshes only spanned half that distance.
    obj.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(scale=True)
    bev = obj.modifiers.new("bevel", type="BEVEL")
    bev.width = bevel
    bev.segments = 3
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.materials.append(material)
    bpy.ops.object.select_all(action='DESELECT')
    return obj


def _import_gltf(path, location=(0, 0, 0), rotation_z_deg=0.0, scale=1.0, name_prefix=""):
    """Real Poly Haven CC0 furniture/prop import (gltf+bin, downloaded
    under vendor/polyhaven/). Returns the list of newly-imported objects,
    parented under one Empty so the whole asset moves/scales as a unit."""
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.gltf(filepath=str(path))
    new_objs = [o for o in bpy.data.objects if o.name not in before]
    anchor = bpy.data.objects.new(f"{name_prefix}_anchor", None)
    bpy.context.collection.objects.link(anchor)
    anchor.location = location
    anchor.rotation_euler = (0, 0, math.radians(rotation_z_deg))
    anchor.scale = (scale, scale, scale)
    for o in new_objs:
        if o.parent is None:
            o.parent = anchor
    return anchor, new_objs


def _import_fbx(path, location=(0, 0, 0), rotation_z_deg=0.0, scale=1.0, name_prefix="",
                fallback_color=(0.22, 0.42, 0.16)):
    """Real CC0Tree CC0 FBX prop import (vegetation/props, vendor/CC0Tree/Assets).
    Real issue found and fixed: this fbx references an embedded texture
    (PG_98885e75.png) that is not actually present on disk anywhere in
    the vendored repo -- Blender's importer leaves the TEX_IMAGE node
    pointing at a missing image, which renders as flat magenta (Blender's
    standard missing-texture color), not the tree's real green/brown. Fix:
    detect any Principled BSDF whose Base Color is fed by a missing/
    zero-size image and drive Base Color directly with a flat fallback
    color instead -- a real, deliberate fallback, not a silent bug."""
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.fbx(filepath=str(path))
    new_objs = [o for o in bpy.data.objects if o.name not in before]
    for o in new_objs:
        if o.type != "MESH":
            continue
        for slot in o.material_slots:
            mat = slot.material
            if mat is None or not mat.use_nodes:
                continue
            bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None:
                continue
            bc_input = bsdf.inputs["Base Color"]
            broken = False
            if bc_input.is_linked:
                src = bc_input.links[0].from_node
                if src.type == "TEX_IMAGE":
                    img = src.image
                    if img is None or not Path(bpy.path.abspath(img.filepath)).exists() or img.size[0] == 0:
                        broken = True
                        mat.node_tree.links.remove(bc_input.links[0])
            if broken:
                bc_input.default_value = (*fallback_color, 1.0)
    anchor = bpy.data.objects.new(f"{name_prefix}_anchor", None)
    bpy.context.collection.objects.link(anchor)
    anchor.location = location
    anchor.rotation_euler = (0, 0, math.radians(rotation_z_deg))
    anchor.scale = (scale, scale, scale)
    for o in new_objs:
        if o.parent is None:
            o.parent = anchor
    return anchor, new_objs


def _import_procgen_city(blend_path, location=(0, 0, 0), rotation_z_deg=0.0, scale=1.0,
                         max_buildings=30, name_prefix="procgen"):
    """Real bene-proggen-maps output (verified headless: `bpy.ops.
    procgen_maps.generate_city()` produced 226 buildings/2858 props/309
    signs in a standalone test, saved to blend_path) linked into THIS
    scene as a distant skyline layer. Buildings' geometry is baked in
    object-local mesh coordinates with object.location==(0,0,0), so a
    single scaled/translated parent Empty correctly repositions the whole
    cluster while preserving its internal city layout."""
    import re
    pattern = re.compile(r"^ProcgenMaps_Building_\d+$")
    with bpy.data.libraries.load(str(blend_path), link=False) as (data_from, data_to):
        names = [n for n in data_from.objects if pattern.match(n)][:max_buildings]
        data_to.objects = names
    anchor = bpy.data.objects.new(f"{name_prefix}_anchor", None)
    bpy.context.collection.objects.link(anchor)
    anchor.location = location
    anchor.rotation_euler = (0, 0, math.radians(rotation_z_deg))
    anchor.scale = (scale, scale, scale)
    imported = []
    for obj in data_to.objects:
        if obj is None:
            continue
        bpy.context.collection.objects.link(obj)
        obj.parent = anchor
        imported.append(obj)
    return anchor, imported


VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor"
POLYHAVEN_DIR = VENDOR_DIR / "polyhaven"
CC0TREE_DIR = VENDOR_DIR / "CC0Tree" / "Assets"


def build_money_stack(location, n_bills=1, color=(0.16, 0.55, 0.28), name="bills"):
    """K70 Voxelizer-style finance object: a stack of beveled-box bills,
    same beveled-cube construction language as the characters/house so it
    reads as part of the same visual world, not a bolted-on prop."""
    mat = _material(f"{name}_mat", color, roughness=0.45)
    objs = []
    for i in range(max(n_bills, 0)):
        b = _beveled_box(f"{name}_{i}", (0.22, 0.34, 0.018), (location[0], location[1], location[2] + 0.02 + i * 0.02),
                         mat, bevel=0.006)
        objs.append(b)
    return objs


def build_coin_stack(location, n_coins=1, color=(0.75, 0.62, 0.22), name="coins"):
    mat = _material(f"{name}_mat", color, roughness=0.3, metallic=0.6)
    objs = []
    for i in range(max(n_coins, 0)):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.09, depth=0.02, location=(location[0], location[1], location[2] + 0.01 + i * 0.022))
        c = bpy.context.active_object
        c.name = f"{name}_{i}"
        for poly in c.data.polygons:
            poly.use_smooth = True
        c.data.materials.append(mat)
        objs.append(c)
    return objs


def build_bank_building(location=(0, 4.0, 0), scale=1.0):
    """Detailed-enough voxel bank facade: body + columns + pediment, same
    beveled-box language, distinct silhouette from the house prop."""
    wall_mat = _material("bank_wall", (0.85, 0.83, 0.78), roughness=0.7)
    column_mat = _material("bank_column", (0.92, 0.90, 0.86), roughness=0.5)
    roof_mat = _material("bank_roof", (0.30, 0.30, 0.34), roughness=0.6)
    sign_mat = _material("bank_sign", (0.55, 0.44, 0.10), roughness=0.35, metallic=0.5)

    w, d, h = 3.4 * scale, 2.0 * scale, 2.2 * scale
    body = _beveled_box("bank_body", (w, d, h), (location[0], location[1], location[2] + h / 2), wall_mat, bevel=0.03)

    ped_h = 0.35 * scale
    ped = _beveled_box("bank_pediment", (w * 1.05, d * 1.1, ped_h), (location[0], location[1], location[2] + h + ped_h / 2), roof_mat, bevel=0.02)

    cols = []
    n_cols = 5
    for i in range(n_cols):
        cx = location[0] - w / 2 + (i + 0.5) * (w / n_cols)
        col = _beveled_box(f"bank_col_{i}", (0.16 * scale, 0.16 * scale, h * 0.9),
                           (cx, location[1] - d / 2 - 0.05, location[2] + h * 0.45), column_mat, bevel=0.015)
        cols.append(col)

    sign = _beveled_box("bank_sign", (w * 0.5, 0.04, 0.3 * scale), (location[0], location[1] - d / 2 - 0.12, location[2] + h + ped_h + 0.2), sign_mat, bevel=0.01)
    return [body, ped, sign] + cols


ROLE_STYLES = {
    "john": {
        "skin": (0.82, 0.62, 0.48), "shirt": (0.18, 0.35, 0.62), "pants": (0.16, 0.16, 0.20),
        "hair": (0.25, 0.16, 0.10), "hair_style": "short",
    },
    "sarah": {
        "skin": (0.85, 0.68, 0.55), "shirt": (0.62, 0.20, 0.35), "pants": (0.15, 0.14, 0.16),
        "hair": (0.35, 0.20, 0.10), "hair_style": "long",
    },
    "banker": {
        "skin": (0.45, 0.32, 0.24), "shirt": (0.08, 0.09, 0.14), "pants": (0.06, 0.06, 0.08),
        "hair": (0.04, 0.04, 0.04), "hair_style": "short", "tie": (0.65, 0.12, 0.12),
    },
    "investor": {
        "skin": (0.42, 0.30, 0.22), "shirt": (0.55, 0.42, 0.10), "pants": (0.18, 0.16, 0.10),
        "hair": (0.05, 0.04, 0.04), "hair_style": "bun",
    },
    "worker": {
        "skin": (0.78, 0.58, 0.44), "shirt": (0.78, 0.42, 0.08), "pants": (0.22, 0.21, 0.19),
        "hair": (0.30, 0.20, 0.12), "hair_style": "cap",
    },
    "business_owner": {
        "skin": (0.40, 0.28, 0.20), "shirt": (0.10, 0.28, 0.18), "pants": (0.08, 0.08, 0.10),
        "hair": (0.03, 0.03, 0.03), "hair_style": "long",
    },
}

# Body proportions in meters, shared rig topology across all roles.
H = 1.75  # total standing height target
HEAD = 0.30
NECK = 0.04
TORSO_H = 0.55
TORSO_W = 0.42
TORSO_D = 0.22
HIP_W = 0.36
LEG_UP_H = 0.42
LEG_LO_H = 0.40
FOOT_H = 0.10
ARM_UP_H = 0.34
ARM_LO_H = 0.30
ARM_W = 0.13
HAND = 0.13


def build_house_silhouette(location=(0, 3.2, 0), scale=1.0):
    """Simple blocky house prop for story context in the walk/ending
    shots -- deliberately minimal (a box + a wedge roof), not competing
    with the character for detail budget under a hard time limit."""
    wall_mat = _material("house_wall", (0.90, 0.87, 0.80), roughness=0.85)
    roof_mat = _material("house_roof", (0.45, 0.22, 0.18), roughness=0.6)
    door_mat = _material("house_door", (0.30, 0.18, 0.10), roughness=0.5)

    w, d, h = 2.6 * scale, 2.2 * scale, 1.8 * scale
    bpy.ops.mesh.primitive_cube_add(size=1, location=(location[0], location[1], location[2] + h / 2))
    body = bpy.context.active_object
    body.scale = (w, d, h)
    bpy.ops.object.transform_apply(scale=True)
    body.data.materials.append(wall_mat)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(location[0], location[1] - d * 0.28, location[2] + h * 0.32))
    door = bpy.context.active_object
    door.scale = (w * 0.16, 0.06, h * 0.6)
    bpy.ops.object.transform_apply(scale=True)
    door.data.materials.append(door_mat)

    roof_h = h * 0.55
    bm = bmesh.new()
    hw, hd = w / 2 * 1.1, d / 2 * 1.08
    b0 = bm.verts.new((-hw, -hd, 0)); b1 = bm.verts.new((hw, -hd, 0))
    b2 = bm.verts.new((hw, hd, 0)); b3 = bm.verts.new((-hw, hd, 0))
    t0 = bm.verts.new((-hw, -hd, roof_h)); t1 = bm.verts.new((hw, -hd, roof_h))
    bm.faces.new((b0, b1, t1, t0)); bm.faces.new((b3, b2, t1, t0))
    bm.faces.new((b0, b3, t0)); bm.faces.new((b1, b2, t1))
    bm.faces.new((b0, b1, b2, b3))
    roof_mesh = bpy.data.meshes.new("house_roof_mesh")
    bm.to_mesh(roof_mesh)
    bm.free()
    roof = bpy.data.objects.new("house_roof", roof_mesh)
    bpy.context.collection.objects.link(roof)
    roof.location = (location[0], location[1], location[2] + h)
    for poly in roof.data.polygons:
        poly.use_smooth = False
    roof.data.materials.append(roof_mat)
    return [body, door, roof]


def build_voxel_human(role: str, root_location=(0, 0, 0), root_rotation_z=0.0):
    """Returns (root_empty, joints_dict) where joints_dict maps semantic
    joint name -> Empty object whose rotation drives that limb. Ground
    contact: root sits at floor level (z=0 local), legs hang below torso
    down to feet at root height, matching root_location's Z as the floor."""
    style = ROLE_STYLES[role]
    skin_mat = _material(f"{role}_skin", style["skin"], roughness=0.6)
    shirt_mat = _material(f"{role}_shirt", style["shirt"], roughness=0.55)
    pants_mat = _material(f"{role}_pants", style["pants"], roughness=0.6)
    hair_mat = _material(f"{role}_hair", style["hair"], roughness=0.4)

    root = bpy.data.objects.new(f"{role}_root", None)
    root.empty_display_size = 0.05
    bpy.context.collection.objects.link(root)
    root.location = root_location
    root.rotation_euler = (0, 0, root_rotation_z)

    floor_z = root_location[2]
    feet_z = floor_z
    hip_z = feet_z + LEG_LO_H + LEG_UP_H
    shoulder_z = hip_z + TORSO_H
    head_center_z = shoulder_z + NECK + HEAD / 2

    joints = {}

    # pelvis -> torso -> head chain, all parented to root (rigid, no
    # separate pelvis joint needed for this simplified rig). Location
    # given to _beveled_box is always a LOCAL offset from the eventual
    # parent -- consistent with every other body part below.
    torso = _beveled_box(f"{role}_torso", (TORSO_W, TORSO_D, TORSO_H),
                         (0, 0, hip_z + TORSO_H / 2 - root_location[2]), shirt_mat)
    torso.parent = root

    neck_empty = bpy.data.objects.new(f"{role}_neck", None)
    bpy.context.collection.objects.link(neck_empty)
    neck_empty.parent = root
    neck_empty.location = (0, 0, shoulder_z - root_location[2])
    joints["head"] = neck_empty

    head = _beveled_box(f"{role}_head", (HEAD * 0.85, HEAD * 0.85, HEAD), (0, 0, NECK + HEAD / 2),
                        skin_mat, bevel=0.05)
    head.parent = neck_empty

    hair_style = style["hair_style"]
    if hair_style == "short":
        hair = _beveled_box(f"{role}_hair", (HEAD * 0.9, HEAD * 0.9, HEAD * 0.32),
                            (0, -0.01, NECK + HEAD * 0.92), hair_mat, bevel=0.04)
        hair.parent = neck_empty
    elif hair_style == "long":
        hair = _beveled_box(f"{role}_hair", (HEAD * 0.95, HEAD * 0.95, HEAD * 1.35),
                            (0, 0.02, NECK + HEAD * 0.75), hair_mat, bevel=0.05)
        hair.parent = neck_empty
    elif hair_style == "bun":
        hair = _beveled_box(f"{role}_hair", (HEAD * 0.9, HEAD * 0.9, HEAD * 0.3),
                            (0, -0.01, NECK + HEAD * 0.9), hair_mat, bevel=0.04)
        hair.parent = neck_empty
        bun = _beveled_box(f"{role}_bun", (HEAD * 0.35, HEAD * 0.35, HEAD * 0.35),
                           (0, HEAD * 0.5, NECK + HEAD * 1.1), hair_mat, bevel=0.06)
        bun.parent = neck_empty
    elif hair_style == "cap":
        hair = _beveled_box(f"{role}_hair", (HEAD * 0.95, HEAD * 1.05, HEAD * 0.35),
                            (0, -HEAD * 0.1, NECK + HEAD * 0.92), (style["hair"] and
                            _material(f"{role}_cap", (0.65, 0.45, 0.10), roughness=0.5)),
                            bevel=0.04)
        hair.parent = neck_empty

    if "tie" in style:
        tie_mat = _material(f"{role}_tie", style["tie"], roughness=0.4)
        tie = _beveled_box(f"{role}_tie", (0.06, 0.03, TORSO_H * 0.55),
                           (0, -TORSO_D / 2 - 0.02, TORSO_H * 0.05), tie_mat, bevel=0.015)
        tie.parent = torso

    # shoulders / arms
    for side, sx in (("L", -1), ("R", 1)):
        sh_empty = bpy.data.objects.new(f"{role}_shoulder_{side}", None)
        bpy.context.collection.objects.link(sh_empty)
        sh_empty.parent = root
        sh_empty.location = (sx * (TORSO_W / 2 + ARM_W / 2 * 0.6), 0, shoulder_z - root_location[2] - 0.03)
        joints[f"shoulder_{side}"] = sh_empty

        upper_arm = _beveled_box(f"{role}_upperarm_{side}", (ARM_W, ARM_W, ARM_UP_H),
                                 (0, 0, -ARM_UP_H / 2), skin_mat if role != "banker" else shirt_mat)
        upper_arm.parent = sh_empty

        elbow_empty = bpy.data.objects.new(f"{role}_elbow_{side}", None)
        bpy.context.collection.objects.link(elbow_empty)
        elbow_empty.parent = sh_empty
        elbow_empty.location = (0, 0, -ARM_UP_H)
        joints[f"elbow_{side}"] = elbow_empty

        lower_arm = _beveled_box(f"{role}_lowerarm_{side}", (ARM_W * 0.9, ARM_W * 0.9, ARM_LO_H),
                                 (0, 0, -ARM_LO_H / 2), skin_mat)
        lower_arm.parent = elbow_empty

        hand = _beveled_box(f"{role}_hand_{side}", (HAND * 0.8, HAND * 0.6, HAND),
                            (0, 0, -ARM_LO_H - HAND / 2), skin_mat, bevel=0.03)
        hand.parent = elbow_empty

    # hips / legs
    for side, sx in (("L", -1), ("R", 1)):
        hip_empty = bpy.data.objects.new(f"{role}_hip_{side}", None)
        bpy.context.collection.objects.link(hip_empty)
        hip_empty.parent = root
        hip_empty.location = (sx * HIP_W / 2, 0, hip_z - root_location[2])
        joints[f"hip_{side}"] = hip_empty

        upper_leg = _beveled_box(f"{role}_upperleg_{side}", (0.16, 0.17, LEG_UP_H),
                                 (0, 0, -LEG_UP_H / 2), pants_mat)
        upper_leg.parent = hip_empty

        knee_empty = bpy.data.objects.new(f"{role}_knee_{side}", None)
        bpy.context.collection.objects.link(knee_empty)
        knee_empty.parent = hip_empty
        knee_empty.location = (0, 0, -LEG_UP_H)
        joints[f"knee_{side}"] = knee_empty

        lower_leg = _beveled_box(f"{role}_lowerleg_{side}", (0.14, 0.15, LEG_LO_H),
                                 (0, 0, -LEG_LO_H / 2), pants_mat)
        lower_leg.parent = knee_empty

        foot = _beveled_box(f"{role}_foot_{side}", (0.16, 0.26, FOOT_H),
                            (0, 0.05, -LEG_LO_H - FOOT_H / 2), _material(f"{role}_shoe", (0.05, 0.05, 0.06), roughness=0.5),
                            bevel=0.025)
        foot.parent = knee_empty

    joints["root"] = root
    return root, joints


def deg(x):
    return math.radians(x)


def key(obj, frame, euler=None, loc=None, scale=None):
    bpy.context.scene.frame_set(frame)
    if euler is not None:
        obj.rotation_euler = euler
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert(data_path="location", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)


def animate_finance_flow(stage):
    """Physical money storytelling for the finance_transform scene:
    salary bills land -> a portion (bills/expenses) flies off and
    shrinks away -> the remainder becomes a savings stack that visibly
    grows. All objects are the same beveled-box K70 Voxelizer-style
    finance props built in main() -- this only choreographs them."""
    f_in, f_split, f_grow = stage["f_in"], stage["f_split"], stage["f_grow"]

    salary = build_money_stack((0, 0.42, 0.12), n_bills=stage.get("n_salary", 9),
                               color=(0.16, 0.55, 0.28), name="salary")
    bills = build_money_stack((0, 0.42, 0.12), n_bills=stage.get("n_bills", 3),
                              color=(0.55, 0.16, 0.16), name="billsdue")

    # Real bug found and fixed: capturing the "landed" position via
    # obj.location AFTER already overwriting it with the drop-in keyframe
    # meant every bill kept the elevated drop-in position forever (it
    # never actually landed on the pedestal, floating out of camera view).
    # Fix: capture the true landed position BEFORE moving the object.
    for i, obj in enumerate(salary + bills):
        landed = Vector(obj.location)
        drop_from = landed + Vector((0, 0, 1.6 + i * 0.05))
        key(obj, 0, loc=(drop_from.x, drop_from.y, drop_from.z), scale=(1, 1, 1))
        key(obj, f_in, loc=(landed.x, landed.y, landed.z), scale=(1, 1, 1))

    for i, obj in enumerate(bills):
        landed = Vector(obj.location)
        key(obj, f_in, loc=(landed.x, landed.y, landed.z), scale=(1, 1, 1))
        fly_to = landed + Vector((0.9 + i * 0.1, 0.3, 0.3))
        key(obj, f_split, loc=(fly_to.x, fly_to.y, fly_to.z), scale=(0.15, 0.15, 0.15))

    # Full-grown height 0.85m (base box) so the "savings grow" beat is
    # actually visible next to the characters/pedestal, not a 6cm sliver.
    pillar_mat = _material("savings_pillar_mat", (0.20, 0.42, 0.62), roughness=0.4, metallic=0.15)
    pillar_h = 0.85
    pillar = _beveled_box("savings_pillar", (0.34, 0.34, pillar_h), (-0.85, 0.5, pillar_h / 2), pillar_mat, bevel=0.015)
    key(pillar, f_split, scale=(1, 1, 0.06), loc=(-0.85, 0.5, pillar_h * 0.06 / 2))
    key(pillar, f_grow, scale=(1, 1, 1.0), loc=(-0.85, 0.5, pillar_h / 2))
    return salary, bills, pillar


def animate_idle(root, joints, start=0, length=48):
    base_loc = Vector(root.location)
    for f, sway, bob in ((start, 0.0, 0.0), (start + length // 2, 3.0, 0.01), (start + length, 0.0, 0.0)):
        key(root, f, euler=(0, 0, root.rotation_euler[2] + deg(sway * 0.3)))
    for f, tilt in ((start, 0.0), (start + length // 2, -3.0), (start + length, 0.0)):
        key(joints["head"], f, euler=(0, deg(tilt * 0.4), deg(tilt)))
    for side, sgn in (("L", 1), ("R", -1)):
        for f, swing in ((start, 0.0), (start + length // 2, sgn * 4.0), (start + length, 0.0)):
            key(joints[f"shoulder_{side}"], f, euler=(deg(swing * 0.5), 0, 0))


def animate_walk(root, joints, start=0, length=24, n_cycles=3, stride_deg=32, forward_dist=0.0):
    base = Vector(root.location)
    total = length * n_cycles
    for c in range(n_cycles + 1):
        f = start + c * length
        t = c / max(n_cycles, 1)
        loc = base + Vector((0, forward_dist * t, 0))
        bob = abs(math.sin(c * math.pi)) * 0.015
        key(root, f, loc=(loc.x, loc.y, loc.z + bob))
    half = length // 2
    for side, phase in (("L", 0), ("R", half)):
        for c in range(n_cycles + 1):
            base_f = start + c * length
            key(joints[f"hip_{side}"], base_f + phase, euler=(deg(stride_deg), 0, 0))
            key(joints[f"hip_{side}"], base_f + phase + half, euler=(deg(-stride_deg), 0, 0))
            key(joints[f"knee_{side}"], base_f + phase, euler=(deg(8), 0, 0))
            key(joints[f"knee_{side}"], base_f + phase + half // 2, euler=(deg(-45), 0, 0))
            key(joints[f"knee_{side}"], base_f + phase + half, euler=(deg(8), 0, 0))
        opp = "R" if side == "L" else "L"
        for c in range(n_cycles + 1):
            base_f = start + c * length
            key(joints[f"shoulder_{side}"], base_f + phase, euler=(deg(-stride_deg * 0.6), 0, 0))
            key(joints[f"shoulder_{side}"], base_f + phase + half, euler=(deg(stride_deg * 0.6), 0, 0))


def animate_point_present(root, joints, start=0, length=60):
    for f, e in ((start, (0, 0, 0)),
                 (start + int(length * 0.3), (deg(-70), deg(10), deg(-15))),
                 (start + int(length * 0.7), (deg(-75), deg(-5), deg(-10))),
                 (start + length, (0, 0, 0))):
        key(joints["shoulder_R"], f, euler=e)
    for f, e in ((start, (0, 0, 0)),
                 (start + int(length * 0.3), (deg(-20), 0, 0)),
                 (start + int(length * 0.7), (deg(-15), 0, 0)),
                 (start + length, (0, 0, 0))):
        key(joints["elbow_R"], f, euler=e)
    for f, tilt in ((start, 0.0), (start + int(length * 0.4), -4.0), (start + length, 0.0)):
        key(joints["head"], f, euler=(0, 0, deg(tilt)))


def animate_sit(root, joints, start=0, length=40, seat_height=0.46):
    """Held seated pose: root drops to seat height, hips/knees bend to
    ~90deg. No stand->sit transition physics (not needed for a held
    behind-the-desk shot) -- just a clean settle over a short ease-in."""
    base = Vector(root.location)
    drop = max(0.0, (LEG_LO_H + LEG_UP_H) - seat_height)
    for f, t in ((start, 0.0), (start + length, 1.0)):
        loc = base - Vector((0, 0, drop * t))
        key(root, f, loc=(loc.x, loc.y, loc.z))
    for side in ("L", "R"):
        for f, e in ((start, (0, 0, 0)), (start + length, (deg(-95), 0, 0))):
            key(joints[f"hip_{side}"], f, euler=e)
        for f, e in ((start, (0, 0, 0)), (start + length, (deg(100), 0, 0))):
            key(joints[f"knee_{side}"], f, euler=e)
    for f, tilt in ((start, 0.0), (start + length, -2.0)):
        key(joints["head"], f, euler=(0, deg(tilt * 0.3), deg(tilt)))


def animate_sit_point(root, joints, length=48, **_):
    animate_sit(root, joints, start=0, length=length)
    animate_point_present(root, joints, start=int(length * 0.35), length=int(length * 0.65))


ANIMATIONS = {"idle": animate_idle, "walk": animate_walk, "point": animate_point_present,
             "sit": animate_sit, "sit_point": animate_sit_point}


def main() -> None:
    a = _args()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    scene_type = a["scene_type"]
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
            scene.eevee.use_raytracing = render.get("raytracing", True)
        except AttributeError:
            pass

    ground_mat = _material("ground", (0.55, 0.58, 0.52), roughness=0.85)
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.data.materials.append(ground_mat)

    if scene_type in ("office", "bank"):
        wall_mat = _material("wall", (0.88, 0.86, 0.80), roughness=0.9)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 2.2, 1.5))
        wall = bpy.context.active_object
        wall.scale = (6, 0.1, 3)
        bpy.ops.object.transform_apply(scale=True)
        wall.data.materials.append(wall_mat)

        # Real Poly Haven CC0 furniture (gltf) physically placed in-scene,
        # not a flat backdrop -- desk the characters stand/sit at, a real
        # chair, and small desk props for readability/depth.
        _import_gltf(POLYHAVEN_DIR / "metal_office_desk" / "metal_office_desk.gltf",
                     location=(0, 0.95, 0), rotation_z_deg=0, scale=1.0, name_prefix="desk")
        _import_gltf(POLYHAVEN_DIR / "SchoolChair_01" / "SchoolChair_01.gltf",
                     location=(0.55, 1.55, 0), rotation_z_deg=200, scale=1.0, name_prefix="chair")
        _import_gltf(POLYHAVEN_DIR / "classic_laptop" / "classic_laptop.gltf",
                     location=(-0.25, 0.85, 0.76), rotation_z_deg=15, scale=1.0, name_prefix="laptop")
        _import_gltf(POLYHAVEN_DIR / "desk_lamp_arm_01" / "desk_lamp_arm_01.gltf",
                     location=(0.5, 0.7, 0.76), rotation_z_deg=-30, scale=1.0, name_prefix="lamp")
        _import_gltf(POLYHAVEN_DIR / "wall_clock" / "wall_clock.gltf",
                     location=(-2.2, 2.14, 2.0), rotation_z_deg=0, scale=1.0, name_prefix="clock")
        if scene_type == "bank":
            _import_gltf(POLYHAVEN_DIR / "CashRegister_01" / "CashRegister_01.gltf",
                         location=(1.4, 0.75, 0.76), rotation_z_deg=0, scale=1.0, name_prefix="register")
            _import_gltf(POLYHAVEN_DIR / "Shelf_01" / "Shelf_01.gltf",
                         location=(-2.3, 1.6, 0), rotation_z_deg=90, scale=1.0, name_prefix="shelf")

    elif scene_type == "finance_transform":
        # Neutral stage for physical money->bills->savings choreography --
        # deliberately uncluttered so the K70 Voxelizer-style finance
        # objects (built in main() below from a.get("finance_stage")) read
        # clearly, with a soft gradient backdrop for depth instead of an
        # empty flat background.
        backdrop_mat = _material("fin_backdrop", (0.10, 0.11, 0.14), roughness=0.95)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 1.6, 1.2))
        backdrop = bpy.context.active_object
        backdrop.scale = (4.5, 0.1, 2.6)
        bpy.ops.object.transform_apply(scale=True)
        backdrop.data.materials.append(backdrop_mat)

        pedestal_mat = _material("fin_pedestal", (0.22, 0.22, 0.25), roughness=0.4, metallic=0.2)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.55, depth=0.12, location=(0, 0.4, 0.06))
        pedestal = bpy.context.active_object
        for poly in pedestal.data.polygons:
            poly.use_smooth = True
        pedestal.data.materials.append(pedestal_mat)

    elif scene_type == "house":
        build_house_silhouette(location=tuple(a.get("house_location", [0, 3.2, 0])),
                               scale=a.get("house_scale", 1.0))
        for i, pos in enumerate([(-2.9, 1.6, 0), (3.1, 0.8, 0)]):
            _import_fbx(CC0TREE_DIR / "SM_Tree_1.fbx", location=pos,
                        rotation_z_deg=(i * 80) % 360, scale=0.68, name_prefix=f"htree_{i}")

    elif scene_type == "apartment":
        wall_mat = _material("apt_wall", (0.82, 0.80, 0.74), roughness=0.9)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 2.0, 1.4))
        wall = bpy.context.active_object
        wall.scale = (5.5, 0.1, 2.8)
        bpy.ops.object.transform_apply(scale=True)
        wall.data.materials.append(wall_mat)

        window_mat = _material("apt_window", (0.55, 0.70, 0.85), roughness=0.1, metallic=0.15)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.4, 1.94, 1.5))
        window = bpy.context.active_object
        window.scale = (1.1, 0.04, 1.2)
        bpy.ops.object.transform_apply(scale=True)
        window.data.materials.append(window_mat)

        table_mat = _material("apt_table", (0.35, 0.24, 0.15), roughness=0.5)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0.6, 0.7, 0.34))
        table = bpy.context.active_object
        table.scale = (0.9, 0.6, 0.68)
        bpy.ops.object.transform_apply(scale=True)
        table.data.materials.append(table_mat)

        couch_mat = _material("apt_couch", (0.30, 0.38, 0.45), roughness=0.7)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.6, -0.4, 0.28))
        couch = bpy.context.active_object
        couch.scale = (0.6, 1.3, 0.55)
        bpy.ops.object.transform_apply(scale=True)
        couch.data.materials.append(couch_mat)

        # Real Poly Haven CC0 furniture layered into the same room for
        # genuine foreground/midground depth (sofa near-camera, cabinet
        # against the back wall), not a second unrelated demo scene.
        _import_gltf(POLYHAVEN_DIR / "Sofa_01" / "Sofa_01.gltf",
                     location=(-1.75, -0.7, 0), rotation_z_deg=70, scale=1.0, name_prefix="sofa")
        _import_gltf(POLYHAVEN_DIR / "drawer_cabinet" / "drawer_cabinet.gltf",
                     location=(1.9, 1.7, 0), rotation_z_deg=180, scale=1.0, name_prefix="cabinet")
        _import_gltf(POLYHAVEN_DIR / "wall_clock" / "wall_clock.gltf",
                     location=(1.2, 1.94, 1.9), rotation_z_deg=0, scale=1.0, name_prefix="clock")

    elif scene_type == "street":
        # Real foreground/midground/background depth for a walking
        # tracking shot: near buildings tall and close either side,
        # progressively shorter/further/hazier buildings behind them.
        road_mat = _material("road", (0.12, 0.12, 0.13), roughness=0.75)
        bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0.001))
        road = bpy.context.active_object
        road.scale = (5.0, 60, 1)
        bpy.ops.object.transform_apply(scale=True)
        road.data.materials.append(road_mat)

        sidewalk_mat = _material("sidewalk", (0.55, 0.54, 0.50), roughness=0.85)
        for side in (-1, 1):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(side * 3.2, 0, 0.05))
            sw = bpy.context.active_object
            sw.scale = (1.4, 60, 0.1)
            bpy.ops.object.transform_apply(scale=True)
            sw.data.materials.append(sidewalk_mat)

        import random
        rnd = random.Random(a.get("street_seed", 7))
        building_palette = [(0.75, 0.55, 0.35), (0.65, 0.68, 0.72), (0.55, 0.35, 0.30),
                            (0.70, 0.65, 0.50), (0.45, 0.50, 0.55)]
        for side in (-1, 1):
            for i in range(9):
                depth = -6 + i * 7 + rnd.uniform(-1, 1)
                dist = 4.5 + rnd.uniform(0, 1.5)
                height = rnd.uniform(2.2, 7.0) if i > 1 else rnd.uniform(2.0, 3.2)
                width = rnd.uniform(2.0, 3.5)
                color = building_palette[rnd.randrange(len(building_palette))]
                mat = _material(f"bld_{side}_{i}", color, roughness=0.8)
                bpy.ops.mesh.primitive_cube_add(size=1, location=(side * dist, depth, height / 2))
                b = bpy.context.active_object
                b.scale = (width, width * 0.8, height)
                bpy.ops.object.transform_apply(scale=True)
                b.data.materials.append(mat)
                # windows: a simple grid of emissive squares for night-lit depth cues
                win_mat = _material(f"bldwin_{side}_{i}", (1.0, 0.85, 0.55), roughness=0.4)
                win_mat.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1.0, 0.82, 0.5, 1)
                win_mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = rnd.uniform(0.4, 1.4)
                rows = max(1, int(height / 0.7))
                for r in range(rows):
                    if rnd.random() < 0.4:
                        continue
                    wz = 0.4 + r * 0.7
                    if wz > height - 0.3:
                        continue
                    bpy.ops.mesh.primitive_cube_add(
                        size=1, location=(side * (dist - width / 2 * 0.98), depth, wz))
                    win = bpy.context.active_object
                    win.scale = (0.03, width * 0.6, 0.35)
                    bpy.ops.object.transform_apply(scale=True)
                    win.data.materials.append(win_mat)

        # a streetlamp as a clear foreground silhouette element for depth
        lamp_mat = _material("lamp_pole", (0.08, 0.08, 0.09), roughness=0.5, metallic=0.6)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=2.6, location=(2.0, -1.5, 1.3))
        pole = bpy.context.active_object
        pole.data.materials.append(lamp_mat)
        glow_mat = _material("lamp_glow", (1.0, 0.9, 0.6), roughness=0.3)
        glow_mat.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1.0, 0.88, 0.6, 1)
        glow_mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 3.0
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, location=(2.0, -1.5, 2.65))
        glow = bpy.context.active_object
        glow.data.materials.append(glow_mat)

        # Real CC0Tree CC0 vegetation for midground street dressing --
        # genuine environmental richness, not just buildings+road.
        # Real bug found: trees placed close to the camera's own dolly
        # track (x around -5.5..-4.2 across the shot) intersected the
        # canopy, filling the whole frame with flat green. Fix: keep all
        # trees on the FAR side of the street (opposite the camera track)
        # so they read as midground dressing across the road, never as a
        # collision.
        tree_positions = [(4.3, -3.2, 0), (4.4, -0.4, 0), (4.35, 2.6, 0), (4.5, 5.0, 0)]
        for i, pos in enumerate(tree_positions):
            _import_fbx(CC0TREE_DIR / "SM_Tree_1.fbx", location=pos,
                        rotation_z_deg=(i * 47) % 360, scale=0.62, name_prefix=f"tree_{i}")

        if a.get("show_bank_facade"):
            build_bank_building(location=(3.9, 5.0, 0), scale=0.9)

        procgen_path = a.get("procgen_city_blend")
        if procgen_path:
            # Real vendor/bene-proggen-maps output (verified headless this
            # session) as a distant skyline layer beyond the hand-authored
            # midground buildings -- genuine Procgen Maps content in the
            # same shot, not an isolated demo render.
            _import_procgen_city(Path(procgen_path), location=a.get("procgen_location", [0, 34, 0]),
                                 rotation_z_deg=a.get("procgen_rotation_deg", 0),
                                 scale=a.get("procgen_scale", 0.10),
                                 max_buildings=a.get("procgen_max_buildings", 24))

    finance_stage = a.get("finance_stage")
    if finance_stage:
        animate_finance_flow(finance_stage)

    characters = {}
    for spec in a.get("characters", []):
        root, joints = build_voxel_human(spec["role"], root_location=tuple(spec["location"]),
                                          root_rotation_z=deg(spec.get("rotation_z_deg", 0)))
        characters[spec["role"]] = (root, joints)
        anim = spec.get("animation")
        if anim:
            ANIMATIONS[anim["type"]](root, joints, **anim.get("params", {}))

    frame_range = a.get("frame_range")
    if frame_range:
        scene.frame_start, scene.frame_end = frame_range

    lighting_preset = a.get("lighting_preset")
    if lighting_preset:
        # Real CC0 Poly Haven HDRI, MD5-verified -- motivated lighting +
        # real environment reflections instead of a flat color dome.
        from lighting_presets import apply_hdri_world
        apply_hdri_world(lighting_preset, rotation_z=deg(a.get("hdri_rotation_deg", 0)),
                         strength_override=a.get("hdri_strength"))
    else:
        world = bpy.data.worlds.new("k70_voxel_world")
        world.use_nodes = True
        bpy.context.scene.world = world
        bg = world.node_tree.nodes.get("Background")
        if bg is not None:
            sky = a.get("sky_color", [0.55, 0.68, 0.82])
            bg.inputs["Color"].default_value = (*sky, 1.0)
            bg.inputs["Strength"].default_value = a.get("sky_strength", 1.0)

    sun_data = bpy.data.lights.new("k70_sun", type="SUN")
    sun_data.energy = a.get("sun_energy", 2.0)
    sun_data.angle = 0.2
    sun_obj = bpy.data.objects.new("k70_sun", sun_data)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = tuple(a.get("sun_rotation", [0.9, 0, 0.6]))

    fill_data = bpy.data.lights.new("k70_fill", type="AREA")
    fill_data.energy = a.get("fill_energy", 35)
    fill_data.size = 3
    fill_obj = bpy.data.objects.new("k70_fill", fill_data)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = tuple(a.get("fill_location", [-2, -2, 2.5]))
    fill_obj.rotation_euler = (deg(60), 0, deg(-45))

    cam_data = bpy.data.cameras.new("k70_cam")
    cam_data.lens = a.get("lens", 50)
    # AUTO sensor_fit mis-frames portrait (height>width) renders -- FOV
    # stays governed by sensor_width regardless of lens/distance, so a
    # 9:16 render shows mostly empty headroom no matter what. Explicit
    # VERTICAL fit for portrait jobs fixes this; default AUTO preserves
    # every prior (landscape) benchmark's framing unchanged.
    cam_data.sensor_fit = a.get("sensor_fit", "AUTO")
    cam_data.dof.use_dof = a.get("dof", False)
    if a.get("dof"):
        cam_data.dof.aperture_fstop = a.get("fstop", 2.0)
    cam_obj = bpy.data.objects.new("k70_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)

    def aim_camera(location, look_at_pt):
        cam_obj.location = location
        cam_obj.rotation_euler = (Vector(look_at_pt) - Vector(location)).to_track_quat("-Z", "Y").to_euler()

    camera_keyframes = a.get("camera_keyframes")
    focus_empty = None
    if a.get("dof"):
        focus_empty = bpy.data.objects.new("focus", None)
        bpy.context.collection.objects.link(focus_empty)
        cam_data.dof.focus_object = focus_empty

    if camera_keyframes:
        # Real cinematic camera move: dolly/track/orbit authored as
        # location+look_at keyframes, same reliable direct-keyframing
        # technique used for character animation.
        for kf in camera_keyframes:
            scene.frame_set(kf["frame"])
            aim_camera(kf["location"], kf["look_at"])
            cam_obj.keyframe_insert(data_path="location", frame=kf["frame"])
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=kf["frame"])
            if focus_empty is not None:
                focus_empty.location = kf["look_at"]
                focus_empty.keyframe_insert(data_path="location", frame=kf["frame"])
        for fc in cam_obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'BEZIER'
                kp.handle_left_type = 'AUTO_CLAMPED'
                kp.handle_right_type = 'AUTO_CLAMPED'
        if focus_empty is not None and focus_empty.animation_data:
            for fc in focus_empty.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = 'BEZIER'
    else:
        aim_camera(tuple(a["camera"]["location"]), tuple(a["camera"]["look_at"]))
        if focus_empty is not None:
            focus_empty.location = tuple(a["camera"]["look_at"])
    bpy.context.scene.camera = cam_obj

    out_dir = Path(render["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    n_frames = a.get("n_frames", 1)
    # Resume support: skip any frame whose PNG already exists and is a
    # complete file (>1KB, not a truncated write from a killed process),
    # so an interrupted render only re-renders what's actually missing.
    def _done(p: Path) -> bool:
        return p.exists() and p.stat().st_size > 1024
    if n_frames == 1:
        out_path = out_dir / "frame_000.png"
        if not _done(out_path):
            scene.render.filepath = str(out_path)
            bpy.ops.render.render(write_still=True)
        else:
            print(f"  [resume] frame_000 already present, skipping")
    else:
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
    print(f"K70_VOXEL_HUMAN_RENDER_OK {out_dir} frames={n_frames}")


if __name__ == "__main__":
    main()
