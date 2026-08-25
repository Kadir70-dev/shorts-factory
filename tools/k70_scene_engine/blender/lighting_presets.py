"""Reusable premium lighting presets, runs INSIDE Blender.

Replaces the old fixed-constant three-point-light studio
(`scene_builder_script.py::_build_studio`) as the ONLY lighting language
this engine has. That system still exists (cheap, fast, fine for a quick
prop/building proof render) -- this module adds real HDRI-based
environment lighting for anything that needs to look genuinely lit, not
just visible.

HDRIs are real, CC0, MD5-verified downloads from Poly Haven (same
verified pipeline as `catalog/sources/polyhaven.py`), stored under
`vendor/polyhaven_hdri/`. Five curated environments cover the finance-
documentary shot list this engine actually needs: a soft neutral studio
for portraits, a clean daylight sky for exteriors, a warm low-angle sky
for cinematic golden-hour exteriors, an office-interior ambient set, and
a modern-buildings environment for city-adjacent shots.
"""
from __future__ import annotations

import math as _math
from pathlib import Path

import bpy
from mathutils import Vector

HDRI_DIR = Path(__file__).resolve().parents[1] / "vendor" / "polyhaven_hdri"

PRESETS = {
    "portrait_studio": {"hdri": "brown_photostudio_02_2k.hdr", "strength": 1.1,
                        "desc": "Soft neutral studio light -- character portraits, product inserts."},
    "exterior_day": {"hdri": "hausdorf_clear_sky_2k.hdr", "strength": 1.0,
                     "desc": "Clean daylight sky -- house/street/city exteriors."},
    "golden_hour": {"hdri": "dikhololo_sunset_2k.hdr", "strength": 1.15,
                    "desc": "Warm low-angle cinematic exterior light."},
    "office_interior": {"hdri": "unfinished_office_2k.hdr", "strength": 0.9,
                        "desc": "Office/interior ambient illumination."},
    "city": {"hdri": "modern_buildings_2_2k.hdr", "strength": 1.0,
            "desc": "Modern-buildings environment -- city-adjacent establishing shots."},
}

_loaded_images: dict[str, "bpy.types.Image"] = {}


def _load_hdri(filename: str):
    if filename not in _loaded_images:
        path = HDRI_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"HDRI not found: {path} (expected a curated Poly Haven download)")
        _loaded_images[filename] = bpy.data.images.load(str(path))
    return _loaded_images[filename]


