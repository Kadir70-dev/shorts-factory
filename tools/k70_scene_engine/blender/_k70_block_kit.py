"""K70 VOXEL V3 -- block-world kit. Runs inside Blender.

Core primitive: a manually-built (bmesh) cube with EXPLICIT per-face UVs
(not dependent on Blender's default primitive_cube_add face ordering,
which is not something to rely on for correctness) so a 6-region texture
atlas maps predictably onto front/back/left/right/top/bottom.

Two box variants:
  - textured_box()         -- full 3x2 atlas (per-face-type art), used for
                               character body parts (see gen_k70_skin.py).
  - simple_textured_box()  -- one square tile stretched 0..1 on every
                               face, used for environment blocks (see
                               gen_k70_env_textures.py).

Both default to ZERO bevel and FLAT shading (poly.use_smooth = False) --
this is the deliberate V3 fix for the "rounded plastic toy" look. A tiny
bevel is allowed (kwarg) only if a specific piece needs it for render
stability; default is 0.0.

Nearest-neighbor ('Closest') texture interpolation is hard-set on every
material this module creates -- pixels must never be blurred.

Import from a scene script with:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _k70_block_kit as bk
"""
from __future__ import annotations

import math
from pathlib import Path

import bmesh
import bpy

VENDOR_TEX_DIR = Path(__file__).resolve().parents[1] / "vendor" / "k70_textures"
CHAR_TEX_DIR = VENDOR_TEX_DIR / "characters"
ENV_TEX_DIR = VENDOR_TEX_DIR / "environment"

_image_cache: dict[str, "bpy.types.Image"] = {}
_material_cache: dict[str, "bpy.types.Material"] = {}


def _load_image(path: Path):
    key = str(path)
    if key not in _image_cache:
        if not path.exists():
            raise FileNotFoundError(f"K70 texture not found: {path}")
        img = bpy.data.images.load(key)
        img.colorspace_settings.name = "sRGB"
        _image_cache[key] = img
    return _image_cache[key]


