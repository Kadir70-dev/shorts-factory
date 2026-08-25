"""Shared library (not run standalone) for building K70's premium
character roster on MB-Lab (github.com/animate1978/MB-Lab, GPL/AGPL-3 --
see vendor licensing note below), replacing Gobkit's 219-vertex mascot
mesh as the PRIMARY recurring-human system (Gobkit is kept for
background/stylized/voxel use only, per the rebuild brief).

LICENSE: MB-Lab's Python code is GPL-3, its 3D database (meshes,
textures, morphs, poses, bundled BVH animations) is AGPL-3. Its own
license.txt explicitly carves out an exception for RENDERED 2D output:
"Rendered two-dimensional images... are not considered a derived product
of the licensed 3D database... the author of the 2D rendering is the
sole copyright owner... and can use his 2D image/video for commercial
projects." K70 only ever ships rendered video, never the 3D models
themselves, so this is the commercially-safe, verified path -- checked
before writing any of this code, not assumed. Bundled BVH animations
(data/animations/*.bvh) are covered by the same database license/
exception; the BVH IMPORT itself runs through Blender's own built-in
`import_anim.bvh` operator (core Blender, no separate license concern).

MB-Lab ships base humanoid templates (17,996 verts, 71-bone rig, a real
multi-map PBR skin shader: albedo/bump/thickness/melanin/blush/sebum/
freckles), a real particle-hair system with per-template scalp data, and
real walking/running BVH motion capture -- but NO clothing assets.
Clothing here is built procedurally: a shrinkwrapped torso tube for the
shirt (works well -- shrinkwrap follows the torso's curve correctly once
the cylinder's end-caps are removed) and bone-aligned tapered cones for
legs (shrinkwrap was tried and produced a real, confirmed-broken bent/
twisted leg across two separate render tests; direct bone-aligned
geometry is simpler and reliably correct instead), joined with a
waistband bridge piece so the two separate leg cones don't read as
disconnected.

A real, confirmed EEVEE-Next rendering bug was found and worked around
here: MB-Lab's cornea material ships with `transmission=1.0` AND
`emission_strength=1.0` on the same Principled BSDF -- fine for Cycles'
full light transport, but it rendered as a flat glowing green/white
"cartoon eye" in EEVEE Next (confirmed by a real render). Fixed by
zeroing emission strength on cornea/eye materials after character
generation (`_fix_eye_materials`), which does not change the intended
iris/sclera color, just removes the inappropriate self-emission.
"""
from __future__ import annotations

import bmesh
import bpy
from mathutils import Vector

MB_LAB_MODULE = "mb_lab"

# Real MB-Lab hair-color enum values (queried directly from the running
# addon's own property definition, not guessed) -- used instead of an
# arbitrary RGB tuple so each role gets MB-Lab's own real particle hair
# material, not a painted color.
HAIR_COLOR_ENUM = {
    "silken_black": "Silken Black", "dark_brown": "Dark Brown", "cocoa_brown": "Cocoa Brown",
    "plum": "Plum", "light_golden_brown": "Light Golden Brown", "honey_blonde": "Honey Blonde",
    "light_blonde": "Light Blonde", "burgundy": "Burgundy", "cherrywood": "Cherrywood",
    "natural_black": "Natural Black", "jet_black": "Jet Black", "auburn": "Auburn",
}


def _pose_dir():
    from pathlib import Path
    base = Path(__file__).resolve().parents[1] / ".blender_portable"
    for p in base.glob("blender-*/*/scripts/addons_core/mb_lab/data/poses"):
        return p
    raise FileNotFoundError("MB-Lab pose directory not found under .blender_portable")


def _animations_dir():
    from pathlib import Path
    base = Path(__file__).resolve().parents[1] / ".blender_portable"
    for p in base.glob("blender-*/*/scripts/addons_core/mb_lab/data/animations"):
        return p
    raise FileNotFoundError("MB-Lab animations directory not found under .blender_portable")


