"""Blender entry point for the four isolated CMU contact benchmarks."""
from __future__ import annotations
import json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector

HERE=Path(__file__).resolve().parent; sys.path.insert(0,str(HERE))
from contact_layer import ProceduralContactLayer
from rest_retarget_blender import retarget_bvh

TARGET=None

def args():
    i=sys.argv.index("--"); return json.loads(Path(sys.argv[i+1]).read_text())
def mat(name,c):
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name); m.diffuse_color=(*c,1); return m
def cube(name,loc,scale,color,role=None):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=bpy.context.object; o.name=name; o.scale=scale; o.data.materials.append(mat(name+"Mat",color))
    if role:o["k70_contact_role"]=role
    return o
def stage(two=False):
    cube("K70_Ground",(0,0,-.04),(5,4,.04),(.08,.1,.13),"ground")
    bpy.ops.object.light_add(type="AREA",location=(2,-3,5)); bpy.context.object.data.energy=900; bpy.context.object.data.shape="DISK"; bpy.context.object.data.size=4
    bpy.ops.object.light_add(type="AREA",location=(-3,1,3)); bpy.context.object.data.energy=500; bpy.context.object.data.color=(.3,.5,1); bpy.context.object.data.size=3
    bpy.ops.object.camera_add(location=(3.4,-5.7,2.5)); cam=bpy.context.object; target=Vector((0,0,1.05)); cam.rotation_euler=(target-cam.location).to_track_quat("-Z","Y").to_euler(); cam.data.lens=55; bpy.context.scene.camera=cam
def body(arm,color):
    material=mat("Person"+str(color),color)
    skip={"Hips","LHipJoint","RHipJoint","LeftFingerBase","RightFingerBase"}
    for b in arm.data.bones:
        if b.name in skip or b.length<.025: continue
        bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=.045,depth=max(.04,b.length))
        o=bpy.context.object; o.name="Body_"+b.name; o.data.materials.append(material); o.parent=arm; o.parent_type="BONE"; o.parent_bone=b.name; o.location=(0,b.length*.5,0); o.rotation_euler=(0,0,0)
    head=arm.pose.bones.get("Head")
    if head:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,radius=.12); o=bpy.context.object; o.data.materials.append(material); o.parent=arm; o.parent_type="BONE"; o.parent_bone="Head"; o.location=(0,head.length,0)
def person(path,name,color,location=(0,0,0),yaw=0):
    before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=TARGET);objects=[o for o in bpy.data.objects if o not in before];arm=next(o for o in objects if o.type=="ARMATURE");arm.name=name;arm.animation_data_clear();action,_=retarget_bvh(path,arm,action_name="K70_CMU_"+Path(path).stem)
    anchor=bpy.data.objects.new(name+"_Anchor",None);bpy.context.collection.objects.link(anchor);anchor.location=location;anchor.rotation_euler.z=yaw
    imported=set(objects)
    for o in objects:
        if o.parent not in imported:o.parent=anchor
    return arm,anchor,action
def height(arm):
    z=[v for b in arm.data.bones for v in (b.head_local.z,b.tail_local.z)];return max(z)-min(z)
def hand_world(arm,side):return arm.matrix_world@arm.pose.bones[f"hand_{side[0]}"].head
def chair(arm):
    h=height(arm);p=arm.matrix_world@arm.pose.bones["pelvis"].head;seat=cube("K70_Chair",(p.x,p.y,p.z-h*.09),(h*.24,h*.24,h*.04),(.32,.16,.06),"chair");cube("ChairBack",(p.x,p.y+h*.23,p.z+h*.18),(h*.24,h*.04,h*.28),(.32,.16,.06));return seat
def configure(out):
    s=bpy.context.scene;s.frame_start=1;s.frame_end=48;s.render.fps=12;s.render.engine="BLENDER_EEVEE_NEXT";s.render.resolution_x=480;s.render.resolution_y=270;s.render.resolution_percentage=100;s.render.image_settings.file_format="PNG";s.render.filepath=str(out/"frame_");s.world.color=(.015,.02,.03);out.mkdir(parents=True,exist_ok=True)
