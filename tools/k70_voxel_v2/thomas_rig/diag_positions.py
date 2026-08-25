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

rows = []
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    eo = o.evaluated_get(depsgraph)
    try:
        verts = eo.data.vertices
        if not verts:
            continue
        zs = [ (eo.matrix_world @ v.co).z for v in verts ]
        xs = [ (eo.matrix_world @ v.co).x for v in verts ]
        zmin, zmax = min(zs), max(zs)
        xmin, xmax = min(xs), max(xs)
        rows.append((o.name, o.hide_render, round(zmin,3), round(zmax,3), round(xmin,3), round(xmax,3)))
    except Exception as e:
        rows.append((o.name, o.hide_render, "ERR", str(e), None, None))

rows.sort(key=lambda r: -(r[3] if isinstance(r[3], float) else -999))
print("K70_POSITIONS_START")
for r in rows:
    print("K70_POS", r)
print("K70_POSITIONS_END")