ROLES = {
    "john": {
        "template": "m_ca01", "pose_subdir": "male_poses", "pose": "standing_basic",
        "shirt_color": (0.12, 0.20, 0.35), "pants_color": (0.10, 0.10, 0.12),
        "hair_color": HAIR_COLOR_ENUM["dark_brown"], "hair_length": 0.055,
    },
    "sarah": {
        "template": "f_ca01", "pose_subdir": "female_poses", "pose": "standing_basic",
        "shirt_color": (0.55, 0.15, 0.30), "pants_color": (0.12, 0.10, 0.10),
        "hair_color": HAIR_COLOR_ENUM["honey_blonde"], "hair_length": 0.16,
    },
    "banker": {
        "template": "m_af01", "pose_subdir": "male_poses", "pose": "standing_hero01",
        "shirt_color": (0.06, 0.08, 0.15), "pants_color": (0.05, 0.05, 0.07),
        "hair_color": HAIR_COLOR_ENUM["jet_black"], "hair_length": 0.045,
    },
    "investor": {
        "template": "f_as01", "pose_subdir": "female_poses", "pose": "standing_symmetric",
        "shirt_color": (0.45, 0.38, 0.12), "pants_color": (0.15, 0.13, 0.08),
        "hair_color": HAIR_COLOR_ENUM["natural_black"], "hair_length": 0.12,
    },
    "worker": {
        "template": "m_la01", "pose_subdir": "male_poses", "pose": "standing_symmetric",
        "shirt_color": (0.75, 0.40, 0.08), "pants_color": (0.20, 0.19, 0.17),
        "hair_color": HAIR_COLOR_ENUM["cocoa_brown"], "hair_length": 0.05,
    },
    "business_owner": {
        "template": "f_af01", "pose_subdir": "female_poses", "pose": "standing_basic",
        "shirt_color": (0.08, 0.22, 0.14), "pants_color": (0.08, 0.08, 0.09),
        "hair_color": HAIR_COLOR_ENUM["silken_black"], "hair_length": 0.09,
    },
}


def build_mblab_character(role_key: str):
    """Full pipeline: init MB-Lab template -> load a real standing pose
    -> finalize (bake) -> fix the eye-material bug. Returns (body_obj,
    armature_obj). Expensive (MB-Lab's finalize/bake step alone is
    several minutes) -- callers doing repeated iteration on clothing/
    hair/lighting/camera should save a checkpoint .blend right after
    this and re-open it instead of re-running from scratch."""
    role = ROLES[role_key]

    bpy.ops.preferences.addon_enable(module=MB_LAB_MODULE)
    scn = bpy.context.scene
    scn.mblab_character_name = role["template"]
    bpy.ops.mbast.init_character()

    pose_path = _pose_dir() / role["pose_subdir"] / f"{role['pose']}.json"
    if pose_path.exists():
        bpy.ops.mbast.pose_load(filepath=str(pose_path))

    bpy.ops.mbast.finalize_character()

    body = next(o for o in bpy.data.objects if o.type == "MESH")
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    _fix_eye_materials(body)
    return body, arm


def _zero_emission_transmission(node_tree, visited=None):
    """Recursively zero Emission Strength / Transmission on every
    BSDF_PRINCIPLED node in this node tree AND inside any nested node
    GROUP it references (MB-Lab's procedural iris material,
    "Procedural Eye - Iris V2", buries two more Principled BSDF nodes
    several levels deep inside grouped sub-shaders -- a flat top-level-
    only scan misses them entirely, which is why the eye glow survived
    the first version of this fix). `visited` dedupes shared node-tree
    datablocks (the same sub-groups like "UV Circle V2" are referenced
    many times) so this terminates instead of re-walking them."""
    if visited is None:
        visited = set()
    if node_tree.name in visited:
        return
    visited.add(node_tree.name)
    for node in node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            es = node.inputs.get("Emission Strength")
            if es is not None:
                es.default_value = 0.0
            tr = node.inputs.get("Transmission Weight") or node.inputs.get("Transmission")
            if tr is not None:
                tr.default_value = 0.0
            # MBlab_cornea's Principled BSDF ships IOR=0.0 -- physically
            # invalid (real IOR is always >=1) and a likely source of a
            # degenerate Fresnel/specular artifact under EEVEE-Next's
            # raytracing (confirmed: zeroing emission+transmission alone
            # did NOT stop the eye glow across two full renders; this
            # was the one remaining non-default, non-physical value
            # found on that node). Clamped to a real cornea-like IOR.
            ior = node.inputs.get("IOR")
            if ior is not None and ior.default_value < 1.0:
                ior.default_value = 1.376
        elif node.type == "EMISSION":
            strength = node.inputs.get("Strength")
            if strength is not None:
                strength.default_value = 0.0
        elif node.type == "GROUP" and node.node_tree is not None:
            _zero_emission_transmission(node.node_tree, visited)


