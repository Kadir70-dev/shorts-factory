"""Replicates Blender's own viewport click-to-select via ray_cast,
using the exact camera setup from my render tests -- casts a ray from
the camera through the floating head's known screen position (visible
in frame_000.png at roughly the top-center, above the connected body)
to identify EXACTLY which object occupies that space. This is the
scriptable equivalent of clicking on it in the interactive GUI.
"""
import sys
import bpy
from mathutils import Vector

rig_blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=rig_blend)
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.thomas_rig_legacy")

rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.thomasriglegacy.appendbasemesh()

# same camera as my render tests: location (4.5, -5.5, 1.6), looking at (0,0,0.9), lens 35mm
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
depsgraph = bpy.context.evaluated_depsgraph_get()

def screen_to_ray(px, py, width, height):
    # Blender camera view matrix math: build a ray from camera through
    # normalized device coords matching pixel (px,py) in a width x height image.
    import bpy_extras
    from mathutils import Matrix
    # normalized coords: 0..1, origin bottom-left (Blender convention)
    x = px / width
    y = 1.0 - (py / height)
    region_data = None
    # Use camera's view_frame to compute a ray manually (no 3D viewport needed)
    frame = cam_data.view_frame(scene=scene)
    # frame is 4 corners in camera local space: order is
    # top-right, bottom-right, bottom-left, top-left (Blender convention)
    tr, br, bl, tl = [cam_obj.matrix_world @ v for v in frame]
    top = tl.lerp(tr, x)
    bottom = bl.lerp(br, x)
    point = bottom.lerp(top, y)
    direction = (point - cam_loc).normalized()
    return cam_loc, direction

# Try several pixel locations across the floating head's visible area
# (roughly x=200-280, y=90-180 in the 480x640 render based on the
# contact-sheet crops I've reviewed)
test_points = [(240, 110), (240, 130), (220, 120), (260, 120), (240, 150)]
for px, py in test_points:
    origin, direction = screen_to_ray(px, py, 480, 640)
    success, location, normal, index, obj, matrix = scene.ray_cast(depsgraph, origin, direction)
    print(f"K70_RAYCAST px=({px},{py}) hit={success} obj={obj.name if obj else None} "
          f"loc={tuple(location) if success else None}")
    sys.stdout.flush()
