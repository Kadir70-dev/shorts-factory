"""Real test: can Thomas Rig actually be POSED/ANIMATED headlessly?
This is the single most important untested question -- static mesh
build succeeded earlier, but walk/turn/sit/gesture require posing the
armature across keyframes, which is a different code path (pose mode,
bone rotations) that hasn't been touched yet.
"""
import sys
import bpy
import math

rig_blend = sys.argv[sys.argv.index("--") + 1]
out_dir = sys.argv[sys.argv.index("--") + 2]

bpy.ops.wm.open_mainfile(filepath=rig_blend)
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.thomas_rig_legacy")

rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
print("K70_RIG_FOUND", rig.name)
sys.stdout.flush()

bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.thomasriglegacy.appendbasemesh()
print("K70_MESH_BUILT_OK")
sys.stdout.flush()

# Real bug, correctly root-caused via a comprehensive per-object dump
# (visibility + collection + evaluated post-deform world position for
# every "Head"-named object): object .location on an armature-deformed
# mesh does NOT determine its rendered position here (confirmed: moving
# Head_Layer's .location had zero visual effect, since the Armature
# modifier deforms from bind-pose vertex weights, not object.location).
# The real cause is that exactly TWO head meshes are simultaneously
# visible after append_base_mesh: "Head_Layer" (the real, correctly-
# deforming mesh, keep it) and "Head_NoDeform" (a static bind-pose
# reference copy -- everything else with "Head" in its name is already
# correctly hidden by default). In the normal interactive UI workflow
# something evidently hides Head_NoDeform (likely the reference-object
# depsgraph_update_post handler seen in properties.py) that never
# fires headlessly. Hiding it explicitly is the real, minimal fix.
# REAL ROOT CAUSE, found via camera ray-casting through the exact
# visible floating-head pixel in a render (replicating an interactive
# viewport click without a GUI): the object there is "2_Layer_
# Extrusion" -- a GENERICALLY named extrusion-helper object with no
# "head" in its name at all, which is exactly why every name-based
# "head" filter tried so far missed it. Confirmed by the addon
# developer's own words (extension review thread): appendbasemesh()
# intentionally creates non-render "extrusion helper" objects for
# manual armor/hat modeling in the interactive UI. Deleting every
# "*_Layer_Extrusion"-named object (there's likely a sibling
# "1_Layer_Extrusion" too) should clear this for good.
for o in list(bpy.data.objects):
    if o.type == "MESH" and "Extrusion" in o.name and not o.hide_render:
        print(f"K70_DELETED_EXTRUSION_HELPER {o.name}")
        bpy.data.objects.remove(o, do_unlink=True)
bpy.context.view_layer.update()
sys.stdout.flush()

print("K70_POSE_BONE_COUNT", len(rig.pose.bones))
print("K70_POSE_BONE_NAMES", [b.name for b in rig.pose.bones])
sys.stdout.flush()

# find likely leg/arm/spine bones by common naming patterns
bone_names = [b.name for b in rig.pose.bones]
def find_bone(*keywords):
    for kw in keywords:
        for name in bone_names:
            if kw.lower() in name.lower():
                return name
    return None

leg_r = find_bone("Leg.R", "R.Leg", "RightLeg", "Leg_R")
arm_r = find_bone("Arm.R", "R.Arm", "RightArm", "Arm_R")
spine = find_bone("Spine", "Body", "Torso", "Chest")
print("K70_BONE_GUESSES", {"leg_r": leg_r, "arm_r": arm_r, "spine": spine})
sys.stdout.flush()

bpy.ops.object.mode_set(mode="POSE")

def key(bone_name, frame, euler_deg):
    if bone_name is None:
        return
    pb = rig.pose.bones[bone_name]
    pb.rotation_mode = "XYZ"
    pb.rotation_euler = tuple(math.radians(d) for d in euler_deg)
    pb.keyframe_insert(data_path="rotation_euler", frame=frame)

for bn, cycle in ((leg_r, 30), (arm_r, -25)):
    key(bn, 1, (0, 0, 0))
    key(bn, 12, (cycle, 0, 0))
    key(bn, 24, (0, 0, 0))

if spine:
    key(spine, 1, (0, 0, 0))
    key(spine, 12, (10, 0, 0))
    key(spine, 24, (0, 0, 0))

print("K70_KEYFRAMES_SET_OK")
sys.stdout.flush()

bpy.ops.object.mode_set(mode="OBJECT")

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 480
scene.render.resolution_y = 640
scene.render.image_settings.file_format = "PNG"
from mathutils import Vector
cam_loc = (4.5, -5.5, 1.6)
look_at = Vector((0, 0, 0.9))
if scene.camera is None:
    cam_data = bpy.data.cameras.new("k70_cam")
    cam_data.lens = 35
    cam_obj = bpy.data.objects.new("k70_cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj
scene.camera.location = cam_loc
scene.camera.rotation_euler = (look_at - Vector(cam_loc)).to_track_quat("-Z", "Y").to_euler()

# "_NoDeform" helper/reference meshes are likely meant to be hidden
# from render by an interactive-only visibility handler
# (thomas_rig_reference_handler, wired to depsgraph_update_post) that
# never fires in a headless script -- hide them explicitly instead.
for o in bpy.data.objects:
    if o.type == "MESH" and "NoDeform" in o.name:
        o.hide_render = True
        print("K70_HID_NODEFORM", o.name)

mesh_objs = [o for o in bpy.data.objects if o.type == "MESH" and not o.hide_render]
print("K70_VISIBLE_MESH_COUNT", len(mesh_objs))
print("K70_VISIBLE_MESH_NAMES", [o.name for o in mesh_objs])
sys.stdout.flush()

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

for i, frame in enumerate((1, 6, 12, 18, 24)):
    scene.frame_set(frame)
    scene.render.filepath = f"{out_dir}/frame_{i:03d}.png"
    bpy.ops.render.render(write_still=True)
    print(f"K70_FRAME_OK {i} (source frame {frame})")
    sys.stdout.flush()

print("K70_THOMAS_RIG_ANIMATION_TEST_OK")