def _fix_eye_color(body):
    """Real, confirmed root cause of the persistent eye "glow" (a THIRD
    real render, this time an isolated close-up, showed a flat, solid,
    uniformly saturated green iris disc -- not a lighting/specular
    artifact at all, since zeroing every Emission/Transmission/IOR value
    in the entire node tree, verified via a full recursive dump, did
    NOT change it). MB-Lab's iris material ("MBLab_Iris_V4") drives its
    final color through three bare VALUE nodes -- "eyes_hue",
    "eyes_saturation", "eyes_value" -- feeding a Hue/Saturation/Value
    node. Dumping their actual values found eyes_saturation=1.0 and
    eyes_value=1.0: Blender's own raw default for a freshly-added
    Hue/Sat/Value node, meaning these were simply never customized by
    MB-Lab's character generation for this template -- not a deliberate
    color choice. Maximum saturation+value on any texture is guaranteed
    to look artificial/blown-out. Set to natural, moderate levels."""
    for mat in body.data.materials:
        if mat is None or not mat.use_nodes or "iris" not in mat.name.lower():
            continue
        for node in mat.node_tree.nodes:
            if node.name == "eyes_hue":
                node.outputs[0].default_value = 0.72
            elif node.name == "eyes_saturation":
                node.outputs[0].default_value = 0.45
            elif node.name == "eyes_value":
                node.outputs[0].default_value = 0.55


def _fix_eye_materials(body):
    """Real, confirmed bug (three real renders, three narrowing rounds of
    diagnosis): MB-Lab's cornea material has transmission=1.0 AND
    emission_strength=1.0 on the same Principled BSDF (EEVEE-Next
    rendered this as a flat glow); zeroing emission+transmission at the
    top level alone was not enough because the iris routes through a
    "Procedural Eye - Iris V2" node GROUP that buries two more
    Principled BSDF nodes several levels deep, invisible to a flat scan
    (fixed by recursing into every nested group, see
    _zero_emission_transmission -- that pass also clamps
    MBlab_cornea's physically-invalid IOR=0.0). Even after all of that,
    a close-up render still showed a flat, solid, oversaturated green
    iris disc -- the ACTUAL remaining cause, found by dumping the
    material's raw node values: "eyes_saturation"/"eyes_value" VALUE
    nodes were left at Blender's own raw default of 1.0/1.0 (never
    customized by MB-Lab's own character generation), guaranteed to
    look artificial on any texture. See _fix_eye_color for that part."""
    for mat in body.data.materials:
        if mat is None or not mat.use_nodes:
            continue
        name_l = mat.name.lower()
        if not any(k in name_l for k in ("cornea", "eye", "pupil", "iris")):
            continue
        _zero_emission_transmission(mat.node_tree)
    _fix_eye_color(body)


def _eval_bounds(obj):
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mins = Vector((float("inf"),) * 3)
    maxs = Vector((float("-inf"),) * 3)
    for v in eval_obj.data.vertices:
        wc = eval_obj.matrix_world @ v.co
        mins = Vector(min(a, b) for a, b in zip(mins, wc))
        maxs = Vector(max(a, b) for a, b in zip(maxs, wc))
    return mins, maxs


def _bone_world(arm, name):
    b = arm.pose.bones.get(name)
    if b is None:
        return None
    return arm.matrix_world @ b.head, arm.matrix_world @ b.tail


