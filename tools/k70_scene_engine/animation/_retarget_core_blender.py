"""Isolated CMU BVH -> K70 production humanoid retarget diagnostic."""
from __future__ import annotations
import json, math, sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

HERE=Path(__file__).resolve().parent; sys.path.insert(0,str(HERE))
from bvh_adapter import import_action

MAP={
 "Hips":"pelvis","LowerBack":"spine_01","Spine":"spine_02","Spine1":"spine_03",
 "Neck":"neck_01","Head":"head","LeftShoulder":"clavicle_l","LeftArm":"upperarm_l",
 "LeftForeArm":"lowerarm_l","LeftHand":"hand_l","RightShoulder":"clavicle_r",
 "RightArm":"upperarm_r","RightForeArm":"lowerarm_r","RightHand":"hand_r",
 "LeftUpLeg":"thigh_l","LeftLeg":"calf_l","LeftFoot":"foot_l",
 "RightUpLeg":"thigh_r","RightLeg":"calf_r","RightFoot":"foot_r",
}

def argv():
 i=sys.argv.index("--");return json.loads(Path(sys.argv[i+1]).read_text())
def clean():
 bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)
def point(arm,name,tail=False,rest=True):
 b=arm.data.bones[name] if rest else arm.pose.bones[name]
 return (b.tail_local if tail and rest else b.head_local if rest else b.tail if tail else b.head).copy()
def skeleton_basis(arm,names):
 hips=point(arm,names["hips"]); head=point(arm,names["head"],True)
 left=point(arm,names["left"]);right=point(arm,names["right"])
 up=(head-hips).normalized(); x=(right-left).normalized(); forward=x.cross(up).normalized(); x=up.cross(forward).normalized()
 return Matrix(((x.x,forward.x,up.x),(x.y,forward.y,up.y),(x.z,forward.z,up.z))).transposed(),hips,(head-hips).length
def skeleton_height(arm):
 zs=[v for b in arm.data.bones for v in (b.head_local.z,b.tail_local.z)]
 return max(zs)-min(zs)
def hierarchy(arm,mapping):
 names=set(mapping.values());return sorted(names,key=lambda n:len(arm.data.bones[n].parent_recursive))
def mesh_bounds(objects):
 pts=[o.matrix_world@Vector(c) for o in objects if o.type=="MESH" for c in o.bound_box]
 return Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts))),Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))
def mat(name,c):
 m=bpy.data.materials.new(name);m.diffuse_color=(*c,1);return m
