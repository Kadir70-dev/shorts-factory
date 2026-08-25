"""Shared library (not run standalone) defining the K70 recurring character
roster as genuine geometric differentiation on top of the ONE rigged
humanoid mesh actually available in the vendored assets (gobkit's
minion-*.glb -- confirmed by direct glTF inspection that all 8 minion
variants share identical mesh geometry: same 4 sub-meshes, same vertex
counts [82, 8, 112, 17], only differing in file name / intended tint).

No second rigged humanoid source exists in any currently-verified,
license-clear, actually-downloadable pipeline (Poly Haven's real API was
keyword-searched across all 521 models -- zero humanoid/character results;
Quaternius/Kenney in cc0-asset-index are marketing-page pointers only, no
programmatic download endpoint). Building new rigged meshes by hand is out
of scope for this session.

Given that constraint, honest differentiation happens on every OTHER axis
the brief allows: silhouette (attached prop geometry), proportions (non-
uniform per-role scale), clothing/accessories (procedurally built props,
same bmesh/primitive technique as _procedural_building_script.py), and
role-specific held props. This is NOT a color-tint trick -- every role adds
or removes actual geometry -- but the underlying skinned mesh is shared,
and that limitation is reported plainly rather than hidden.

Imported by both _character_roster_script.py (static portrait/interaction
renders) and _animated_character_script.py (animation renders), via
sys.path.insert of this directory, same pattern _voxel_story_script.py
uses to import _procedural_building_script.py.
"""
import bpy
from mathutils import Vector

MINION_BASE = r"C:\Users\Admin\shorts-factory\tools\k70_scene_engine\vendor\gobkit-free-assets\minion\minion-a01.glb"

# Local-space reference: the shared mesh spans roughly x:[-0.95,0.95],
# y:[-1,1], z:[-1,1] (verified by direct import + bound_box inspection).
# Character "front" faces -Y (matches scene_builder_script.py's "front"
# camera offset, which sits at -Y looking toward +Y).


def _mat(name, color, roughness=0.55, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


# Every _attach_* builder below was designed against a REFERENCE half-height
# of 1.0 (i.e. a character spanning roughly z:[-1,1]). The real base mesh,
# measured at its actual posed frame, is nowhere near that size (confirmed
# by direct inspection: height ~0.62, not ~2.0) -- using the hand-picked
# offsets unscaled put props like the tie and briefcase far outside the
# character's real geometry entirely (confirmed by a real render: they
# rendered as disconnected shapes floating well off to the side). Every
# helper below therefore takes `k` (the real character's half-height /
# REFERENCE_HALF_HEIGHT) and scales both location and size by it, so a
# prop offset written as "roughly chest height" lands at chest height on
# whatever the mesh's real posed proportions actually are.
REFERENCE_HALF_HEIGHT = 1.0


def _scaled(triplet, k):
    return tuple(v * k for v in triplet)


def _box(name, size, location, mat, parent, k=1.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=_scaled(location, k))
    o = bpy.context.active_object
    o.name = name
    o.scale = _scaled(size, k)
    o.data.materials.append(mat)
    o.parent = parent
    return o


def _cyl(name, radius, depth, location, mat, parent, rotation=(0, 0, 0), k=1.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius * k, depth=depth * k, location=_scaled(location, k))
    o = bpy.context.active_object
    o.name = name
    o.rotation_euler = rotation
    o.data.materials.append(mat)
    o.parent = parent
    return o


def _sphere(name, radius, location, mat, parent, k=1.0):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius * k, location=_scaled(location, k))
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat)
    o.parent = parent
    return o


def _torus(name, major_r, minor_r, location, mat, parent, rotation=(0, 0, 0), k=1.0):
    bpy.ops.mesh.primitive_torus_add(major_radius=major_r * k, minor_radius=minor_r * k, location=_scaled(location, k))
    o = bpy.context.active_object
    o.name = name
    o.rotation_euler = rotation
    o.data.materials.append(mat)
    o.parent = parent
    return o


