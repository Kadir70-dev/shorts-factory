import sys
import bpy

rig_blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=rig_blend)
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.thomas_rig_legacy")

rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.thomasriglegacy.appendbasemesh()

deform_bone_names = {b.name for b in rig.data.bones if b.use_deform}
print("K70_DEFORM_BONE_COUNT", len(deform_bone_names))
print("K70_DEFORM_BONE_NAMES", sorted(deform_bone_names))
sys.stdout.flush()

for o in bpy.data.objects:
    if o.type != "MESH" or o.hide_render:
        continue
    has_armature_mod = any(m.type == "ARMATURE" for m in o.modifiers)
    if not has_armature_mod:
        continue
    vg_names = {vg.name for vg in o.vertex_groups}
    deform_vgs = vg_names & deform_bone_names
    print(f"K70_BIND {o.name} vertex_groups={sorted(vg_names)} "
          f"deform_bound={sorted(deform_vgs)} is_deform_bound={len(deform_vgs) > 0}")
sys.stdout.flush()