def _atlas_material(path: Path, roughness: float = 0.85) -> "bpy.types.Material":
    key = f"atlas::{path}"
    if key in _material_cache:
        return _material_cache[key]
    mat = bpy.data.materials.new(f"k70_atlas_{path.stem}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.0
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = _load_image(path)
    tex.interpolation = "Closest"  # nearest-neighbor -- pixels stay crisp, never blurred
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    _material_cache[key] = mat
    return mat


# ---- atlas UV layout: 3 cols x 2 rows, matches gen_k70_skin.py exactly ---- #
# front/back/left in the TOP half of the image (UV v 0.5-1.0),
# right/top/bottom in the BOTTOM half (UV v 0.0-0.5).
_ATLAS_CELLS = {
    "front":  (0, True), "back": (1, True), "left": (2, True),
    "right":  (0, False), "top": (1, False), "bottom": (2, False),
}


def _cell_uv(face_name: str) -> tuple[float, float, float, float]:
    col, upper = _ATLAS_CELLS[face_name]
    u0, u1 = col / 3.0, (col + 1) / 3.0
    v0, v1 = (0.5, 1.0) if upper else (0.0, 0.5)
    return u0, v0, u1, v1


def _build_cube_bmesh(size):
    sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
    bm = bmesh.new()
    v = {}
    for xi in (-1, 1):
        for yi in (-1, 1):
            for zi in (-1, 1):
                v[(xi, yi, zi)] = bm.verts.new((xi * sx, yi * sy, zi * sz))
    # each face listed (bottom-left, bottom-right, top-right, top-left) by
    # Z, viewed from OUTSIDE the box along that face's outward normal.
    faces = {
        "front":  bm.faces.new([v[(-1, -1, -1)], v[(1, -1, -1)], v[(1, -1, 1)], v[(-1, -1, 1)]]),   # -Y
        "back":   bm.faces.new([v[(1, 1, -1)], v[(-1, 1, -1)], v[(-1, 1, 1)], v[(1, 1, 1)]]),        # +Y
        "left":   bm.faces.new([v[(-1, 1, -1)], v[(-1, -1, -1)], v[(-1, -1, 1)], v[(-1, 1, 1)]]),    # -X
        "right":  bm.faces.new([v[(1, -1, -1)], v[(1, 1, -1)], v[(1, 1, 1)], v[(1, -1, 1)]]),        # +X
        "top":    bm.faces.new([v[(-1, -1, 1)], v[(1, -1, 1)], v[(1, 1, 1)], v[(-1, 1, 1)]]),        # +Z
        "bottom": bm.faces.new([v[(-1, 1, -1)], v[(1, 1, -1)], v[(1, -1, -1)], v[(-1, -1, -1)]]),    # -Z
    }
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    return bm, faces


def _finalize_mesh(name, bm, location, material, bevel: float):
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = False  # FLAT shading -- hard block edges, no soft toy look
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.data.materials.append(material)
    if bevel > 0.0:
        bev = obj.modifiers.new("bevel", type="BEVEL")
        bev.width = bevel
        bev.segments = 1  # single segment = a hard chamfer, not a rounded soap-bar edge
    return obj


def textured_box(name, size, location, atlas_dir: Path, bevel: float = 0.0, roughness: float = 0.85):
    """A box whose 6 faces sample the 6 regions of a 3x2 character atlas
    (see gen_k70_skin.py). `atlas_dir` is the PNG file for this specific
    body part (e.g. .../characters/john/head.png)."""
    mat = _atlas_material(atlas_dir, roughness=roughness)
    bm, faces = _build_cube_bmesh(size)
    uv_layer = bm.loops.layers.uv.new()
    for face_name, face in faces.items():
        u0, v0, u1, v1 = _cell_uv(face_name)
        corners = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        for loop, uv in zip(face.loops, corners):
            loop[uv_layer].uv = uv
    return _finalize_mesh(name, bm, location, mat, bevel)


def simple_textured_box(name, size, location, tex_path: Path, bevel: float = 0.0, roughness: float = 0.85):
    """A box whose every face is the SAME square tile stretched 0..1 --
    for environment materials (concrete/road/wood/glass/brick/grass/
    leaves/metal/office_surface, see gen_k70_env_textures.py)."""
    mat = _atlas_material(tex_path, roughness=roughness)
    bm, faces = _build_cube_bmesh(size)
    uv_layer = bm.loops.layers.uv.new()
    corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    for face in faces.values():
        for loop, uv in zip(face.loops, corners):
            loop[uv_layer].uv = uv
    return _finalize_mesh(name, bm, location, mat, bevel)


def env_tex(name: str) -> Path:
    return ENV_TEX_DIR / f"{name}.png"


def sign_tex(key: str) -> Path:
    return ENV_TEX_DIR / "signs" / f"{key}.png"


def char_tex(role: str, part: str) -> Path:
    return CHAR_TEX_DIR / role / f"{part}.png"


# ==================================================================== #
# ENVIRONMENT PRIMITIVES -- all block-grid, all K70 pixel materials
# ==================================================================== #

def build_road_segment(name, location, length, width=1.6):
    return simple_textured_box(name, (width, length, 0.02), (location[0], location[1], location[2] + 0.01),
                                env_tex("road"), roughness=0.8)


def build_sidewalk_segment(name, location, length, width=0.9):
    return simple_textured_box(name, (width, length, 0.06), (location[0], location[1], location[2] + 0.03),
                                env_tex("concrete"), roughness=0.9)


def build_wall_panel(name, location, w, h, thickness=0.12, material="concrete"):
    return simple_textured_box(name, (w, thickness, h), (location[0], location[1], location[2] + h / 2),
                                env_tex(material), roughness=0.85)


def build_window(name, location, w=0.5, h=0.6, thickness=0.04):
    return simple_textured_box(name, (w, thickness, h), location, env_tex("glass"), roughness=0.15)


def build_door(name, location, w=0.5, h=1.1, thickness=0.06):
    return simple_textured_box(name, (w, thickness, h), (location[0], location[1], location[2] + h / 2),
                                env_tex("wood"), roughness=0.7)


def build_streetlamp(name, location, height=2.2):
    pole = simple_textured_box(f"{name}_pole", (0.08, 0.08, height), (location[0], location[1], location[2] + height / 2),
                                env_tex("metal"), roughness=0.4)
    glow_mat_key = f"glow::{name}"
    glow = simple_textured_box(f"{name}_head", (0.22, 0.22, 0.16), (location[0], location[1], location[2] + height + 0.05),
                               env_tex("metal"), roughness=0.4)
    bsdf = glow.data.materials[0].node_tree.nodes.get("Principled BSDF")
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.88, 0.62, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 1.4
    return pole, glow


def build_tree(name, location, trunk_h=0.7, canopy_size=0.7):
    trunk = simple_textured_box(f"{name}_trunk", (0.14, 0.14, trunk_h), (location[0], location[1], location[2] + trunk_h / 2),
                                env_tex("wood"), roughness=0.8)
    canopy = simple_textured_box(f"{name}_canopy", (canopy_size, canopy_size, canopy_size),
                                 (location[0], location[1], location[2] + trunk_h + canopy_size / 2),
                                 env_tex("leaves"), roughness=0.9)
    return trunk, canopy


def build_house(name, location, w=2.4, d=2.2, h=1.7, roof_h=0.6):
    body = simple_textured_box(f"{name}_body", (w, d, h), (location[0], location[1], location[2] + h / 2),
                               env_tex("brick"), roughness=0.85)
    roof = simple_textured_box(f"{name}_roof", (w * 1.05, d * 1.05, roof_h),
                               (location[0], location[1], location[2] + h + roof_h / 2),
                               env_tex("wood"), roughness=0.75)
    door = build_door(f"{name}_door", (location[0], location[1] - d / 2 - 0.02, location[2]), w=0.5, h=1.0)
    win1 = build_window(f"{name}_win1", (location[0] - w * 0.28, location[1] - d / 2 - 0.02, location[2] + h * 0.6))
    win2 = build_window(f"{name}_win2", (location[0] + w * 0.28, location[1] - d / 2 - 0.02, location[2] + h * 0.6))
    return [body, roof, door, win1, win2]


def build_desk(name, location, w=1.0, d=0.55, h=0.72):
    top = simple_textured_box(f"{name}_top", (w, d, 0.05), (location[0], location[1], location[2] + h),
                              env_tex("wood"), roughness=0.6)
    legs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            leg = simple_textured_box(f"{name}_leg_{sx}_{sy}", (0.05, 0.05, h),
                                      (location[0] + sx * (w / 2 - 0.05), location[1] + sy * (d / 2 - 0.05), location[2] + h / 2),
                                      env_tex("metal"), roughness=0.4)
            legs.append(leg)
    return [top] + legs


def build_chair(name, location, seat_h=0.46):
    seat = simple_textured_box(f"{name}_seat", (0.42, 0.42, 0.06), (location[0], location[1], location[2] + seat_h),
                               env_tex("wood"), roughness=0.6)
    back = simple_textured_box(f"{name}_back", (0.42, 0.05, 0.45),
                               (location[0], location[1] + 0.18, location[2] + seat_h + 0.22),
                               env_tex("wood"), roughness=0.6)
    leg = simple_textured_box(f"{name}_leg", (0.06, 0.06, seat_h), (location[0], location[1], location[2] + seat_h / 2),
                              env_tex("metal"), roughness=0.4)
    return [seat, back, leg]


def build_laptop(name, location):
    base = simple_textured_box(f"{name}_base", (0.34, 0.24, 0.02), (location[0], location[1], location[2] + 0.01),
                               env_tex("metal"), roughness=0.35)
    screen = simple_textured_box(f"{name}_screen", (0.34, 0.02, 0.22),
                                 (location[0], location[1] - 0.10, location[2] + 0.12),
                                 env_tex("office_surface"), roughness=0.3)
    return [base, screen]


def build_counter(name, location, w=1.6, d=0.6, h=0.95):
    body = simple_textured_box(f"{name}_body", (w, d, h), (location[0], location[1], location[2] + h / 2),
                               env_tex("wood"), roughness=0.6)
    top = simple_textured_box(f"{name}_top", (w * 1.02, d * 1.05, 0.05), (location[0], location[1], location[2] + h),
                              env_tex("office_surface"), roughness=0.3)
    return [body, top]


def build_sign(name, location, w=0.9, h=0.4, color_tex="metal"):
    return simple_textured_box(name, (w, 0.04, h), location, env_tex(color_tex), roughness=0.4)


# ==================================================================== #
# V3.1 additions -- density/story vocabulary. All reuse the same
# simple_textured_box primitive; no new geometry technique introduced.
# ==================================================================== #

def build_signboard(name, location, sign_key, w=0.5, h=0.2, thickness=0.03):
    return simple_textured_box(name, (w, thickness, h), location, sign_tex(sign_key), roughness=0.5)


def build_building_multistory(name, location, floors=3, w=2.2, d=2.0, floor_h=0.85,
                              wall_material="concrete", roof_material="wood",
                              window_every=1, ground_shop=False, shop_sign_key=None):
    """A stacked multi-floor block building -- ground floor optionally a
    shopfront (awning + signboard), upper floors get a window band per
    floor. This is the main density workhorse for the city shots."""
    objs = []
    total_h = floors * floor_h
    body = simple_textured_box(f"{name}_body", (w, d, total_h),
                               (location[0], location[1], location[2] + total_h / 2),
                               env_tex(wall_material), roughness=0.85)
    objs.append(body)
    roof = simple_textured_box(f"{name}_roof", (w * 1.04, d * 1.04, floor_h * 0.22),
                               (location[0], location[1], location[2] + total_h + floor_h * 0.11),
                               env_tex(roof_material), roughness=0.75)
    objs.append(roof)
    for f in range(floors):
        if f == 0 and ground_shop:
            awning = simple_textured_box(f"{name}_awning_{f}", (w * 1.02, 0.28, 0.10),
                                         (location[0], location[1] - d / 2 - 0.12, location[2] + floor_h * 0.85),
                                         env_tex("metal"), roughness=0.5)
            objs.append(awning)
            if shop_sign_key:
                sign = build_signboard(f"{name}_sign", (location[0], location[1] - d / 2 - 0.03, location[2] + floor_h * 0.55),
                                       shop_sign_key, w=w * 0.55, h=floor_h * 0.28)
                objs.append(sign)
            win = build_window(f"{name}_gwin", (location[0] + w * 0.28, location[1] - d / 2 - 0.02, location[2] + floor_h * 0.5),
                               w=w * 0.22, h=floor_h * 0.55)
            objs.append(win)
            continue
        if f % window_every == 0:
            for side_sign in (-1, 1):
                win = build_window(f"{name}_win_{f}_{side_sign}",
                                   (location[0] + side_sign * w * 0.26, location[1] - d / 2 - 0.02,
                                    location[2] + f * floor_h + floor_h * 0.55),
                                   w=w * 0.24, h=floor_h * 0.45)
                objs.append(win)
    return objs


def build_traffic_light(name, location, height=1.5):
    pole = simple_textured_box(f"{name}_pole", (0.07, 0.07, height), (location[0], location[1], location[2] + height / 2),
                               env_tex("metal"), roughness=0.4)
    box = simple_textured_box(f"{name}_box", (0.12, 0.12, 0.3), (location[0], location[1], location[2] + height + 0.15),
                              env_tex("metal"), roughness=0.4)
    lights = []
    for i, col in enumerate([(0.85, 0.15, 0.12), (0.85, 0.75, 0.1), (0.15, 0.75, 0.2)]):
        lamp = simple_textured_box(f"{name}_lamp_{i}", (0.02, 0.06, 0.06),
                                   (location[0], location[1] - 0.07, location[2] + height + 0.27 - i * 0.09),
                                   env_tex("metal"), roughness=0.3)
        bsdf = lamp.data.materials[0].node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*col, 1.0)
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*col, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 1.2 if i == 0 else 0.15
        lights.append(lamp)
    return [pole, box] + lights