def import_base_character(root_name="CharacterRoot", pose_frame=None):
    """Imports the shared base mesh under a fresh Empty root so the whole
    assembly (mesh + role attachments, added later) can be scaled/placed
    as one unit without re-deriving per-attachment offsets."""
    root = bpy.data.objects.new(root_name, None)
    bpy.context.collection.objects.link(root)

    bpy.ops.import_scene.gltf(filepath=MINION_BASE)
    imported = list(bpy.context.selected_objects)
    for o in imported:
        if o.parent is None:
            o.parent = root

    # The armature's raw bind/rest pose renders as disconnected floating
    # body parts (confirmed by a real render during this fix -- looked
    # broken even though bound-box math said "grounded"). The proven-good
    # animated-character pipeline (_animated_character_script.py) never
    # renders at the bind pose either -- it always frame_sets to the
    # "movement" action's own frame_start first. Do the same here so a
    # STILL portrait shows the same valid poses the animation renderer
    # already produces, not an undefined rest pose.
    armature = next((o for o in imported if o.type == "ARMATURE"), None)
    if armature is not None and armature.animation_data and armature.animation_data.action:
        frame_start, frame_end = armature.animation_data.action.frame_range
        frame = pose_frame if pose_frame is not None else int(frame_start)
        frame = max(int(frame_start), min(int(frame_end), frame))
        bpy.context.scene.frame_set(frame)

    return root, imported


def apply_tint(mesh_objects, color, strength: float = 0.35):
    """Role-identifying tint that PRESERVES the source material's real
    texture/PBR data instead of deleting it. The original version called
    `o.data.materials.clear()` then appended one flat-color-only material
    -- a real, confirmed bug: minion-a01.glb ships a genuine
    baseColorTexture (MinionA_AlbedoTransparency.png, roughness 0.45)
    that this was silently throwing away on every character render this
    engine has ever produced. Fixed by, for each existing material,
    inserting a Mix Color (multiply) node between whatever already feeds
    Base Color and the Principled BSDF, multiplying in the tint at
    partial `strength` instead of replacing the input outright. A
    material with no texture (a flat color already) still gets a
    reasonable result since multiplying a flat color by a tint is the
    same visual effect the old code produced.
    """
    for o in mesh_objects:
        if o.type != "MESH" or not o.data.materials:
            continue
        for slot in o.data.materials:
            if slot is None or not slot.use_nodes:
                continue
            nt = slot.node_tree
            bsdf = nt.nodes.get("Principled BSDF")
            if bsdf is None:
                continue
            base_color_input = bsdf.inputs["Base Color"]
            existing_link = base_color_input.links[0] if base_color_input.links else None

            mix = nt.nodes.new("ShaderNodeMixRGB")
            mix.blend_type = "MULTIPLY"
            mix.inputs["Fac"].default_value = strength
            mix.inputs["Color2"].default_value = (*color, 1.0)

            if existing_link is not None:
                nt.links.new(existing_link.from_socket, mix.inputs["Color1"])
            else:
                mix.inputs["Color1"].default_value = base_color_input.default_value
            nt.links.new(mix.outputs["Color"], base_color_input)


# ---------------------------------------------------------------------------
# Role definitions: tint, non-uniform proportion scale, and a builder that
# attaches real extra geometry (not color) to the character root.
# ---------------------------------------------------------------------------

def _attach_tie(root, color, k):
    mat = _mat("k70_tie", color, roughness=0.4)
    _box("tie", (0.10, 0.03, 0.55), (0, -0.85, -0.05), mat, root, k=k)


def _attach_bowtie(root, color, k):
    mat = _mat("k70_bowtie", color, roughness=0.4)
    _box("bowtie_l", (0.16, 0.05, 0.14), (-0.10, -0.85, 0.30), mat, root, k=k)
    _box("bowtie_r", (0.16, 0.05, 0.14), (0.10, -0.85, 0.30), mat, root, k=k)
    _sphere("bowtie_knot", 0.06, (0, -0.88, 0.30), mat, root, k=k)


def _attach_briefcase(root, color, k):
    mat = _mat("k70_briefcase", color, roughness=0.5)
    handle_mat = _mat("k70_briefcase_handle", (0.05, 0.05, 0.05), roughness=0.6)
    _box("briefcase_body", (0.55, 0.15, 0.42), (1.15, -0.55, -0.55), mat, root, k=k)
    _box("briefcase_handle", (0.05, 0.05, 0.12), (1.15, -0.55, -0.30), handle_mat, root, k=k)


