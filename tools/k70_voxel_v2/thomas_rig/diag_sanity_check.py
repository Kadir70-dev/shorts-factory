"""Sanity check: delete EVERYTHING except the ground/camera/sun, render
a blank scene. If this still produces the same character image, the
render pipeline itself is broken (not my object identification)."""
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

# nuke EVERY mesh object, no exceptions
deleted = 0
for o in list(bpy.data.objects):
    if o.type == "MESH":
        bpy.data.objects.remove(o, do_unlink=True)
        deleted += 1
print("K70_DELETED_ALL_MESH_COUNT", deleted)
bpy.context.view_layer.update()
sys.stdout.flush()

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 480
scene.render.resolution_y = 640
scene.render.image_settings.file_format = "PNG"

cam_loc = Vector((4.5, -5.5, 1.6))
look_at = Vector((0, 0, 0.9))
cam_data = bpy.data.cameras.new("k70_cam")
cam_data.lens = 35
cam_obj = bpy.data.objects.new("k70_cam", cam_data)
bpy.context.collection.objects.link(cam_obj)
cam_obj.location = cam_loc
cam_obj.rotation_euler = (look_at - cam_loc).to_track_quat("-Z", "Y").to_euler()
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
print("K70_SANITY_RENDER_OK")