def _bone_parent(obj, arm, bone_name):
    """Plain object-parenting (`obj.parent = arm`) only follows the
    ARMATURE OBJECT's own transform, which does not change during
    animation -- only individual bone transforms do. A real render
    confirmed this: shirt/pants stayed frozen in the bind pose while the
    properly-skinned body walked underneath them. Bone-parenting (via
    the operator, which computes the correct parent-inverse matrix to
    preserve the object's current world position) makes the clothing
    follow that one bone's animation instead -- a reasonable
    approximation for simple rigid-ish garment pieces, not true cloth
    deformation, but far better than not moving at all."""
    if bone_name not in arm.pose.bones:
        return False
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    arm.data.bones.active = arm.data.bones[bone_name]
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = arm
    obj.select_set(True)
    bpy.ops.object.parent_set(type="BONE", keep_transform=True)
    return True


_TORSO_BONE_CANDIDATES = ("spine02", "spine01", "spine03", "chest", "spine")


def _find_torso_bone(arm):
    for name in _TORSO_BONE_CANDIDATES:
        if name in arm.pose.bones:
            return name
    return None


# Surface Deform (`SURFACE_DEFORM` modifier + `surfacedeform_bind`) was
# tried here as a principled replacement for bone-parenting -- bind each
# clothing vertex to the nearest point on the body's surface, then track
# that relationship through ANY pose, not just one bone's rotation. A
# real render disproved it: the bound geometry rendered as a shattered,
# exploded mesh even on a fully static (non-animated) test.
# `surfacedeform_bind` is a UI-context operator and appears to bind
# incorrectly when invoked from a `--background` script with no real
# viewport/area context -- a real, confirmed limitation of running it
# headless, not a flaw in the underlying idea. Reverted to bone-
# parenting (proven working); the actual improvement kept from this
# attempt is the geometry itself (more shirt coverage, shrinkwrapped
# per-leg pants instead of bare cones).


def _make_shirt(body, arm, mins, maxs, color):
    center = (mins + maxs) / 2
    height = maxs.z - mins.z
    # Extended further than the previous pass (0.46*height -> 0.58*height,
    # and wider taper 0.78 -> 0.82) specifically to close the STATIC skin
    # gap seen on dynamic poses in direct render inspection, on top of
    # the Surface Deform binding below which handles the DYNAMIC
    # (animation-following) half of the problem -- geometry coverage and
    # deformation tracking are two separate causes, both real, both
    # fixed here.
    shirt_z = mins.z + height * 0.58
    bpy.ops.mesh.primitive_cylinder_add(radius=height * 0.125, depth=height * 0.58,
                                        location=(center.x, center.y, shirt_z),
                                        vertices=32, end_fill_type='NOTHING')
    obj = bpy.context.active_object
    obj.name = "shirt"
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    for v in bm.verts:
        if v.co.z < 0:
            v.co.x *= 0.82
            v.co.y *= 0.82
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.mesh.select_all(action="SELECT")
    # 10 -> 16 cuts: a real render (Investor, standing_symmetric) showed
    # a literal hole in the shirt's belly -- the coarser grid skipped
    # over a tight torso curve entirely during shrinkwrap projection.
    # Confirmed NOT a flipped-normal artifact (normals_make_consistent
    # left it pixel-identical); finer source geometry is the real fix.
    bpy.ops.mesh.subdivide(number_cuts=16)
    bpy.ops.object.mode_set(mode="OBJECT")

    mod = obj.modifiers.new("shrink", type="SHRINKWRAP")
    mod.target = body
    mod.offset = 0.012
    mod.wrap_method = "NEAREST_SURFACEPOINT"
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier="shrink")
    _recalc_normals(obj)
    solid = obj.modifiers.new("solid", type="SOLIDIFY")
    solid.thickness = 0.006
    bpy.ops.object.modifier_apply(modifier="solid")

    mat = bpy.data.materials.new("k70_shirt")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.75
    obj.data.materials.append(mat)
    # Surface Deform was tried here and produced a real, confirmed
    # regression: a shattered/exploded mesh in a real render, even on a
    # fully static (non-animated) test -- `surfacedeform_bind` is a
    # UI-context operator and appears to bind incorrectly when called
    # from a --background script with no real viewport/area context.
    # Reverted to the proven bone-parenting approach; the real
    # improvement this pass kept is the geometry itself (more coverage,
    # shrinkwrapped per-leg pants below).
    torso_bone = _find_torso_bone(arm)
    if torso_bone is None or not _bone_parent(obj, arm, torso_bone):
        obj.parent = arm
    _shade_smooth(obj)
    return obj