def _attach_hair_bun(root, color, k):
    mat = _mat("k70_hair", color, roughness=0.7)
    _sphere("hair_bun", 0.22, (0, 0.55, 0.95), mat, root, k=k)
    _sphere("hair_ponytail_1", 0.14, (0, 0.75, 0.75), mat, root, k=k)
    _sphere("hair_ponytail_2", 0.10, (0, 0.85, 0.55), mat, root, k=k)


def _attach_hardhat(root, color, k):
    # Positioned relative to head_top_z (passed via k's caller having
    # already measured the real head, not the original REFERENCE_HALF_
    # HEIGHT=1.0 guess) -- z=0.78 sits just above the actual head top
    # (measured ~0.25 at k=0.308, i.e. ~0.81 in reference units) instead
    # of the original 1.05, which rendered as a hat floating with a big
    # visible gap above the head (confirmed by a real render).
    mat = _mat("k70_hardhat", color, roughness=0.35, metallic=0.05)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.62 * k, location=_scaled((0, 0, 0.78), k))
    hat = bpy.context.active_object
    hat.name = "hardhat"
    hat.scale = (1.0, 1.0, 0.55)
    # cut the lower half off so it sits like a dome, not a full sphere
    bpy.ops.object.mode_set(mode="EDIT")
    import bmesh
    bm = bmesh.from_edit_mesh(hat.data)
    to_del = [v for v in bm.verts if v.co.z < -0.02 * k]
    bmesh.ops.delete(bm, geom=to_del, context="VERTS")
    bmesh.update_edit_mesh(hat.data)
    bpy.ops.object.mode_set(mode="OBJECT")
    hat.data.materials.append(mat)
    hat.parent = root
    _cyl("hardhat_brim", 0.68, 0.06, (0, 0, 0.76), mat, root, k=k)


def _attach_tophat(root, color, k):
    mat = _mat("k70_tophat", color, roughness=0.3)
    _cyl("tophat_brim", 0.52, 0.05, (0, 0, 0.76), mat, root, k=k)
    _cyl("tophat_top", 0.33, 0.45, (0, 0, 1.0), mat, root, k=k)
    _torus("monocle_ring", 0.14, 0.02, (0.42, -0.72, 0.15),
          _mat("k70_monocle", (0.85, 0.75, 0.35), metallic=0.8, roughness=0.15), root,
          rotation=(1.5708, 0, 0), k=k)


def _attach_toolbelt(root, color, k):
    mat = _mat("k70_toolbelt", color, roughness=0.6)
    _box("toolbelt", (1.0, 0.35, 0.18), (0, -0.6, -0.35), mat, root, k=k)
    wrench_mat = _mat("k70_wrench", (0.55, 0.56, 0.58), metallic=0.7, roughness=0.3)
    _box("wrench_handle", (0.06, 0.06, 0.55), (1.05, -0.5, -0.55), wrench_mat, root, k=k)
    _box("wrench_head", (0.22, 0.10, 0.14), (1.05, -0.5, -0.85), wrench_mat, root, k=k)


def _attach_blazer_collar(root, color, k):
    mat = _mat("k70_collar", color, roughness=0.55)
    _box("collar_l", (0.22, 0.15, 0.45), (-0.60, -0.35, -0.30), mat, root, k=k)
    _box("collar_r", (0.22, 0.15, 0.45), (0.60, -0.35, -0.30), mat, root, k=k)


