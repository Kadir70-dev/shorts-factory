from __future__ import annotations
import json,sys
from pathlib import Path
import bpy
from mathutils import Vector
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from rest_retarget_blender import retarget_bvh
from contact_layer import ProceduralContactLayer
def main():
 i=sys.argv.index("--");s=json.loads(Path(sys.argv[i+1]).read_text());bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=s["target"]);objs=[o for o in bpy.data.objects if o not in before];arm=next(o for o in objs if o.type=="ARMATURE");arm.animation_data_clear();retarget_bvh(Path(s["bvh"]),arm,action_name="K70_VISIBLE_SOLE_WALK",end_fraction=.55)
 anchor=bpy.data.objects.new("CharacterAnchor",None);bpy.context.collection.objects.link(anchor);imported=set(objs)
 for o in objs:
  if o.parent not in imported:o.parent=anchor
 bpy.ops.mesh.primitive_plane_add(size=12);ground=bpy.context.object;ground.name="Ground";ground["k70_contact_role"]="ground";m=bpy.data.materials.new("GroundMat");m.diffuse_color=(.08,.1,.13,1);ground.data.materials.append(m)
 result=ProceduralContactLayer(arm,anchor).visible_ground(1,48,ground)
 # Bounds-derived full-body camera.
 bpy.context.scene.frame_set(24);bpy.context.view_layer.update();pts=[o.matrix_world@Vector(c) for o in objs if o.type=="MESH" for c in o.bound_box];lo=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)));hi=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)));h=hi.z-lo.z;center=(lo+hi)*.5
 bpy.ops.object.camera_add(location=(center.x+h*.8,center.y-h*2.5,center.z));cam=bpy.context.object;cam.rotation_euler=(center-cam.location).to_track_quat("-Z","Y").to_euler();cam.data.lens=55;bpy.context.scene.camera=cam;bpy.ops.object.light_add(type="AREA",location=(center.x+h,center.y-h,hi.z+h));bpy.context.object.data.energy=900;bpy.context.object.data.size=h*2
 sc=bpy.context.scene;sc.frame_start=1;sc.frame_end=48;sc.render.fps=12;sc.render.engine="BLENDER_EEVEE_NEXT";sc.render.resolution_x=480;sc.render.resolution_y=480;sc.render.resolution_percentage=100;sc.render.image_settings.file_format="PNG";sc.render.filepath=s["frames"]+"/frame_";Path(s["frames"]).mkdir(parents=True,exist_ok=True);bpy.ops.wm.save_as_mainfile(filepath=s["blend"]);bpy.ops.render.render(animation=True);Path(s["result"]).write_text(json.dumps(result,indent=2));print("K70_SOLE_OK")
main()
