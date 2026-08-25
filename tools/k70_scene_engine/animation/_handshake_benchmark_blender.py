from __future__ import annotations
import json,math,sys
from pathlib import Path
import bpy
from mathutils import Vector
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from rest_retarget_blender import retarget_bvh
from contact_layer import ProceduralContactLayer
def actor(target,bvh,name):
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=target);objs=[o for o in bpy.data.objects if o not in before];arm=next(o for o in objs if o.type=="ARMATURE");arm.name=name;arm.animation_data_clear();retarget_bvh(Path(bvh),arm,action_name=name+"Handshake");anchor=bpy.data.objects.new(name+"Anchor",None);bpy.context.collection.objects.link(anchor);imp=set(objs)
 for o in objs:
  if o.parent not in imp:o.parent=anchor
 return arm,anchor,objs
def main():
 i=sys.argv.index("--");s=json.loads(Path(sys.argv[i+1]).read_text());bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False);a,aa,ao=actor(s["target"],s["bvh"],"ActorA");b,ba,bo=actor(s["target"],s["bvh"],"ActorB")
 armreach=a.data.bones["upperarm_r"].length+a.data.bones["lowerarm_r"].length;shoulders=(a.data.bones["clavicle_l"].head_local-a.data.bones["clavicle_r"].head_local).length;separation=max(shoulders*1.35,armreach*1.65);aa.location.x=-separation*.5;ba.location.x=separation*.5;aa.rotation_euler.z=-math.pi/2;ba.rotation_euler.z=math.pi/2
 bpy.ops.mesh.primitive_plane_add(size=separation*8);ground=bpy.context.object;ground["k70_contact_role"]="ground";gm=bpy.data.materials.new("Ground");gm.diffuse_color=(.08,.1,.13,1);ground.data.materials.append(gm);la=ProceduralContactLayer(a,aa);lb=ProceduralContactLayer(b,ba);ga=la.visible_ground(1,48,ground);gb=lb.visible_ground(1,48,ground)
 bpy.context.scene.frame_set(24);bpy.context.view_layer.update();sa=a.matrix_world@a.pose.bones["upperarm_r"].head;sb=b.matrix_world@b.pose.bones["upperarm_r"].head;shared=(sa+sb)*.5;bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,radius=armreach*.025,location=shared);marker=bpy.context.object;marker.name="HandshakeShared";marker["k70_contact_role"]="handshake";marker.hide_render=True;ha=la.hand("right","handshake",14,36,marker);hb=lb.hand("right","handshake",14,36,marker)
 # Camera from combined evaluated character bounds.
 pts=[o.matrix_world@Vector(c) for o in ao+bo if o.type=="MESH" for c in o.bound_box];lo=Vector((min(p.x for p in pts),min(p.y for p in pts),0));hi=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)));center=(lo+hi)*.5;span=max(hi.z,(hi-lo).length);bpy.ops.object.camera_add(location=(center.x+span*.7,center.y-span*2.4,center.z));cam=bpy.context.object;cam.rotation_euler=(center-cam.location).to_track_quat("-Z","Y").to_euler();bpy.context.scene.camera=cam;bpy.ops.object.light_add(type="AREA",location=(span,-span,span*2));bpy.context.object.data.energy=1000;bpy.context.object.data.size=span
 sc=bpy.context.scene;sc.frame_start=1;sc.frame_end=48;sc.render.fps=12;sc.render.engine="BLENDER_EEVEE_NEXT";sc.render.resolution_x=480;sc.render.resolution_y=480;sc.render.resolution_percentage=100;sc.render.image_settings.file_format="PNG";sc.render.filepath=s["frames"]+"/frame_";Path(s["frames"]).mkdir(parents=True,exist_ok=True);bpy.ops.wm.save_as_mainfile(filepath=s["blend"]);bpy.ops.render.render(animation=True);Path(s["result"]).write_text(json.dumps({"ground_a":ga,"ground_b":gb,"hand_a":ha.__dict__,"hand_b":hb.__dict__,"separation":separation,"arm_reach":armreach,"shoulder_width":shoulders},indent=2));print("K70_HANDSHAKE_OK")
main()
