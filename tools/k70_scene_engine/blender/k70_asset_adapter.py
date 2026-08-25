"""K70 VOXEL V4 -- CC0 asset adapter. Runs inside Blender.

Imports vetted, manually-downloaded CC0 asset packs (Kenney/Quaternius,
cached under vendor/cc0_assets/<source>/<pack>/) and adapts them to K70's
art direction:
  - deterministic import via bpy.ops.import_scene.* (fully scriptable,
    no GUI/addon dependency)
  - origin corrected to the object's own floor (bounding-box bottom
    center), regardless of the source file's internal pivot
  - flat shading forced (bpy.ops.object.shade_flat) -- removes any smooth
    shading the source asset may have used, matching K70's hard-edge rule
  - every Image Texture node's interpolation forced to 'Closest'
    (nearest-neighbor) -- keeps textures crisp/blocky instead of the
    smooth-filtered look the source pack ships with by default
  - optional palette tint (a Hue/Saturation node multiplying toward a
    target color) to harmonize an asset's colors with K70's muted palette
    without needing a full manual re-texture
  - every import is logged to PROVENANCE for the calling script to dump
    into metadata.json (source pack, asset file, license, adaptations)

Does NOT touch _voxel_human_v3_script.py, John, or any existing K70
character/lighting code. This is a new, additive module.
"""
from __future__ import annotations

import math
from pathlib import Path

import bpy

VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor"
CC0_DIR = VENDOR_DIR / "cc0_assets"

PROVENANCE: list[dict] = []

# Known-bad AUTHORED flat colors in specific CC0 source materials, keyed
# by material name (not by tint parameter -- a mesh can carry several
# materials, e.g. a tree's "woodBark" trunk alongside its "leafsGreen"
# canopy, and a blanket per-asset tint would wrongly recolor both). Add
# entries here only for materials verified to render wrong regardless of
# candidate/seed -- this is a one-time asset-data fix, not a per-shot one.
_KNOWN_BAD_FLAT_COLORS = {
    "leafsGreen": (0.22, 0.50, 0.18),  # Kenney nature-kit: authored as (0.16,0.79,0.67), a cyan-teal, not green
}

# Known sub-folder names per source pack (Kenney is inconsistent: most
# kits ship "GLB format", nature-kit ships "GLTF format" but the files
# inside are still plain single-file .glb).
_GLB_SUBDIRS = ["Models/GLB format", "Models/GLTF format", "Models"]


def _find_glb(source: str, pack: str, filename: str) -> Path:
    base = CC0_DIR / source / pack
    for sub in _GLB_SUBDIRS:
        candidate = base / sub / filename
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"CC0 asset not found: {source}/{pack}/*/{filename} (tried {_GLB_SUBDIRS})")


def _bbox_world(obj):
    coords = [obj.matrix_world @ v.co for v in obj.data.vertices] if obj.type == "MESH" else []
    return coords


def _recenter_origin_to_floor(mesh_objs):
    """Shift each mesh's own local origin so the combined bbox
    bottom-center sits at LOCAL (0,0,0) -- i.e. directly under the anchor
    once parented -- reliable regardless of how the source asset's own
    pivot was authored.

    IMPORTANT: this must NOT reference the anchor's location/scale at
    all. The meshes are still unparented, plain world-space objects at
    this point; matrix_parent_inverse is left at Blender's identity
    default (see import_cc0_asset), so anchor.matrix_world (location +
    rotation + scale) composes correctly on top of this anchor-relative
    offset afterward. An earlier version computed the shift relative to
    the anchor's own location and then also set
    `matrix_parent_inverse = anchor.matrix_world.inverted()` to try to
    cancel the resulting double-application -- but matrix_world isn't
    refreshed until a depsgraph update, so that inverse was read as
    identity, silently reintroducing the double-transform (confirmed via
    an isolated import test: a tree at anchor location -1.097 and scale
    1.849 rendered at world x=-3.125, i.e. -1.097*(1+1.849) -- the
    anchor's own translation being added a second time, scaled).
    """
    xs, ys, zs = [], [], []
    for o in mesh_objs:
        for v in o.data.vertices:
            world_co = o.matrix_world @ v.co
            xs.append(world_co.x)
            ys.append(world_co.y)
            zs.append(world_co.z)
    if not xs:
        return
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    floor_z = min(zs)
    for o in mesh_objs:
        o.location.x -= cx
        o.location.y -= cy
        o.location.z -= floor_z


