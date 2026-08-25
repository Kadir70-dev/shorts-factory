"""Real fix attempt based on a collection literally named
'Rig [only append this]' -- the addon's own author signaled the
intended workflow is APPEND that specific collection into a fresh
scene, not OPEN the whole rig template file (which loads everything
else in it too -- very likely explaining the stray duplicate head).
"""
import sys
import bpy
import os
import math

rig_blend = sys.argv[sys.argv.index("--") + 1]
out_dir = sys.argv[sys.argv.index("--") + 2]

bpy.ops.wm.read_factory_settings(use_empty=True)

collection_name = "Rig [only append this]"
bpy.ops.wm.append(
    filepath=os.path.join(rig_blend, "Collection", collection_name),
    directory=os.path.join(rig_blend, "Collection"),
    filename=collection_name,
    link=False,
)
print("K70_APPENDED_OBJECTS", [o.name for o in bpy.data.objects])
sys.stdout.flush()

bpy.ops.preferences.addon_enable(module="bl_ext.user_default.thomas_rig_legacy")

rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
if rig is None:
    print("K70_NO_ARMATURE_FOUND")
    sys.exit(1)
print("K70_RIG_FOUND", rig.name)
sys.stdout.flush()

bpy.context.view_layer.objects.active = rig
rig.select_set(True)

try:
    result = bpy.ops.thomasriglegacy.appendbasemesh()
    print("K70_APPEND_BASE_MESH_RESULT", result)
except Exception as e:
    print(f"K70_APPEND_BASE_MESH_FAIL {type(e).__name__}: {e}")
    sys.exit(1)
sys.stdout.flush()

mesh_objs = [o for o in bpy.data.objects if o.type == "MESH" and not o.hide_render]
print("K70_VISIBLE_MESH_COUNT", len(mesh_objs))
sys.stdout.flush()

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 480
scene.render.resolution_y = 640
scene.render.image_settings.file_format = "PNG"

from mathutils import Vector
cam_loc = (4.5, -5.5, 1.6)
look_at = Vector((0, 0, 0.9))
cam_data = bpy.data.cameras.new("k70_cam")
cam_data.lens = 35
cam_obj = bpy.data.objects.new("k70_cam", cam_data)
bpy.context.collection.objects.link(cam_obj)
cam_obj.location = cam_loc
cam_obj.rotation_euler = (look_at - Vector(cam_loc)).to_track_quat("-Z", "Y").to_euler()
scene.camera = cam_obj

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
print("K70_CORRECT_APPEND_RENDER_OK")
