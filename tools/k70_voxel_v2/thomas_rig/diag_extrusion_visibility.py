import sys
import bpy

rig_blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=rig_blend)
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.thomas_rig_legacy")

rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.thomasriglegacy.appendbasemesh()

for name in ("1_Layer_Extrusion", "2_Layer_Extrusion"):
    o = bpy.data.objects.get(name)
    if o is None:
        print(f"K70_MISSING {name}")
        continue
    print(f"K70_EXTRUSION_VIS {name} hide_render={o.hide_render} "
          f"hide_viewport={o.hide_viewport} visible_get={o.visible_get()} "
          f"collections={[c.name for c in o.users_collection]} "
          f"material_count={len(o.data.materials)}")
    for slot_i, mat in enumerate(o.data.materials):
        print(f"  K70_MAT_SLOT {slot_i} {mat.name if mat else None}")