def _force_flat_and_crisp(obj, palette_tint=None, saturation=1.0):
    if obj.type != "MESH":
        return
    bpy.context.view_layer.objects.active = obj
    for poly in obj.data.polygons:
        poly.use_smooth = False
    if obj.data.use_auto_smooth if hasattr(obj.data, "use_auto_smooth") else False:
        obj.data.use_auto_smooth = False
    for mat in obj.data.materials:
        if mat is None or not mat.use_nodes:
            continue
        nt = mat.node_tree
        for node in nt.nodes:
            if node.type == "TEX_IMAGE":
                node.interpolation = "Closest"
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.85
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.0
        if "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = 0.15
        if mat.name in _KNOWN_BAD_FLAT_COLORS:
            # Some Kenney materials ship as a flat, UNTEXTURED Base Color
            # whose authored value is simply wrong for what the material
            # is named -- found via tree_blocks.glb: its "leafsGreen"
            # material's flat color is actually (0.16, 0.79, 0.67), a
            # cyan-teal, not green, which rendered as a huge flat cyan
            # slab dominating the frame in K70 V5.2. Fixed at the
            # specific material-name level (not via the general
            # palette_tint path below) because a mesh can carry several
            # materials -- e.g. this same tree also has "woodBark" for
            # the trunk -- and a blanket per-asset tint would wrongly
            # recolor those too.
            bc = bsdf.inputs.get("Base Color")
            if bc is not None and not bc.is_linked:
                bc.default_value = (*_KNOWN_BAD_FLAT_COLORS[mat.name], 1.0)
        if palette_tint is not None:
            bc = bsdf.inputs.get("Base Color")
            if bc is not None and bc.is_linked:
                src_socket = bc.links[0].from_socket
                hsv = nt.nodes.new("ShaderNodeHueSaturation")
                hsv.inputs["Saturation"].default_value = saturation
                hsv.inputs["Color"].default_value = (*palette_tint, 1.0)
                nt.links.new(src_socket, hsv.inputs["Color"])
                nt.links.new(hsv.outputs["Color"], bc)


def import_cc0_asset(source: str, pack: str, filename: str, name: str,
                     location=(0.0, 0.0, 0.0), rotation_z_deg: float = 0.0, scale: float = 1.0,
                     license_: str = "CC0", creator: str = "Kenney", pack_url: str = "",
                     palette_tint=None, saturation: float = 1.0):
    """Import one CC0 glb, adapt it to K70 art direction, return the anchor
    Empty (so it can be parented/animated like any other K70 object)."""
    path = _find_glb(source, pack, filename)
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.gltf(filepath=str(path))
    new_objs = [o for o in bpy.data.objects if o.name not in before]
    mesh_objs = [o for o in new_objs if o.type == "MESH"]

    anchor = bpy.data.objects.new(f"{name}_anchor", None)
    bpy.context.collection.objects.link(anchor)
    anchor.location = location
    anchor.rotation_euler = (0, 0, math.radians(rotation_z_deg))
    anchor.scale = (scale, scale, scale)

    _recenter_origin_to_floor(mesh_objs) if mesh_objs else None

    top_level = [o for o in new_objs if o.parent is None or o.parent not in new_objs]
    for o in top_level:
        o.parent = anchor
        # matrix_parent_inverse is deliberately left at Blender's identity
        # default here (do NOT set it to anchor.matrix_world.inverted() --
        # see _recenter_origin_to_floor's docstring for why that silently
        # double-applies the anchor's transform). Identity is correct:
        # child.matrix_world = anchor.matrix_world @ child.matrix_basis,
        # so the anchor's location/rotation/scale composes normally on
        # top of the mesh's now anchor-relative (0,0,0-based) location.

    for o in mesh_objs:
        _force_flat_and_crisp(o, palette_tint=palette_tint, saturation=saturation)

    # Custom ID-property (not a return-signature change -- keeps every
    # existing caller, including the V4 hero scene, working unmodified)
    # so the director's visibility pass can find every mesh belonging to
    # this asset for occlusion/coverage testing.
    anchor["k70_mesh_names"] = [o.name for o in mesh_objs]

    PROVENANCE.append({
        "k70_name": name, "source": source, "pack": pack, "asset_file": filename,
        "creator": creator, "license": license_, "pack_url": pack_url,
        "adaptations": ["flat_shading", "nearest_neighbor_textures", "floor_origin_recentered"] +
                      (["palette_tint"] if palette_tint is not None else []),
    })
    return anchor


def dump_provenance() -> list[dict]:
    return list(PROVENANCE)