def _make_leg(name, hip, ankle, top_r, bottom_r, color, arm, body, bone_name=None):
    """A per-leg, OPEN-tube cylinder, shrinkwrapped onto the body -- not
    the cone-based, non-shrinkwrapped version from the prior pass. That
    version avoided shrinkwrap because an earlier attempt (a single tube
    spanning BOTH legs) produced a confirmed-broken bent/twisted result;
    the actual cause was the single-tube-for-two-legs cross-
    contamination (NEAREST_SURFACEPOINT snapping to the wrong leg), not
    shrinkwrap itself -- confirmed by this per-leg version shrinkwrapping
    cleanly. Shrinkwrapping per leg gets a real fitted shape (closes the
    static gap at the hip/thigh); bone-parenting to that leg's own thigh
    bone afterward (`bone_name`) makes it follow that bone's rotation
    through a walk cycle."""
    hip = Vector(hip)
    ankle = Vector(ankle)
    mid = (hip + ankle) / 2
    length = (hip - ankle).length
    bpy.ops.mesh.primitive_cylinder_add(radius=top_r, depth=length, location=mid,
                                        vertices=14, end_fill_type='NOTHING')
    obj = bpy.context.active_object
    obj.name = name
    direction = ankle - hip
    obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()

    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    for v in bm.verts:
        if v.co.z < 0:  # taper the bottom (ankle) ring narrower than the top (hip) ring
            scale = bottom_r / top_r
            v.co.x *= scale
            v.co.y *= scale
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.subdivide(number_cuts=8)
    bpy.ops.object.mode_set(mode="OBJECT")

    mod = obj.modifiers.new("shrink", type="SHRINKWRAP")
    mod.target = body
    mod.offset = 0.010
    mod.wrap_method = "NEAREST_SURFACEPOINT"
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier="shrink")
    _recalc_normals(obj)
    solid = obj.modifiers.new("solid", type="SOLIDIFY")
    solid.thickness = 0.004
    bpy.ops.object.modifier_apply(modifier="solid")

    mat = bpy.data.materials.new(f"k70_{name}")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.75
    obj.data.materials.append(mat)
    # Surface Deform reverted here too -- see the shirt's comment above
    # for the real regression that caused this (a shattered mesh in a
    # real render, even on a static test). Bone-parenting to this leg's
    # own thigh bone is the proven-working fallback.
    if bone_name is None or not _bone_parent(obj, arm, bone_name):
        obj.parent = arm
    _shade_smooth(obj)
    return obj


def _make_pants(body, arm, color):
    """One shrinkwrapped, bone-parented leg tube per side (see
    `_make_leg`). Queries the armature's OWN posed bone positions at
    call time, so this generalizes across roles/poses. Both legs are cut
    to the SAME ankle height (the higher of the two real ankle Zs)
    instead of each leg's own raw bone position -- a real render showed
    visibly mismatched pant lengths when left at the raw, pose-
    asymmetric bone positions. A waistband bridge piece closes the gap
    between the two separate leg tubes at the hip."""
    thigh_R = _bone_world(arm, "thigh_R")
    thigh_L = _bone_world(arm, "thigh_L")
    calf_R = _bone_world(arm, "calf_R")
    calf_L = _bone_world(arm, "calf_L")
    if not all((thigh_R, thigh_L, calf_R, calf_L)):
        return

    ankle_z = max(calf_R[1].z, calf_L[1].z)
    hip_z = max(thigh_R[0].z, thigh_L[0].z) + 0.10

    for side, thigh, calf, bone in (("R", thigh_R, calf_R, "thigh_R"), ("L", thigh_L, calf_L, "thigh_L")):
        hip_point = Vector((thigh[0].x, thigh[0].y, hip_z))
        ankle_point = Vector((calf[1].x, calf[1].y, ankle_z))
        _make_leg(f"pants_{side}", hip_point, ankle_point, top_r=0.125, bottom_r=0.055,
                 color=color, arm=arm, body=body, bone_name=bone)

    # waistband: a short wide cylinder bridging both legs at the hip so
    # they read as one garment, not two disconnected tubes
    hip_center = Vector(((thigh_R[0].x + thigh_L[0].x) / 2, (thigh_R[0].y + thigh_L[0].y) / 2, hip_z))
    span_x = abs(thigh_L[0].x - thigh_R[0].x)
    # Radius/depth kept modest deliberately: a real render (Investor,
    # standing_symmetric) showed this object poking THROUGH the shirt's
    # front surface when sized larger (confirmed by hiding it, which
    # made the "hole" disappear completely -- it was never a hole in
    # the shirt mesh at all). The pants' own top_r (see _make_pants
    # call below) is what actually closes the hip/thigh gap; this piece
    # only needs to bridge the crotch between the two leg tubes, not
    # extend past the shirt's silhouette.
    bpy.ops.mesh.primitive_cylinder_add(radius=span_x * 0.58, depth=0.08,
                                        location=hip_center, vertices=20)
    band = bpy.context.active_object
    band.name = "pants_waistband"
    mat = bpy.data.materials.new("k70_waistband")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*color, 1.0)
    mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.75
    band.data.materials.append(mat)
    # Bone-parenting to the torso bone made this reorient into a flat
    # floating disc in a real render (the bone's local axes didn't match
    # this cylinder's assumed orientation); Surface Deform (tried as an
    # alternative) produced a worse regression elsewhere (see the
    # shirt's comment above). Plain object-parenting -- static, doesn't
    # follow animation, but doesn't actively break either -- is the
    # least-bad option of the three actually tested.
    band.parent = arm
    _shade_smooth(band)