def build_bench(name, location, rotation_facing_y=True):
    seat = simple_textured_box(f"{name}_seat", (0.9, 0.32, 0.05), (location[0], location[1], location[2] + 0.28),
                               env_tex("wood"), roughness=0.7)
    back = simple_textured_box(f"{name}_back", (0.9, 0.05, 0.35), (location[0], location[1] + 0.13, location[2] + 0.45),
                               env_tex("wood"), roughness=0.7)
    legs = []
    for sx in (-1, 1):
        leg = simple_textured_box(f"{name}_leg_{sx}", (0.05, 0.30, 0.28), (location[0] + sx * 0.38, location[1], location[2] + 0.14),
                                  env_tex("metal"), roughness=0.4)
        legs.append(leg)
    return [seat, back] + legs


def build_bin(name, location):
    body = simple_textured_box(f"{name}_body", (0.24, 0.24, 0.4), (location[0], location[1], location[2] + 0.2),
                               env_tex("metal"), roughness=0.45)
    lid = simple_textured_box(f"{name}_lid", (0.27, 0.27, 0.04), (location[0], location[1], location[2] + 0.42),
                              env_tex("metal"), roughness=0.4)
    return [body, lid]


def build_fence_segment(name, location, length=1.2, height=0.5):
    rails = []
    for i, z in enumerate((0.15, 0.35)):
        rail = simple_textured_box(f"{name}_rail_{i}", (length, 0.03, 0.04), (location[0], location[1], location[2] + z),
                                   env_tex("wood"), roughness=0.7)
        rails.append(rail)
    n_posts = max(2, int(length / 0.4) + 1)
    posts = []
    for i in range(n_posts):
        px = location[0] - length / 2 + i * (length / (n_posts - 1))
        post = simple_textured_box(f"{name}_post_{i}", (0.04, 0.04, height), (px, location[1], location[2] + height / 2),
                                   env_tex("wood"), roughness=0.7)
        posts.append(post)
    return rails + posts