def run(spec):
    global TARGET;TARGET=spec["target"];stage(); kind=spec["kind"]; root=Path(spec["bvh_root"]); qa={}; actions=[]
    if kind=="A":
        arm,anchor,act=person(root/"13_01.bvh","Actor",(.25,.55,.9));actions=[act.name];bpy.context.scene.frame_set(24);seat=chair(arm);layer=ProceduralContactLayer(arm,anchor);qa["ground_pre"]=layer.ground(1,12).__dict__;qa["chair"]=layer.chair(17,34,seat).__dict__;qa["ground_post"]=layer.ground(40,48).__dict__
    elif kind=="B":
        arm,anchor,act=person(root/"79_85.bvh","Typist",(.2,.7,.35));actions=[act.name];bpy.context.scene.frame_set(24);seat=chair(arm);lh,rh=hand_world(arm,"left"),hand_world(arm,"right");m=(lh+rh)*.5;h=height(arm);kb=cube("Keyboard",m,(max((lh-rh).length*.6,h*.12),h*.08,h*.015),(.06,.07,.08),"keyboard");desk=cube("Desk",(m.x,m.y,m.z-h*.04),(h*.42,h*.25,h*.03),(.18,.18,.2));layer=ProceduralContactLayer(arm,anchor);qa["chair"]=layer.chair(1,48,seat).__dict__;qa["left_hand"]=layer.hand("left","keyboard",8,42,kb).__dict__;qa["right_hand"]=layer.hand("right","keyboard",8,42,kb).__dict__
    elif kind=="C":
        a,aa,act=person(root/"18_01.bvh","ActorA",(.9,.1,0));b,ba,act2=person(root/"18_01.bvh","ActorB",(.9,.45,.2));reach=a.data.bones["upperarm_r"].length+a.data.bones["lowerarm_r"].length;aa.location.x=-reach*.8;ba.location.x=reach*.8;aa.rotation_euler.z=-math.pi/2;ba.rotation_euler.z=math.pi/2;bpy.context.scene.frame_set(24);bpy.context.view_layer.update();mid=(hand_world(a,"right")+hand_world(b,"right"))*.5;actions=[act.name,act2.name];marker=cube("HandshakeTarget",mid,(reach*.025,)*3,(.8,.8,.1),"handshake");la=ProceduralContactLayer(a,aa);lb=ProceduralContactLayer(b,ba);qa["a_ground"]=la.ground(1,48).__dict__;qa["b_ground"]=lb.ground(1,48).__dict__;qa["a_hand"]=la.hand("right","handshake",16,36,marker).__dict__;qa["b_hand"]=lb.hand("right","handshake",16,36,marker).__dict__
    else:
        a,aa,act=person(root/"18_08.bvh","Giver",(.25,.6,.9));b,ba,act2=person(root/"18_08.bvh","Receiver",(.8,.4,.2));reach=a.data.bones["upperarm_r"].length+a.data.bones["lowerarm_r"].length;aa.location.x=-reach*.8;ba.location.x=reach*.8;aa.rotation_euler.z=-math.pi/2;ba.rotation_euler.z=math.pi/2;bpy.context.scene.frame_set(20);bpy.context.view_layer.update();give=hand_world(a,"right");receive=hand_world(b,"right");mid=(give+receive)*.5;actions=[act.name,act2.name];doc=cube("Document",give,(reach*.12,reach*.015,reach*.08),(.9,.85,.65),"document");la=ProceduralContactLayer(a,aa);lb=ProceduralContactLayer(b,ba);qa["a_ground"]=la.ground(1,48).__dict__;qa["b_ground"]=lb.ground(1,48).__dict__;ra=la.hand("right","document",10,27,doc);rb=lb.hand("right","document",26,43,doc);qa["giver_hand"]=ra.__dict__;qa["receiver_hand"]=rb.__dict__;doc.location=give;doc.keyframe_insert("location",frame=1);doc.keyframe_insert("location",frame=24);doc.location=receive;doc.keyframe_insert("location",frame=32);doc.keyframe_insert("location",frame=48)
        # Scene-derived hand targets follow the same prop transfer curve.
        for target in la.targets+lb.targets:
            target.location=give;target.keyframe_insert("location",frame=1);target.keyframe_insert("location",frame=24);target.location=receive;target.keyframe_insert("location",frame=32);target.keyframe_insert("location",frame=48)
    out=Path(spec["frames"]);configure(out);bpy.ops.wm.save_as_mainfile(filepath=spec["blend"]);bpy.ops.render.render(animation=True)
    Path(spec["result"]).write_text(json.dumps({"kind":kind,"actions":actions,"qa":qa,"manual_per_frame":False},indent=2));print("K70_CONTACT_BENCHMARK_OK")
run(args())