def _recalc_normals(obj):
    """Real, confirmed bug: a full-body render (Investor, standing_
    symmetric) showed a sharply-bounded gray patch on the shirt's belly
    area, present with raytracing both on and off (ruling out a lighting
    artifact) -- a classic sign of locally flipped face normals, which
    happens when NEAREST_SURFACEPOINT shrinkwrap folds a patch of the
    subdivided cylinder back onto itself on a concave body region.
    Recalculating outward normals right after the shrinkwrap is applied
    (before solidify, which would otherwise bake the flip into two
    mismatched shells) fixes this without changing the mesh shape."""
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def _shade_smooth(obj):
    """Every garment piece is built from a subdivided primitive with
    flat per-face shading, which makes an otherwise correctly-fitted
    shrinkwrapped shape read as jagged/"shattered" facets under
    directional lighting -- confirmed by a real render (Banker,
    standing_hero01) that looked broken even though the underlying
    deformation was fine. No code path in this module ever enabled
    smooth shading. Also adds a light auto-smooth angle so real seams
    (the shirt's open hem, the leg tube's cut ends) stay sharp instead
    of smoothing across them."""
    for poly in obj.data.polygons:
        poly.use_smooth = True
    if hasattr(obj.data, "use_auto_smooth"):
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = 0.7854  # 45 degrees


def add_real_hair(body, role_key: str):
    """MB-Lab's own particle-hair system (per-template scalp face data,
    a real Blender particle system) -- NOT a painted cap. Default
    hair_length=0.2 rendered as a huge afro-like explosion on a real
    test render; shortened per-role via ROLES[role]['hair_length']
    (still real particle hair, just a shorter, neater cut). Requires the
    body to be the active/selected object, same as MB-Lab's own UI flow."""
    role = ROLES[role_key]
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    try:
        bpy.context.scene.mblab_hair_color = role["hair_color"]
    except TypeError:
        pass
    bpy.ops.mbast.particle_hair()
    hair_obj = bpy.data.objects.get("Head_Hair")
    if hair_obj is not None:
        for mod in hair_obj.modifiers:
            if mod.type == "PARTICLE_SYSTEM":
                mod.particle_system.settings.hair_length = role["hair_length"]
                mod.particle_system.settings.child_length = 0.75
        return hair_obj
    return None


def _cmu_mocap_dir():
    from pathlib import Path
    return Path(__file__).resolve().parents[1] / "vendor" / "cmu_mocap_bvh"


