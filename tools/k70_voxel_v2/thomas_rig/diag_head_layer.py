import sys
import bpy

rig_blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=rig_blend)
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.thomas_rig_legacy")

rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.thomasriglegacy.appendbasemesh()

obj = bpy.data.objects.get("Head_Layer")
print("K70_OBJ_FOUND", obj is not None)
print("K70_PARENT", obj.parent.name if obj.parent else None)
print("K70_LOCATION", tuple(obj.location))
print("K70_MATRIX_WORLD_TRANSLATION", tuple(obj.matrix_world.translation))
print("K70_MODIFIERS", [(m.name, m.type, getattr(m, "object", None).name if getattr(m, "object", None) else None) for m in obj.modifiers])
print("K70_VERTEX_GROUPS", [vg.name for vg in obj.vertex_groups])

# compare to Body (the base mesh, presumably correctly positioned)
body = bpy.data.objects.get("Body")
if body:
    print("K70_BODY_LOCATION", tuple(body.location))
    print("K70_BODY_MODIFIERS", [(m.name, m.type, getattr(m, "object", None).name if getattr(m, "object", None) else None) for m in body.modifiers])

# also compare to Head_NoDeform, which should be positioned correctly at rest
head_ref = bpy.data.objects.get("Head_NoDeform")
if head_ref:
    print("K70_HEAD_NODEFORM_LOCATION", tuple(head_ref.location))
    print("K70_HEAD_NODEFORM_WORLD", tuple(head_ref.matrix_world.translation))