def apply_hdri_world(preset: str, rotation_z: float = 0.0, strength_override: float | None = None):
    """Sets `bpy.context.scene.world` to an HDRI environment. This alone
    both lights and fills the background -- for a character/prop shot
    where the HDRI itself shouldn't be directly visible (e.g. a plain
    portrait against a controlled backdrop), pair this with a ground
    plane and let camera framing crop the background, same as the
    existing `_build_studio` ground-plane convention."""
    if preset not in PRESETS:
        raise ValueError(f"unknown lighting preset '{preset}', expected one of {list(PRESETS)}")
    spec = PRESETS[preset]
    world = bpy.data.worlds.new(f"k70_world_{preset}")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    mapping_input = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0, 0, rotation_z)
    env_tex = nt.nodes.new("ShaderNodeTexEnvironment")
    env_tex.image = _load_hdri(spec["hdri"])
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength_override if strength_override is not None else spec["strength"]
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(mapping_input.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env_tex.inputs["Vector"])
    nt.links.new(env_tex.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return world


def setup_block_world_v3(sun_rotation=(0.9, 0, 0.6), sun_energy: float = 4.0,
                         ambient_preset: str = "exterior_day", ambient_strength: float = 0.18,
                         sky_color=(0.55, 0.68, 0.85)):
    """K70 VOXEL V3 lighting: a strong directional SUN as the dominant key
    light (crisp, defined shadow edges -- what flat-shaded block geometry
    needs to read as 'block world' rather than 'soft HDRI-lit toy'), plus
    the existing HDRI only as a LOW-strength ambient fill/reflection cue,
    never the dominant light source. Additive to this module -- does not
    change apply_hdri_world()/setup_lighting(), which every prior
    benchmark (including Day 06) still uses unmodified."""
    import bpy
    import math as _math

    try:
        apply_hdri_world(ambient_preset, strength_override=ambient_strength)
    except FileNotFoundError:
        world = bpy.data.worlds.new("k70_v3_flat_world")
        bpy.context.scene.world = world
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        bg.inputs["Color"].default_value = (*sky_color, 1.0)
        bg.inputs["Strength"].default_value = ambient_strength

    sun_data = bpy.data.lights.new("k70_v3_sun", type="SUN")
    sun_data.energy = sun_energy
    sun_data.angle = 0.06  # tighter angle than the old 0.2 -- crisper, more defined shadow edges
    sun_obj = bpy.data.objects.new("k70_v3_sun", sun_data)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = tuple(sun_rotation)

    # gentle bounce/fill so shadow sides aren't pure black, but far too
    # weak to compete with the sun for shadow definition
    fill_data = bpy.data.lights.new("k70_v3_fill", type="AREA")
    fill_data.energy = sun_energy * 3.0
    fill_data.size = 3.0
    fill_obj = bpy.data.objects.new("k70_v3_fill", fill_data)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = (-2.2, -2.2, 2.0)
    fill_obj.rotation_euler = (_math.radians(60), 0, _math.radians(-45))
    return sun_obj


def setup_block_world_v31(sun_rotation=(0.95, 0, 0.75), sun_energy: float = 4.4,
                          sky_color=(0.47, 0.62, 0.82), sun_color=(1.0, 0.94, 0.82),
                          fill_color=(0.55, 0.65, 0.85), rim: bool = True):
    """K70 VOXEL V3.1 lighting -- the block_world_v3 fix: NO HDRI is used
    as the world background at all anymore (that was a real photograph
    visible directly behind/around built geometry -- exactly the
    'photoreal background breaking the illusion' problem). World
    background is now a flat, fully procedural stylized sky color --
    guaranteed non-photographic. Pair with
    _k70_block_kit.build_distant_skyline()/build_distant_ground() so the
    horizon is filled with actual block geometry instead of empty sky.

    Directional Sun (warm-tinted) key light + a cooler-tinted Area fill
    (for a bit of warm/cool separation) + an optional soft rim light for
    subject/background separation -- still no HDRI-driven softness."""
    import bpy
    import math as _math

    world = bpy.data.worlds.new("k70_v31_sky")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (*sky_color, 1.0)
    bg.inputs["Strength"].default_value = 1.0

    sun_data = bpy.data.lights.new("k70_v31_sun", type="SUN")
    sun_data.energy = sun_energy
    sun_data.angle = 0.05
    sun_data.color = sun_color
    sun_obj = bpy.data.objects.new("k70_v31_sun", sun_data)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = tuple(sun_rotation)

    fill_data = bpy.data.lights.new("k70_v31_fill", type="AREA")
    fill_data.energy = sun_energy * 2.6
    fill_data.size = 3.2
    fill_data.color = fill_color
    fill_obj = bpy.data.objects.new("k70_v31_fill", fill_data)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = (-2.4, -2.4, 2.1)
    fill_obj.rotation_euler = (_math.radians(58), 0, _math.radians(-45))

    if rim:
        rim_data = bpy.data.lights.new("k70_v31_rim", type="AREA")
        rim_data.energy = sun_energy * 1.4
        rim_data.size = 1.6
        rim_data.color = (0.85, 0.90, 1.0)
        rim_obj = bpy.data.objects.new("k70_v31_rim", rim_data)
        bpy.context.collection.objects.link(rim_obj)
        rim_obj.location = (0.5, 2.6, 1.6)
        rim_obj.rotation_euler = (_math.radians(110), 0, _math.radians(170))

    return sun_obj


def _sun_travel_dir(forward_dir, right_dir, azimuth_deg: float, elevation_deg: float):
    """The direction sun RAYS travel (toward the scene), computed relative
    to the CAMERA's own forward/right basis rather than a fixed absolute
    Euler -- V5's lighting picked an absolute sun rotation independent of
    camera/hero placement, so it was frontal/flat as often as not.
    azimuth_deg=0 means the sun sits back along the camera's forward
    direction (i.e. behind the hero, lighting the camera face-on / risking
    a silhouette); 90 is a pure side light from camera-right; ~120-160 is
    a 3/4 back-light (sun mostly behind the subject, offset to one side)
    -- a classic flattering golden-hour setup that keeps directional
    modeling without flattening the face."""
    az = _math.radians(azimuth_deg)
    el = _math.radians(elevation_deg)
    hx = forward_dir[0] * _math.cos(az) + right_dir[0] * _math.sin(az)
    hy = forward_dir[1] * _math.cos(az) + right_dir[1] * _math.sin(az)
    horiz_scale = _math.cos(el)
    sun_dir_from_scene = Vector((hx * horiz_scale, hy * horiz_scale, _math.sin(el))).normalized()
    return -sun_dir_from_scene


def _gradient_sky_world(name, horizon_color, zenith_color, horizon_boost: float = 1.0):
    """Procedural two-tone sky (warm near horizon, cooler at zenith) driven
    by the world ray direction's Z component -- no HDRI photo, matches the
    'flat procedural sky, never a photograph' rule from setup_block_world_v31,
    but reads far more like a real golden-hour sky than one flat color."""
    world = bpy.data.worlds.new(name)
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    remap = nt.nodes.new("ShaderNodeMapRange")
    remap.inputs["From Min"].default_value = -0.15
    remap.inputs["From Max"].default_value = 0.6
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*horizon_color, 1.0)
    ramp.color_ramp.elements[1].color = (*zenith_color, 1.0)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = horizon_boost
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], remap.inputs["Value"])
    nt.links.new(remap.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return world


def setup_golden_hour_v2(forward_dir, right_dir, azimuth_deg: float = 145.0, elevation_deg: float = 19.0,
                         sun_energy: float = 6.0, sun_color=(1.0, 0.60, 0.32), sun_angle: float = 0.045,
                         fill_color=(0.42, 0.52, 0.85), fill_energy_mult: float = 1.1,
                         rim: bool = True, rim_color=(1.0, 0.75, 0.5),
                         sky_horizon=(0.92, 0.56, 0.38), sky_zenith=(0.33, 0.42, 0.62),
                         exposure: float = 0.35, view_transform: str = "Standard"):
    """K70 golden-hour V2: sun direction is derived from the CAMERA's own
    forward/right basis (a 3/4 back-light by default) instead of a fixed
    absolute rotation, a real two-tone gradient sky instead of one flat
    color, a low sun elevation + tight angle for long, defined shadows, a
    cooler fill so the sun's warmth reads by contrast, a warm rim for
    edge/hair-light separation, and scene exposure/view-transform tuned so
    the warm tones don't get muted by Blender's default AgX response.
    Still no HDRI -- this is 100% procedural, matching the V3.1 rule."""
    _gradient_sky_world("k70_golden_v2_sky", sky_horizon, sky_zenith)

    sun_data = bpy.data.lights.new("k70_gh2_sun", type="SUN")
    sun_data.energy = sun_energy
    sun_data.angle = sun_angle
    sun_data.color = sun_color
    sun_obj = bpy.data.objects.new("k70_gh2_sun", sun_data)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = _sun_travel_dir(forward_dir, right_dir, azimuth_deg, elevation_deg).to_track_quat(
        "-Z", "Y").to_euler()

    # cool fill roughly from the camera's own direction so the face stays
    # readable even though the key sun sits mostly behind the subject
    fill_data = bpy.data.lights.new("k70_gh2_fill", type="AREA")
    fill_data.energy = sun_energy * fill_energy_mult
    fill_data.size = 3.4
    fill_data.color = fill_color
    fill_obj = bpy.data.objects.new("k70_gh2_fill", fill_data)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = (forward_dir[0] * -3.0, forward_dir[1] * -3.0, 2.2)
    fill_obj.rotation_euler = _sun_travel_dir(forward_dir, right_dir, azimuth_deg=0.0,
                                              elevation_deg=35.0).to_track_quat("-Z", "Y").to_euler()

    if rim:
        rim_data = bpy.data.lights.new("k70_gh2_rim", type="AREA")
        rim_data.energy = sun_energy * 1.3
        rim_data.size = 1.4
        rim_data.color = rim_color
        rim_obj = bpy.data.objects.new("k70_gh2_rim", rim_data)
        bpy.context.collection.objects.link(rim_obj)
        rim_obj.location = (forward_dir[0] * 2.6, forward_dir[1] * 2.6, 1.7)
        rim_obj.rotation_euler = _sun_travel_dir(forward_dir, right_dir, azimuth_deg=180.0,
                                                 elevation_deg=40.0).to_track_quat("-Z", "Y").to_euler()

    scene = bpy.context.scene
    scene.view_settings.view_transform = view_transform
    scene.view_settings.exposure = exposure
    scene.view_settings.look = "Medium High Contrast"

    return sun_obj


def build_ground(mins, maxs, span: float, color=(0.08, 0.08, 0.09), roughness=0.9):
    """Same convention as scene_builder_script.py's studio ground: sized
    relative to the subject, sitting at the model's true floor height."""
    center = (mins + maxs) / 2
    bpy.ops.mesh.primitive_plane_add(size=span * 8, location=(center.x, center.y, mins.z))
    ground = bpy.context.active_object
    mat = bpy.data.materials.new("k70_ground")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    ground.data.materials.append(mat)
    return ground


def setup_lighting(preset: str, mins, maxs, *, rotation_z: float = 0.0,
                   add_ground: bool = True, strength_override: float | None = None):
    """One call: HDRI world + (optionally) a ground plane sized to the
    subject. Does NOT add a camera -- pair with camera_presets.py."""
    span = max((maxs - mins).x, (maxs - mins).y, (maxs - mins).z, 0.5)
    apply_hdri_world(preset, rotation_z=rotation_z, strength_override=strength_override)
    if add_ground:
        build_ground(mins, maxs, span)
    return span
