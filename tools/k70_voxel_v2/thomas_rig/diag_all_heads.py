import sys
import bpy

rig_blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=rig_blend)
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.thomas_rig_legacy")

rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.thomasriglegacy.appendbasemesh()

bpy.context.view_layer.update()
depsgraph = bpy.context.evaluated_depsgraph_get()

for o in bpy.data.objects:
    if o.type != "MESH" or "head" not in o.name.lower():
        continue
    colls = [c.name for c in o.users_collection]
    eo = o.evaluated_get(depsgraph)
    zs = [(eo.matrix_world @ v.co).z for v in eo.data.vertices] if len(eo.data.vertices) else [None]
    print(f"K70_HEAD_OBJ {o.name} coll={colls} hide_render={o.hide_render} "
          f"visible_get={o.visible_get()} eval_z=({min(zs) if zs[0] is not None else None},"
          f"{max(zs) if zs[0] is not None else None}) local_loc={tuple(o.location)}")