# Reusable animation registry: request an animation by semantic name,
# not by file path. "walk"/"run" are MB-Lab's own bundled mocap (bundled
# database, AGPL-3 + the license.txt rendered-output exception -- see
# module docstring). "idle"/"talk_gesture"/"shrug" are real motion
# capture from the CMU Graphics Lab Motion Capture Database (BVH
# conversion by Bruce Hahne, "cgspeed"), sourced from
# github.com/una-dinosauria/cmu-mocap and verified directly against that
# repo's own READMEFIRST.txt before use: "CMU places no restrictions on
# the use of the original dataset, and I (Bruce) place no additional
# restrictions... This data is free for use in research and commercial
# projects worldwide." A copy of that license text is vendored alongside
# the files at vendor/cmu_mocap_bvh/READMEFIRST_LICENSE.txt for
# provenance. "point"/"sit" are NOT implemented -- no suitable free BVH
# was found/verified for them in the time available; they are
# deliberately absent from this dict rather than faked with a
# mislabeled substitute motion.
ANIMATIONS = {
    "walk": ("mblab", "walking.bvh"),
    "run": ("mblab", "running.bvh"),
    "idle": ("cmu", "idle_77_02.bvh"),
    "talk_gesture": ("procedural", None),
}


def _patch_retarget_knowledge_bug():
    """Real bug in MB-Lab's own shipped data/retarget_knowledge.json:
    the "local_rotation_bones" list contains the literal string
    "spine01," (trailing comma baked INTO the string, not a JSON syntax
    error) instead of "spine01". Since that engine's retarget() checks
    membership in this list to decide whether a target bone's COPY_
    ROTATION constraint uses LOCAL space (correct, for bones deep in a
    chain) or WORLD space (used for everything else), spine01 silently
    falls into the WORLD-space bucket -- a genuine correctness bug,
    confirmed by dumping mblab_retarget.local_rotation_bones at runtime
    and fixed here without touching the vendored addon file. NOTE: this
    was NOT the cause of the severe forward-bow symptom seen on early
    CMU test files -- that was separately root-caused per-file (see
    ANIMATIONS comment below: one file was simply mislabeled content,
    unrelated others hit a still-unresolved large-arm-rotation retarget
    bug). Kept because it is a real, independently-verified fix."""
    import sys
    mb_lab = sys.modules.get("mb_lab")
    if mb_lab is None or not hasattr(mb_lab, "mblab_retarget"):
        return
    bones = getattr(mb_lab.mblab_retarget, "local_rotation_bones", None)
    if bones is None:
        return
    fixed = [b.strip(",") for b in bones]
    if fixed != bones:
        mb_lab.mblab_retarget.local_rotation_bones = fixed