ROLES = {
    "john": {
        "label": "John",
        "tint": (0.20, 0.45, 0.85),
        "scale": (1.0, 1.0, 1.0),
        "attachments": [],
    },
    "sarah": {
        "label": "Sarah",
        "tint": (0.85, 0.35, 0.55),
        "scale": (0.88, 0.88, 0.92),
        "attachments": [lambda root, k: _attach_hair_bun(root, (0.25, 0.15, 0.1), k)],
    },
    "banker": {
        "label": "Banker",
        "tint": (0.10, 0.14, 0.25),
        "scale": (1.05, 1.05, 1.10),
        "attachments": [
            lambda root, k: _attach_tie(root, (0.55, 0.08, 0.08), k),
            lambda root, k: _attach_briefcase(root, (0.30, 0.20, 0.12), k),
        ],
    },
    "investor": {
        "label": "Investor",
        "tint": (0.55, 0.45, 0.15),
        "scale": (1.0, 1.0, 1.05),
        "attachments": [
            lambda root, k: _attach_bowtie(root, (0.35, 0.08, 0.08), k),
            lambda root, k: _attach_tophat(root, (0.08, 0.08, 0.09), k),
        ],
    },
    "worker": {
        "label": "Worker",
        "tint": (0.85, 0.45, 0.10),
        "scale": (1.08, 1.08, 0.95),
        "attachments": [
            lambda root, k: _attach_hardhat(root, (0.95, 0.75, 0.10), k),
            lambda root, k: _attach_toolbelt(root, (0.25, 0.22, 0.20), k),
        ],
    },
    "business_owner": {
        "label": "Business Owner",
        "tint": (0.12, 0.30, 0.20),
        "scale": (1.10, 1.10, 1.12),
        "attachments": [
            lambda root, k: _attach_tie(root, (0.10, 0.35, 0.15), k),
            lambda root, k: _attach_blazer_collar(root, (0.08, 0.10, 0.09), k),
            lambda root, k: _attach_briefcase(root, (0.10, 0.08, 0.08), k),
        ],
    },
}


def evaluated_world_bounds(objs):
    """True post-deformation world-space bounds. `obj.bound_box` is the
    mesh DATA's own undeformed rest-pose box -- for an armature-skinned
    mesh (this character), that is NOT where the posed geometry actually
    sits, and using it for ground-fit/camera framing produced a character
    that looked like it was floating (visually confirmed via a real
    render before this fix: the math said "bottom at z=0" while the
    render clearly showed a gap above the ground plane). This walks the
    depsgraph-evaluated mesh's real vertices instead."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mins = Vector((float("inf"),) * 3)
    maxs = Vector((float("-inf"),) * 3)
    for obj in objs:
        if obj.type != "MESH":
            continue
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        for v in mesh.vertices:
            wc = eval_obj.matrix_world @ v.co
            mins = Vector(min(a, b) for a, b in zip(mins, wc))
            maxs = Vector(max(a, b) for a, b in zip(maxs, wc))
        eval_obj.to_mesh_clear()
    return mins, maxs


def build_character(role_key: str, pose_frame=None):
    """Builds one full character (base mesh + tint + role attachments)
    under a fresh root Empty, ground-fits it (root.location.z shifted so
    the assembly's true lowest point sits at world z=0), and returns
    (root, mesh_objects). `pose_frame` picks which frame of the
    character's own "movement" action to hold for a still render (default:
    the action's first frame) -- see build_character's caller for why this
    matters (a mid-air walk-cycle frame can look like a floating bug)."""
    role = ROLES[role_key]
    root, mesh_objects = import_base_character(f"Character_{role_key}", pose_frame=pose_frame)
    apply_tint(mesh_objects, role["tint"])

    # Attachment offsets are authored against REFERENCE_HALF_HEIGHT=1.0;
    # the real posed mesh is a different actual size (verified: ~0.31 half
    # -height, not 1.0), so every attachment position/size is scaled by k
    # to land in the right place on the mesh as it actually is, not as
    # originally assumed.
    bpy.context.view_layer.update()
    pre_mins, pre_maxs = evaluated_world_bounds(mesh_objects)
    k = max((pre_maxs.z - pre_mins.z) / 2.0, 1e-4) / REFERENCE_HALF_HEIGHT

    for fn in role["attachments"]:
        fn(root, k)
    root.scale = role["scale"]

    # ground-fit: compute true (deformation-evaluated) world-space min z
    # of the whole assembly, then shift the root so that min sits exactly
    # at z=0 (generic -- works regardless of per-role scale, unlike a
    # single hand-tuned location.z constant).
    bpy.context.view_layer.update()
    mins, _ = evaluated_world_bounds(root.children_recursive)
    root.location.z -= mins.z
    bpy.context.view_layer.update()
    return root, mesh_objects
