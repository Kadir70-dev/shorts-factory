import sys
import bpy

rig_blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=rig_blend)
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.thomas_rig_legacy")

rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.thomasriglegacy.appendbasemesh()

# real render-visibility check: does Blender itself think this object
# will show up in a render, considering collection exclusion, object
# hide_render, and view layer collection state -- not just the raw
# object.hide_render flag.
targets = ["Head_Layer", "Head_NoDeform", "Body", "Legs", "Arms", "wrist", "ik", "LEGS.001", "Bodymain", "Chest_Layer"]
for name in targets:
    o = bpy.data.objects.get(name)
    if o is None:
        print(f"K70_MISSING {name}")
        continue
    colls = [c.name for c in o.users_collection]
    print(f"K70_OBJ {name} collections={colls} hide_render={o.hide_render} "
          f"hide_viewport={o.hide_viewport} visible_get={o.visible_get()}")

for c in bpy.data.collections:
    print(f"K70_COLLECTION {c.name} hide_render={c.hide_render}")