def build_planter(name, location, with_bush=True):
    box = simple_textured_box(f"{name}_box", (0.36, 0.36, 0.22), (location[0], location[1], location[2] + 0.11),
                              env_tex("concrete"), roughness=0.8)
    objs = [box]
    if with_bush:
        bush = simple_textured_box(f"{name}_bush", (0.30, 0.30, 0.26), (location[0], location[1], location[2] + 0.22 + 0.13),
                                   env_tex("leaves"), roughness=0.9)
        objs.append(bush)
    return objs


def build_crosswalk(name, location, width=1.8, n_stripes=5, stripe_len=0.28):
    stripes = []
    spacing = width / n_stripes
    for i in range(n_stripes):
        x = location[0] - width / 2 + spacing * (i + 0.5)
        s = simple_textured_box(f"{name}_stripe_{i}", (spacing * 0.55, stripe_len, 0.006),
                                (x, location[1], location[2] + 0.003), env_tex("office_surface"), roughness=0.9)
        stripes.append(s)
    return stripes


def build_vehicle(name, location, rotation_z_deg=0.0, kind="car", color=(0.65, 0.15, 0.15)):
    """A simple blocky K70 vehicle -- 'car'/'taxi'/'delivery' differ only
    in size/color/roof-shape, same construction language as everything
    else in this kit. rotation_z_deg lets it face along the road."""
    import math as _m
    rad = _m.radians(rotation_z_deg)
    cx, cy, cz = location

    def _rot(dx, dy):
        return (cx + dx * _m.cos(rad) - dy * _m.sin(rad), cy + dx * _m.sin(rad) + dy * _m.cos(rad), cz)

    dims = {"car": (0.42, 0.9, 0.34), "taxi": (0.44, 0.95, 0.36), "delivery": (0.5, 1.3, 0.55)}
    w, length, h = dims.get(kind, dims["car"])
    body = simple_textured_box(f"{name}_body", (w, length, h), _rot(0, 0), env_tex("metal"), roughness=0.35)
    bsdf = body.data.materials[0].node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    cabin_h = h * 0.55 if kind != "delivery" else h * 0.2
    cabin = simple_textured_box(f"{name}_cabin", (w * 0.9, length * 0.5, cabin_h),
                                (cx, cy - length * 0.05 * _m.cos(rad), cz + h / 2 + cabin_h / 2),
                                env_tex("glass_tint"), roughness=0.2)
    wheels = []
    for dx, dy in ((-w / 2, length * 0.32), (w / 2, length * 0.32), (-w / 2, -length * 0.32), (w / 2, -length * 0.32)):
        wx, wy, wz = _rot(dx, dy)
        wheel = simple_textured_box(f"{name}_wheel_{dx:.2f}_{dy:.2f}", (0.10, 0.10, 0.16), (wx, wy, cz - h / 2 + 0.05),
                                    env_tex("metal"), roughness=0.6)
        wb = wheel.data.materials[0].node_tree.nodes.get("Principled BSDF")
        wb.inputs["Base Color"].default_value = (0.05, 0.05, 0.05, 1.0)
        wheels.append(wheel)
    return [body, cabin] + wheels


