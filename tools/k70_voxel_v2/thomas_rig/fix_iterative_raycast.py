"""Robust fix: iteratively ray-cast through the known floating-head
pixel and DELETE whatever object is hit, repeating until the ray finds
nothing there. This peels away every overlapping duplicate at that
exact spot, not just the first one -- confirmed necessary since a
sanity check proved the render pipeline correctly reflects deletions,
meaning earlier single-object deletes left other overlapping
duplicates still occupying the same visual space.
"""
import sys
import bpy
from mathutils import Vector

rig_blend = sys.argv[sys.argv.index("--") + 1]
out_dir = sys.argv[sys.argv.index("--") + 2]

bpy.ops.wm.open_mainfile(filepath=rig_blend)
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.thomas_rig_legacy")

rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.thomasriglegacy.appendbasemesh()

cam_loc = Vector((4.5, -5.5, 1.6))
look_at = Vector((0, 0, 0.9))
cam_data = bpy.data.cameras.new("k70_cam")
cam_data.lens = 35
cam_obj = bpy.data.objects.new("k70_cam", cam_data)
bpy.context.collection.objects.link(cam_obj)
cam_obj.location = cam_loc
cam_obj.rotation_euler = (look_at - cam_loc).to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = cam_obj
bpy.context.view_layer.update()

scene = bpy.context.scene
scene.render.resolution_x = 480
scene.render.resolution_y = 640

def screen_to_ray(px, py, width, height):
    x = px / width
    y = 1.0 - (py / height)
    frame = cam_data.view_frame(scene=scene)
    tr, br, bl, tl = [cam_obj.matrix_world @ v for v in frame]
    top = tl.lerp(tr, x)
    bottom = bl.lerp(br, x)
    point = bottom.lerp(top, y)
    direction = (point - cam_loc).normalized()
    return cam_loc, direction

# Iteratively peel away every object at the known floating-head pixel
# cluster (multiple sample points to catch objects offset slightly
# within that visual cluster, not just one exact pixel).
sample_points = [(240, 110), (240, 130), (220, 120), (260, 120), (240, 150), (240, 95), (240, 170)]
deleted_names = []
for px, py in sample_points:
    for _ in range(10):  # safety cap per point
        depsgraph = bpy.context.evaluated_depsgraph_get()
        origin, direction = screen_to_ray(px, py, 480, 640)
        success, location, normal, index, obj, matrix = scene.ray_cast(depsgraph, origin, direction)
        if not success or obj is None:
            break
        real_obj = obj.original if hasattr(obj, "original") else obj
        name = real_obj.name
        if name in deleted_names:
            # already deleted this one via another sample point but
            # depsgraph is stale -- force a fresh update and retry once
            bpy.context.view_layer.update()
            depsgraph = bpy.context.evaluated_depsgraph_get()
            success, location, normal, index, obj, matrix = scene.ray_cast(depsgraph, origin, direction)
            if not success or obj is None or obj.original.name in deleted_names:
                break
            real_obj = obj.original
            name = real_obj.name
        print(f"K70_ITER_DELETE px=({px},{py}) obj={name}")
        sys.stdout.flush()
        bpy.data.objects.remove(real_obj, do_unlink=True)
        deleted_names.append(name)
        bpy.context.view_layer.update()

print("K70_TOTAL_DELETED", len(deleted_names), deleted_names)
sys.stdout.flush()

scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.image_settings.file_format = "PNG"

sun = bpy.data.lights.new("k70_sun", type="SUN")
sun.energy = 3.0
sun_obj = bpy.data.objects.new("k70_sun", sun)
bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler = (0.9, 0, 0.6)

if hasattr(scene, "eevee"):
    try:
        scene.eevee.taa_render_samples = 16
    except AttributeError:
        pass

scene.render.filepath = f"{out_dir}/frame_000.png"
bpy.ops.render.render(write_still=True)
print("K70_ITERATIVE_FIX_RENDER_OK")