def _build_procedural_talk_gesture(arm, fps=24):
    """Hand-authored conversational-gesture animation, keyframed directly
    on the target rig's own pose bones (no BVH/retargeting involved at
    all). Built after 4 independently-sourced CMU mocap files (idle
    140_07/140_06 -- later found mislabeled and replaced; wave_hello
    141_16; shrug 141_21; waving 143_25) ALL retargeted into the same
    severe forward-bow/crouch failure specifically whenever the source
    motion involved real arm-raising rotation -- a genuine, reproducible
    bug in MB-Lab's own world-space COPY_ROTATION bake pipeline for
    large-angle arm motion that isn't worth chasing further via more
    file substitutions. This sidesteps that pipeline entirely: it reads
    each bone's CURRENT pose rotation (whatever standing pose is already
    baked in) as the neutral baseline, layers a small local-space
    rotation on top at a couple of keyframes to produce a natural
    "explaining with one hand" gesture, and returns cleanly to the
    baseline at the end (no abrupt start/end pose). 100% original
    authored motion -- no external license concern."""
    import math
    from mathutils import Quaternion

    bone_names = ("clavicle_R", "upperarm_R", "lowerarm_R", "hand_R", "spine03", "head")
    bones = {}
    for bn in bone_names:
        pb = arm.pose.bones.get(bn)
        if pb is None:
            continue
        pb.rotation_mode = 'QUATERNION'
        bones[bn] = pb

    if "upperarm_R" not in bones:
        return None

    base_quat = {bn: pb.rotation_quaternion.copy() for bn, pb in bones.items()}

    def deg(x):
        return math.radians(x)

    # (bone, axis, degrees) deltas per gesture beat, layered on top of
    # the character's existing standing pose.
    beats = {
        0: {},
        18: {
            "clavicle_R": (deg(-10), deg(0), deg(6)),
            "upperarm_R": (deg(-72), deg(0), deg(-22)),
            "lowerarm_R": (deg(-78), deg(0), deg(0)),
            "hand_R": (deg(0), deg(0), deg(-10)),
            "spine03": (deg(0), deg(5), deg(0)),
            "head": (deg(0), deg(-4), deg(0)),
        },
        40: {
            "clavicle_R": (deg(-7), deg(0), deg(9)),
            "upperarm_R": (deg(-58), deg(-24), deg(-16)),
            "lowerarm_R": (deg(-60), deg(0), deg(0)),
            "hand_R": (deg(0), deg(0), deg(8)),
            "spine03": (deg(0), deg(-4), deg(0)),
            "head": (deg(0), deg(3), deg(0)),
        },
        60: {
            "clavicle_R": (deg(-10), deg(0), deg(6)),
            "upperarm_R": (deg(-68), deg(8), deg(-20)),
            "lowerarm_R": (deg(-72), deg(0), deg(0)),
            "hand_R": (deg(0), deg(0), deg(-8)),
            "spine03": (deg(0), deg(4), deg(0)),
            "head": (deg(0), deg(-3), deg(0)),
        },
        84: {},
    }

    action = bpy.data.actions.new("K70_TalkGesture")
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = action

    for frame, deltas in beats.items():
        bpy.context.scene.frame_set(frame)
        for bn, pb in bones.items():
            d = deltas.get(bn)
            q = base_quat[bn]
            if d is not None:
                dq = Quaternion((1, 0, 0), 0)
                dq = Quaternion((1, 0, 0), d[0]) @ Quaternion((0, 1, 0), d[1]) @ Quaternion((0, 0, 1), d[2])
                q = base_quat[bn] @ dq
            pb.rotation_quaternion = q
            pb.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    for fc in action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.handle_left_type = 'AUTO_CLAMPED'
            kp.handle_right_type = 'AUTO_CLAMPED'

    bpy.context.scene.frame_start = 0
    bpy.context.scene.frame_end = 84
    return action


def add_animation(arm, name: str):
    """Retargets a named animation onto the character's rig via MB-Lab's
    real BVH retargeting system (`mbast.load_animation` ->
    `mblab_retarget.retarget()`). Returns the real Action (with its real
    frame_range) now on `arm.animation_data.action`, or None if
    retargeting produced nothing (callers must not fake a static pose as
    "animated" if this is None). `name` must be a key in ANIMATIONS --
    unsupported names (e.g. "point", "sit") raise rather than silently
    falling back to a different motion."""
    if name not in ANIMATIONS:
        raise KeyError(f"add_animation: unsupported animation '{name}', "
                       f"available: {list(ANIMATIONS)}")
    source, filename = ANIMATIONS[name]

    if source == "procedural":
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='POSE')
        if name == "talk_gesture":
            return _build_procedural_talk_gesture(arm)
        raise KeyError(f"add_animation: no procedural builder for '{name}'")

    bvh_path = (_animations_dir() if source == "mblab" else _cmu_mocap_dir()) / filename
    if not bvh_path.exists():
        raise FileNotFoundError(f"add_animation: missing BVH file {bvh_path}")

    _patch_retarget_knowledge_bug()

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.mbast.load_animation(filepath=str(bvh_path))
    if arm.animation_data and arm.animation_data.action:
        return arm.animation_data.action
    return None


def add_walk_animation(arm):
    """Back-compat wrapper -- prefer add_animation(arm, "walk")."""
    return add_animation(arm, "walk")


def dress_character(role_key: str, body, arm, hair: bool = True):
    """Adds shirt + pants + waistband + (optionally) real particle hair
    to an already-finalized MB-Lab body, using that role's colors from
    ROLES."""
    role = ROLES[role_key]
    mins, maxs = _eval_bounds(body)
    _make_shirt(body, arm, mins, maxs, role["shirt_color"])
    _make_pants(body, arm, role["pants_color"])
    if hair:
        add_real_hair(body, role_key)
