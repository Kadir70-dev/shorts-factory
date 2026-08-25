from __future__ import annotations
import json,sys
from pathlib import Path
import bpy
from mathutils import Vector
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from rest_retarget_blender import retarget_bvh
from contact_layer import ProceduralContactLayer
def cube(name,loc,scale,color,role=None):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.scale=scale;m=bpy.data.materials.new(name+"Mat");m.diffuse_color=(*color,1);o.data.materials.append(m)
 if role:o["k70_contact_role"]=role
 return o
def main():
 i=sys.argv.index("--");s=json.loads(Path(sys.argv[i+1]).read_text());bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False);before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=s["target"]);objs=[o for o in bpy.data.objects if o not in before];arm=next(o for o in objs if o.type=="ARMATURE");arm.animation_data_clear();retarget_bvh(Path(s["bvh"]),arm,action_name="K70_CHAIR_TEST")
 anchor=bpy.data.objects.new("CharacterAnchor",None);bpy.context.collection.objects.link(anchor);imported=set(objs)
 for o in objs:
  if o.parent not in imported:o.parent=anchor
 bpy.ops.mesh.primitive_plane_add(size=12);ground=bpy.context.object;ground["k70_contact_role"]="ground";gm=bpy.data.materials.new("Ground");gm.diffuse_color=(.08,.1,.13,1);ground.data.materials.append(gm);layer=ProceduralContactLayer(arm,anchor);ground_result=layer.visible_ground(1,12,ground)
 bpy.context.scene.frame_set(24);bpy.context.view_layer.update();contact=layer.visible_seat_contact();h=layer.character_height();seat_top=h*.28;seat=cube("ChairSeat",(contact.x,contact.y,seat_top-h*.035),(h*.26,h*.24,h*.035),(.32,.16,.06),"chair");cube("ChairBack",(contact.x,contact.y+h*.22,seat_top+h*.25),(h*.26,h*.035,h*.28),(.32,.16,.06));chair_result=layer.visible_chair(17,34,seat);post=layer.visible_ground(40,48,ground)
 pts=[o.matrix_world@Vector(c) for o in objs if o.type=="MESH" for c in o.bound_box];lo=Vector((min(p.x for p in pts),min(p.y for p in pts),0));hi=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)));center=(lo+hi)*.5;span=max(hi.z-lo.z,(hi-lo).length);bpy.ops.object.camera_add(location=(center.x+span*.7,center.y-span*2.2,center.z));cam=bpy.context.object;cam.rotation_euler=(center-cam.location).to_track_quat("-Z","Y").to_euler();bpy.context.scene.camera=cam;bpy.ops.object.light_add(type="AREA",location=(span,-span,span*2));bpy.context.object.data.energy=900;bpy.context.object.data.size=span
 sc=bpy.context.scene;sc.frame_start=1;sc.frame_end=48;sc.render.fps=12;sc.render.engine="BLENDER_EEVEE_NEXT";sc.render.resolution_x=480;sc.render.resolution_y=480;sc.render.resolution_percentage=100;sc.render.image_settings.file_format="PNG";sc.render.filepath=s["frames"]+"/frame_";Path(s["frames"]).mkdir(parents=True,exist_ok=True);bpy.ops.wm.save_as_mainfile(filepath=s["blend"]);bpy.ops.render.render(animation=True);Path(s["result"]).write_text(json.dumps({"ground":ground_result,"chair":chair_result,"post_ground":post},indent=2));print("K70_CHAIR_OK")
main()