def build_distant_skyline(name, location, n_buildings=6, spread=8.0, min_h=1.2, max_h=3.2, depth_offset=0.0, seed=7):
    """Low-detail large silhouette buildings far behind the main set --
    keeps the FAR background as actual K70 block geometry (flat-shaded,
    simple materials) instead of empty sky, so the world never suddenly
    reveals a photographic backdrop past the built foreground."""
    import random as _r
    rnd = _r.Random(seed)
    objs = []
    materials = ["concrete", "brick_dark", "wood_dark"]
    for i in range(n_buildings):
        x = location[0] - spread / 2 + spread * i / max(n_buildings - 1, 1) + rnd.uniform(-0.3, 0.3)
        h = rnd.uniform(min_h, max_h)
        w = rnd.uniform(0.8, 1.6)
        mat = materials[rnd.randrange(len(materials))]
        b = simple_textured_box(f"{name}_{i}", (w, 0.9, h), (x, location[1] + depth_offset, location[2] + h / 2),
                                env_tex(mat), roughness=0.95)
        objs.append(b)
    return objs


def build_distant_ground(name, location, size=40.0, material="grass"):
    """A large flat ground plane extending toward the horizon, textured
    with a K70 pixel material -- replaces any 'infinite ground fading
    into a photographic horizon' look with actual stylized geometry."""
    return simple_textured_box(name, (size, size, 0.02), (location[0], location[1], location[2] - 0.01),
                               env_tex(material), roughness=0.9)


def build_money_prop(name, location, n=1):
    objs = []
    for i in range(max(n, 1)):
        b = simple_textured_box(f"{name}_{i}", (0.22, 0.10, 0.015), (location[0], location[1], location[2] + 0.008 + i * 0.016),
                                env_tex("office_surface"), roughness=0.5)
        bsdf = b.data.materials[0].node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.20, 0.55, 0.30, 1.0)
        objs.append(b)
    return objs