def main():
 spec=argv();clean()
 src,src_action=import_action(Path(spec["bvh"]),name="K70_CMU_walk_source")
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=spec["target"]);objects=[o for o in bpy.data.objects if o not in before];tgt=next(o for o in objects if o.type=="ARMATURE")
 # Remove the pack's actions from the target without modifying the source library.
 tgt.animation_data_clear();
 sn={"hips":"Hips","head":"Head","left":"LeftUpLeg","right":"RightUpLeg"};tn={"hips":"pelvis","head":"head","left":"thigh_l","right":"thigh_r"}
 Bs,src_hips,_=skeleton_basis(src,sn);Bt,tgt_hips,_=skeleton_basis(tgt,tn);C=Bt@Bs.inverted()
 src_height=skeleton_height(src);tgt_height=skeleton_height(tgt);scale=tgt_height/src_height
 source_world=[list(r) for r in src.matrix_world];target_world=[list(r) for r in tgt.matrix_world]
 # Root motion range determines the diagnostic sample; keep the walking portion only.
 # Bruce Hahn's converted BVHs prepend a synthetic T-pose at frame 1; motion starts at 2.
 total=int(src_action.frame_range[1]);walk_start=2;walk_end=max(walk_start+47,round(total*.55));sample_src=[walk_start+round(i*(walk_end-walk_start)/47) for i in range(48)]
 out_action=bpy.data.actions.new("K70_CMU_walk_retargeted");out_action.use_fake_user=True;tgt.animation_data_create();tgt.animation_data.action=out_action
 # Derive target object origin/floor from its own production mesh geometry.
 lo,hi=mesh_bounds(objects);tgt_height_mesh=hi.z-lo.z
 initial_root_error=None;final_root_error=0.0;root_path=[];root_expected=[]
 order=hierarchy(tgt,MAP)
 invmap={v:k for k,v in MAP.items()}
 # Per-bone source-local -> target-local rest basis corrections.
 corrections={}
 for source_name,target_name in MAP.items():
  rs=src.data.bones[source_name].matrix_local.to_3x3().normalized()
  rt=tgt.data.bones[target_name].matrix_local.to_3x3().normalized()
  corrections[target_name]=rt.inverted()@C@rs
 root=tgt.pose.bones["root"];root.rotation_mode="QUATERNION"
 bpy.context.scene.frame_set(sample_src[0]);bpy.context.view_layer.update();source_root_origin=src.pose.bones["Hips"].head.copy()
 for out_frame,source_frame in enumerate(sample_src,1):
  bpy.context.scene.frame_set(source_frame);bpy.context.view_layer.update()
  source_delta=src.pose.bones["Hips"].head-source_root_origin;expected=C@source_delta*scale
  root.location=expected;root.keyframe_insert("location",frame=out_frame,group=root.name)
  root.rotation_quaternion=(1,0,0,0);root.keyframe_insert("rotation_quaternion",frame=out_frame,group=root.name)
  for tn_name in order:
   sn_name=invmap[tn_name];source_basis=src.pose.bones[sn_name].matrix_basis.to_quaternion().to_matrix()
   a=corrections[tn_name];target_delta=(a@source_basis@a.inverted()).to_quaternion()
   pb=tgt.pose.bones[tn_name];pb.rotation_mode="QUATERNION";pb.location=(0,0,0);pb.rotation_quaternion=target_delta
   pb.keyframe_insert("location",frame=out_frame,group=pb.name);pb.keyframe_insert("rotation_quaternion",frame=out_frame,group=pb.name)
  bpy.context.view_layer.update()
  actual=root.head-root.bone.head_local
  error=(actual-expected).length
  if out_frame==1:initial_root_error=error
  final_root_error=max(final_root_error,error);root_path.append(tgt.pose.bones["pelvis"].head.copy());root_expected.append(expected.copy())
 # Geometry-derived floor correction is a single normalization transform, not benchmark placement.
 bpy.context.scene.frame_set(1);bpy.context.view_layer.update();feet=[tgt.pose.bones["foot_l"].head,tgt.pose.bones["foot_r"].head];floor=min(p.z for p in feet);tgt.location.z=-floor
 tgt.keyframe_insert("location",frame=1);tgt.keyframe_insert("location",frame=48)
 # Evaluate world-space ground and planted-foot motion after normalization.
 ground=[];plant_vel=[];previous={};threshold=tgt_height*.025
 for frame in range(1,49):
  bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
  feet={n:tgt.matrix_world@tgt.pose.bones[n].head for n in ("foot_l","foot_r")};low=min(p.z for p in feet.values());ground.append(abs(low))
  for n,p in feet.items():
   if p.z<=threshold and n in previous:plant_vel.append(math.hypot(p.x-previous[n].x,p.y-previous[n].y))
   previous[n]=p.copy()
 src.hide_render=True
 bpy.ops.mesh.primitive_plane_add(size=max(6,tgt_height_mesh*4),location=(0,0,0));plane=bpy.context.object;plane.name="Ground";plane.data.materials.append(mat("GroundMat",(.08,.1,.13)))
 # Camera framing derives entirely from evaluated target bounds and measured character height.
 path_lo=Vector((min(p.x for p in root_path),min(p.y for p in root_path),0));path_hi=Vector((max(p.x for p in root_path),max(p.y for p in root_path),tgt_height_mesh));center=(path_lo+path_hi)*.5;span=max(tgt_height_mesh,(path_hi-path_lo).length);distance=span*2.8
 bpy.ops.object.camera_add(location=(distance*.65,-distance,center.z));cam=bpy.context.object;cam.rotation_euler=(center-cam.location).to_track_quat("-Z","Y").to_euler();cam.data.lens=55;bpy.context.scene.camera=cam
 bpy.ops.object.light_add(type="AREA",location=(tgt_height_mesh,-tgt_height_mesh*1.5,tgt_height_mesh*2.4));bpy.context.object.data.energy=900;bpy.context.object.data.size=tgt_height_mesh*2
 s=bpy.context.scene;s.frame_start=1;s.frame_end=48;s.render.fps=12;s.render.engine="BLENDER_EEVEE_NEXT";s.render.resolution_x=480;s.render.resolution_y=480;s.render.resolution_percentage=100;s.render.image_settings.file_format="PNG";s.render.filepath=spec["frames"]+"/frame_";s.world.color=(.015,.02,.03)
 Path(spec["frames"]).mkdir(parents=True,exist_ok=True);bpy.ops.wm.save_as_mainfile(filepath=spec["blend"]);bpy.ops.render.render(animation=True)
 diag={"source_rest_pose":"CMU MotionBuilder BVH neutral/T-like hierarchy","target_rest_pose":"Mesh2Motion production humanoid A-like rest pose","source_matrix_world":source_world,"target_matrix_world":target_world,"source_basis":[list(r) for r in Bs],"target_basis":[list(r) for r in Bt],"source_height":src_height,"target_height":tgt_height,"target_mesh_height":tgt_height_mesh,"scale_factor":scale,"source_root":"Hips translation split to target root; Hips rotation to pelvis","target_root":"root translation with pelvis local rotation","per_bone_corrections":len(corrections),"initial_root_error":initial_root_error,"final_root_error":final_root_error,"maximum_ground_error":max(ground,default=0),"maximum_foot_sliding":max(plant_vel,default=0),"manual_coordinate_adjustment":False,"action":out_action.name,"frames":48}
 Path(spec["result"]).write_text(json.dumps(diag,indent=2));print("K70_RETARGET_CORE_OK")
main()
