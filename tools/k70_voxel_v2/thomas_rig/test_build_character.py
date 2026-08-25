"""Real headless test: open the bundled rig .blend, enable the addon,
call the base-mesh-append operator, render ONE preview frame. This is
the test that actually answers "can we automate character creation
with this rig", not just "does the addon register"."""
import sys
import bpy

rig_blend = sys.argv[sys.argv.index("--") + 1]
out_png = sys.argv[sys.argv.index("--") + 2]

bpy.ops.wm.open_mainfile(filepath=rig_blend)
print("K70_OPEN_OK", [o.name for o in bpy.data.objects])
sys.stdout.flush()

bpy.ops.preferences.addon_enable(module="bl_ext.user_default.thomas_rig_legacy")
print("K70_ADDON_ENABLED_IN_RIG_FILE_OK")
sys.stdout.flush()

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

print("K70_MESH_OBJECTS_AFTER", [o.name for o in bpy.data.objects if o.type == "MESH"])
sys.stdout.flush()

# quick preview render
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 480
scene.render.resolution_y = 640
scene.render.filepath = out_png
scene.render.image_settings.file_format = "PNG"
if scene.camera is None:
    cam_data = bpy.data.cameras.new("k70_cam")
    cam_obj = bpy.data.objects.new("k70_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = (0, -2.5, 1.0)
    from mathutils import Vector
    cam_obj.rotation_euler = (Vector((0, 0, 0.9)) - Vector(cam_obj.location)).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam_obj
if hasattr(scene, "eevee"):
    try:
        scene.eevee.taa_render_samples = 16
    except AttributeError:
        pass
bpy.ops.render.render(write_still=True)
print("K70_THOMAS_RIG_BUILD_AND_RENDER_OK")
