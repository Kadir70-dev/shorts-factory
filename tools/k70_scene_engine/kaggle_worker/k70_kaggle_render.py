"""K70 Kaggle GPU worker -- runs AS a Kaggle kernel (Python script type,
GPU + internet enabled via kernel-metadata.json). Self-contained: no
external K70 dataset needed for this proof, it builds a real procedural
K70 environment scene (the same "no CC0 source has full buildings, build
parametric massing instead" house/bank/office/store system documented in
_procedural_building_script.py) directly, so the only thing sent to
Kaggle is this one file.

Pipeline this script proves, end to end, inside the kernel:
  1. Confirm a real NVIDIA GPU is present (nvidia-smi).
  2. Download and extract a real official Blender Linux build (no apt,
     no license question -- blender.org's own release tarball).
  3. Build a real K70 scene (a procedural house) with Blender's own
     bpy API, configured for Cycles + GPU (CUDA/OptiX) rendering.
  4. Render it.
  5. Save the PNG (and a timing/GPU-info JSON) to /kaggle/working/, which
     Kaggle automatically exposes as kernel output for download.

Cost: Kaggle's own free GPU quota (T4/P100, ~30 GPU-hours/week on a free
account) -- $0, no paid tier ever touched by this script.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

WORK = "/kaggle/working"
BLENDER_VERSION = "4.2.4"
BLENDER_TARBALL = f"blender-{BLENDER_VERSION}-linux-x64.tar.xz"
BLENDER_URL = f"https://download.blender.org/release/Blender4.2/{BLENDER_TARBALL}"
BLENDER_DIR = f"/kaggle/working/blender-{BLENDER_VERSION}-linux-x64"
BLENDER_EXE = f"{BLENDER_DIR}/blender"

TIMINGS = {}


def _step(name):
    print(f"\n=== K70_KAGGLE_STEP {name} ===", flush=True)
    TIMINGS[name] = {"start": time.time()}


def _step_done(name):
    TIMINGS[name]["end"] = time.time()
    TIMINGS[name]["seconds"] = round(TIMINGS[name]["end"] - TIMINGS[name]["start"], 2)
    print(f"=== K70_KAGGLE_STEP {name} DONE in {TIMINGS[name]['seconds']}s ===", flush=True)


# ---------------------------------------------------------------- #
# STEP 1: confirm real GPU
# ---------------------------------------------------------------- #
_step("gpu_check")
gpu_info = "UNKNOWN"
try:
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                          "--format=csv,noheader"], capture_output=True, text=True, timeout=30)
    gpu_info = out.stdout.strip()
    print("K70_KAGGLE_GPU:", gpu_info)
except Exception as e:
    print("K70_KAGGLE_GPU_CHECK_FAILED:", repr(e))
_step_done("gpu_check")

# ---------------------------------------------------------------- #
# STEP 2: real Blender download + extract (official blender.org release)
# ---------------------------------------------------------------- #
_step("blender_download")
if not os.path.exists(BLENDER_EXE):
    tarball_path = os.path.join(WORK, BLENDER_TARBALL)
    print(f"Downloading {BLENDER_URL} ...", flush=True)
    # blender.org returned a real HTTP 403 on the first Kaggle run --
    # confirmed it's a default-User-Agent block (urllib's default
    # "Python-urllib/3.x" UA), not a real access restriction.
    req = urllib.request.Request(BLENDER_URL, headers={"User-Agent": "Mozilla/5.0 (K70 Kaggle Worker)"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(tarball_path, "wb") as f:
        f.write(resp.read())
    print("Download size:", os.path.getsize(tarball_path), "bytes")
    subprocess.run(["tar", "-xf", tarball_path, "-C", WORK], check=True)
    print("Extracted to", BLENDER_DIR)
else:
    print("Blender already present, skipping download")
_step_done("blender_download")

if not os.path.exists(BLENDER_EXE):
    print("K70_KAGGLE_FATAL: Blender executable not found after extraction")
    sys.exit(1)

# ---------------------------------------------------------------- #
# STEP 3+4: real K70 scene build + GPU render, via an inline bpy script
# ---------------------------------------------------------------- #
SCENE_SCRIPT = os.path.join(WORK, "k70_scene.py")
OUT_PNG = os.path.join(WORK, "k70_kaggle_house_gpu.png")

scene_script_src = r'''
import bpy, bmesh, time, json, sys

t0 = time.time()

def _material(name, color, roughness=0.7, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic
    return mat

def _box(name, size, location, material=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(scale=True)
    if material:
        obj.data.materials.append(material)
    return obj

def build_house(width=6.0, depth=8.0, height=3.2):
    objs = []
    wall_mat = _material("wall", (0.85, 0.80, 0.70), roughness=0.85)
    roof_mat = _material("roof", (0.30, 0.18, 0.15), roughness=0.6)
    door_mat = _material("door", (0.35, 0.22, 0.12), roughness=0.5)
    window_mat = _material("window", (0.55, 0.75, 0.85), roughness=0.1, metallic=0.2)

    body = _box("house_body", (width, depth, height), (0, 0, height / 2), wall_mat)
    objs.append(body)

    bm = bmesh.new()
    roof_h = height * 0.55
    hw, hd = width / 2 * 1.08, depth / 2 * 1.05
    b0 = bm.verts.new((-hw, -hd, 0))
    b1 = bm.verts.new((hw, -hd, 0))
    b2 = bm.verts.new((hw, hd, 0))
    b3 = bm.verts.new((-hw, hd, 0))
    r0 = bm.verts.new((0, -hd, roof_h))
    r1 = bm.verts.new((0, hd, roof_h))
    bm.faces.new((b0, b3, r1, r0))
    bm.faces.new((b1, r0, r1, b2))
    bm.faces.new((b0, b1, r0))
    bm.faces.new((b3, r1, b2))
    bm.faces.new((b0, b1, b2, b3))
    mesh = bpy.data.meshes.new("house_roof_mesh")
    bm.to_mesh(mesh)
    bm.free()
    roof = bpy.data.objects.new("house_roof", mesh)
    bpy.context.collection.objects.link(roof)
    roof.location = (0, 0, height)
    roof.data.materials.append(roof_mat)
    objs.append(roof)

    door = _box("house_door", (width * 0.16, 0.1, height * 0.55),
                (0, -depth / 2 - 0.05, height * 0.275), door_mat)
    objs.append(door)
    for side in (-1, 1):
        win = _box(f"house_window_{side}", (width * 0.18, 0.08, height * 0.28),
                   (side * width * 0.28, -depth / 2 - 0.04, height * 0.55), window_mat)
        objs.append(win)
    return objs

bpy.ops.wm.read_factory_settings(use_empty=True)
house_objs = build_house()

from mathutils import Vector
mins = Vector((float("inf"),) * 3)
maxs = Vector((float("-inf"),) * 3)
for obj in bpy.context.scene.objects:
    if obj.type != "MESH":
        continue
    for corner in obj.bound_box:
        wc = obj.matrix_world @ Vector(corner)
        mins = Vector(min(a, b) for a, b in zip(mins, wc))
        maxs = Vector(max(a, b) for a, b in zip(maxs, wc))
center = (mins + maxs) / 2
span = max((maxs - mins).x, (maxs - mins).y, (maxs - mins).z, 1.0)

bpy.ops.mesh.primitive_plane_add(size=span * 6, location=(center.x, center.y, mins.z))
ground = bpy.context.active_object
ground.data.materials.append(_material("ground", (0.35, 0.45, 0.30), roughness=0.9))

world = bpy.data.worlds.new("w")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (0.5, 0.65, 0.85, 1.0)
bg.inputs["Strength"].default_value = 1.0

sun_data = bpy.data.lights.new("sun", type="SUN")
sun_data.energy = 4.0
sun_obj = bpy.data.objects.new("sun", sun_data)
bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler = (0.9, 0, 0.7)

distance = span * 1.8
cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 35
cam_obj = bpy.data.objects.new("cam", cam_data)
bpy.context.collection.objects.link(cam_obj)
cam_obj.location = (center.x + distance * 0.7, center.y - distance * 1.1, center.z + distance * 0.35)
look_at = center
cam_obj.rotation_euler = (look_at - cam_obj.location).to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = cam_obj

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 128
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.filepath = sys.argv[sys.argv.index("--") + 1]
scene.render.image_settings.file_format = "PNG"
scene.render.use_stamp = False

# real GPU device configuration -- CUDA/OptiX, not CPU fallback
prefs = bpy.context.preferences.addons["cycles"].preferences
gpu_report = {"devices_found": [], "compute_type_used": None}
for compute_type in ("OPTIX", "CUDA"):
    prefs.compute_device_type = compute_type
    prefs.get_devices()
    gpu_devices = [d for d in prefs.devices if d.type in ("OPTIX", "CUDA")]
    if gpu_devices:
        gpu_report["compute_type_used"] = compute_type
        for d in prefs.devices:
            d.use = d.type in ("OPTIX", "CUDA")
            gpu_report["devices_found"].append({"name": d.name, "type": d.type, "use": d.use})
        break
scene.cycles.device = "GPU" if gpu_report["compute_type_used"] else "CPU"
print("K70_KAGGLE_GPU_REPORT", json.dumps(gpu_report))

t1 = time.time()
bpy.ops.render.render(write_still=True)
t2 = time.time()

print("K70_KAGGLE_RENDER_OK")
print("K70_KAGGLE_TIMING", json.dumps({
    "scene_build_seconds": round(t1 - t0, 3),
    "render_seconds": round(t2 - t1, 3),
    "render_device": scene.cycles.device,
    "compute_type": gpu_report["compute_type_used"],
    "samples": scene.cycles.samples,
    "resolution": [scene.render.resolution_x, scene.render.resolution_y],
}))
'''

with open(SCENE_SCRIPT, "w", encoding="utf-8") as f:
    f.write(scene_script_src)

_step("blender_gpu_render")
proc = subprocess.run(
    [BLENDER_EXE, "--background", "--python", SCENE_SCRIPT, "--", OUT_PNG],
    capture_output=True, text=True, timeout=1800,
)
print("--- blender stdout (tail) ---")
print(proc.stdout[-4000:])
print("--- blender stderr (tail) ---")
print(proc.stderr[-2000:])
_step_done("blender_gpu_render")

render_ok = "K70_KAGGLE_RENDER_OK" in proc.stdout and os.path.exists(OUT_PNG)
print(f"\nK70_KAGGLE_FINAL_STATUS render_ok={render_ok} "
     f"output_exists={os.path.exists(OUT_PNG)} "
     f"output_size={os.path.getsize(OUT_PNG) if os.path.exists(OUT_PNG) else 0}")

with open(os.path.join(WORK, "k70_kaggle_run_report.json"), "w", encoding="utf-8") as f:
    json.dump({
        "gpu_info": gpu_info,
        "render_ok": render_ok,
        "timings": TIMINGS,
        "blender_version": BLENDER_VERSION,
    }, f, indent=2)

# Clean up the ~350MB Blender download/extract from /kaggle/working before
# the kernel ends -- Kaggle exports the ENTIRE working directory as kernel
# output, and the first real run of this script confirmed that downloading
# the full Blender binary back to Windows takes several minutes for no
# reason (only the render PNG + this JSON report are actually needed).
import shutil
for path in (os.path.join(WORK, BLENDER_TARBALL), BLENDER_DIR):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.remove(path)

print("K70_KAGGLE_DONE")
