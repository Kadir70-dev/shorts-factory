"""Reusable Blender adapter for the verified per-bone CMU retarget math."""
from __future__ import annotations
from mathutils import Matrix
from bvh_adapter import import_action

MAP={"Hips":"pelvis","LowerBack":"spine_01","Spine":"spine_02","Spine1":"spine_03","Neck":"neck_01","Head":"head","LeftShoulder":"clavicle_l","LeftArm":"upperarm_l","LeftForeArm":"lowerarm_l","LeftHand":"hand_l","RightShoulder":"clavicle_r","RightArm":"upperarm_r","RightForeArm":"lowerarm_r","RightHand":"hand_r","LeftUpLeg":"thigh_l","LeftLeg":"calf_l","LeftFoot":"foot_l","RightUpLeg":"thigh_r","RightLeg":"calf_r","RightFoot":"foot_r"}

def _basis(arm,hips,head,left,right):
 h=arm.data.bones[hips].head_local;u=(arm.data.bones[head].tail_local-h).normalized();x=(arm.data.bones[right].head_local-arm.data.bones[left].head_local).normalized();f=x.cross(u).normalized();x=u.cross(f).normalized()
 return Matrix(((x.x,f.x,u.x),(x.y,f.y,u.y),(x.z,f.z,u.z))).transposed()
def _height(arm):
 z=[v for b in arm.data.bones for v in (b.head_local.z,b.tail_local.z)];return max(z)-min(z)

def retarget_bvh(bvh_path,target_armature,*,action_name,frames=48,start_fraction=0.0,end_fraction=1.0):
 import bpy
 src,source_action=import_action(bvh_path,name=action_name+"_source");src.hide_render=True
 bs=_basis(src,"Hips","Head","LeftUpLeg","RightUpLeg");bt=_basis(target_armature,"pelvis","head","thigh_l","thigh_r");c=bt@bs.inverted();scale=_height(target_armature)/_height(src)
 corrections={}
 for s,t in MAP.items():corrections[t]=target_armature.data.bones[t].matrix_local.to_3x3().normalized().inverted()@c@src.data.bones[s].matrix_local.to_3x3().normalized()
 total=int(source_action.frame_range[1]);first=max(2,round(2+(total-2)*start_fraction));last=max(first+1,round(2+(total-2)*end_fraction));samples=[first+round(i*(last-first)/(frames-1)) for i in range(frames)]
 action=bpy.data.actions.new(action_name);action.use_fake_user=True;target_armature.animation_data_create();target_armature.animation_data.action=action
 bpy.context.scene.frame_set(samples[0]);bpy.context.view_layer.update();origin=src.pose.bones["Hips"].head.copy();root=target_armature.pose.bones["root"];root.rotation_mode="QUATERNION"
 for frame,sf in enumerate(samples,1):
  bpy.context.scene.frame_set(sf);bpy.context.view_layer.update();delta=c@(src.pose.bones["Hips"].head-origin)*scale;root.location=delta;root.rotation_quaternion=(1,0,0,0);root.keyframe_insert("location",frame=frame);root.keyframe_insert("rotation_quaternion",frame=frame)
  for s,t in MAP.items():
   a=corrections[t];q=(a@src.pose.bones[s].matrix_basis.to_quaternion().to_matrix()@a.inverted()).to_quaternion();pb=target_armature.pose.bones[t];pb.rotation_mode="QUATERNION";pb.location=(0,0,0);pb.rotation_quaternion=q;pb.keyframe_insert("location",frame=frame);pb.keyframe_insert("rotation_quaternion",frame=frame)
 target_armature.animation_data.action=action
 return action,{"source":src,"scale":scale,"corrections":len(corrections)}
