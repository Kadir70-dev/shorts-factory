"""Reusable Blender-side procedural contacts for retargeted humanoids.

Targets are inferred from object roles/names and bounding boxes.  The layer
adds and bakes native Blender IK constraints; it never edits source motion.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import bpy
from mathutils import Vector


def _bone(arm, *names):
    return next((arm.pose.bones.get(n) for n in names if arm.pose.bones.get(n)), None)


def world_point(obj, local=(0, 0, 0)):
    return obj.matrix_world @ Vector(local)


def bounds(obj):
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))), Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))


def find_role(role, objects=None):
    objects = objects or bpy.context.scene.objects
    role = role.lower()
    matches = [o for o in objects if str(o.get("k70_contact_role", "")).lower() == role]
    if not matches:
        matches = [o for o in objects if role in o.name.lower()]
    if not matches:
        raise LookupError(f"scene has no contact object for role {role!r}")
    return matches[0]


def target_from_object(obj, role, side="right"):
    lo, hi = bounds(obj); center = (lo + hi) * .5
    if role == "ground": return Vector((center.x, center.y, hi.z))
    if role == "chair": return Vector((center.x, center.y - .08 * (hi.y-lo.y), hi.z))
    if role == "keyboard": return Vector((center.x + (-.16 if side == "left" else .16) * (hi.x-lo.x), center.y, hi.z + .015))
    if role in {"document", "handshake"}: return center
    return center


def _empty(name, point):
    obj = bpy.data.objects.new(name, None); bpy.context.collection.objects.link(obj)
    obj.empty_display_type = "SPHERE"; obj.empty_display_size = .06; obj.location = point
    return obj


@dataclass
class ContactResult:
    role: str
    max_error: float
    samples: int


class ProceduralContactLayer:
    def __init__(self, armature, anchor):
        self.arm = armature; self.anchor = anchor; self.targets = []

    def character_height(self):
        pts = [self.arm.matrix_world @ b.head_local for b in self.arm.data.bones]
        return max(p.z for p in pts) - min(p.z for p in pts)

    def visible_sole(self, side):
        """World-space sole derived from evaluated skinned vertices."""
        suffix="_l" if side.startswith("l") else "_r";deps=bpy.context.evaluated_depsgraph_get();points=[]
        for obj in bpy.context.scene.objects:
            if obj.type!="MESH" or not obj.vertex_groups:continue
            groups={g.index for g in obj.vertex_groups if g.name in {"foot"+suffix,"ball"+suffix,"ball_leaf"+suffix}}
            if not groups:continue
            indices=[v.index for v in obj.data.vertices if any(x.group in groups and x.weight>.08 for x in v.groups)]
            ev=obj.evaluated_get(deps);mesh=ev.to_mesh();points.extend(ev.matrix_world@mesh.vertices[i].co for i in indices if i<len(mesh.vertices));ev.to_mesh_clear()
        if not points:raise RuntimeError(f"no evaluated mesh vertices for {side} sole")
        z=min(p.z for p in points);bottom=[p for p in points if p.z<=z+self.character_height()*.012]
        return Vector((sum(p.x for p in bottom)/len(bottom),sum(p.y for p in bottom)/len(bottom),z))

    def visible_ground(self,start,end,ground_obj=None):
        ground_obj=ground_obj or find_role("ground");ground_z=bounds(ground_obj)[1].z
        # First bake vertical sole contact without altering natural horizontal motion.
        for frame in range(start,end+1):
            bpy.context.scene.frame_set(frame);bpy.context.view_layer.update();soles=[self.visible_sole("left"),self.visible_sole("right")]
            self.anchor.location.z+=ground_z-min(p.z for p in soles);self.anchor.keyframe_insert("location",frame=frame)
        samples=[];lock_side=None;lock_point=None
        for frame in range(start,end+1):
            bpy.context.scene.frame_set(frame);bpy.context.view_layer.update();soles={s:self.visible_sole(s) for s in ("left","right")};side=min(soles,key=lambda s:soles[s].z);p=soles[side]
            if side!=lock_side:lock_side=side;lock_point=p.copy()
            self.anchor.location.x+=lock_point.x-p.x;self.anchor.location.y+=lock_point.y-p.y;self.anchor.keyframe_insert("location",frame=frame);bpy.context.view_layer.update();q=self.visible_sole(side);samples.append({"frame":frame,"side":side,"point":tuple(q)})
        errors=[abs(s["point"][2]-ground_z) for s in samples];slides=[math.hypot(b["point"][0]-a["point"][0],b["point"][1]-a["point"][1]) for a,b in zip(samples,samples[1:]) if a["side"]==b["side"]]
        return {"max_visible_ground_error":max(errors,default=0),"max_visible_planted_slide":max(slides,default=0),"anchors":["LEFT_SOLE","RIGHT_SOLE"]}

    def visible_seat_contact(self):
        deps=bpy.context.evaluated_depsgraph_get();points=[]
        for obj in bpy.context.scene.objects:
            if obj.type!="MESH" or not obj.vertex_groups:continue
            groups={g.index for g in obj.vertex_groups if g.name=="pelvis"}
            if not groups:continue
            indices=[v.index for v in obj.data.vertices if any(x.group in groups and x.weight>.12 for x in v.groups)]
            ev=obj.evaluated_get(deps);mesh=ev.to_mesh();points.extend(ev.matrix_world@mesh.vertices[i].co for i in indices if i<len(mesh.vertices));ev.to_mesh_clear()
        if not points:raise RuntimeError("no pelvis-weighted mesh vertices for SEAT_CONTACT")
        z=min(p.z for p in points);bottom=[p for p in points if p.z<=z+self.character_height()*.025]
        return Vector((sum(p.x for p in bottom)/len(bottom),sum(p.y for p in bottom)/len(bottom),z))

    def visible_chair(self,start,end,chair_obj=None):
        chair_obj=chair_obj or find_role("chair");lo,hi=bounds(chair_obj);target=Vector(((lo.x+hi.x)*.5,(lo.y+hi.y)*.5,hi.z));errors=[]
        for frame in range(start,end+1):
            bpy.context.scene.frame_set(frame);bpy.context.view_layer.update();p=self.visible_seat_contact();self.anchor.location+=target-p;self.anchor.keyframe_insert("location",frame=frame);bpy.context.view_layer.update();errors.append((self.visible_seat_contact()-target).length)
        return {"anchor":"SEAT_CONTACT","max_visible_chair_error":max(errors,default=0)}

    def ground(self, start, end, ground_obj=None):
        ground_obj = ground_obj or find_role("ground")
        ground_z = bounds(ground_obj)[1].z
        feet = [_bone(self.arm, "foot_l", "LeftFoot"), _bone(self.arm, "foot_r", "RightFoot")]; feet = [f for f in feet if f]
        samples=[]; locked={}
        for f in range(start, end+1):
            bpy.context.scene.frame_set(f); bpy.context.view_layer.update()
            points={p.name:self.arm.matrix_world @ p.head for p in feet}; planted=min(points, key=lambda n:points[n].z)
            p=points[planted]; target=locked.setdefault(planted, Vector((p.x,p.y,ground_z)))
            self.anchor.location += Vector((target.x-p.x,target.y-p.y,ground_z-min(v.z for v in points.values())))
            self.anchor.keyframe_insert("location", frame=f); bpy.context.view_layer.update()
            q=self.arm.matrix_world @ self.arm.pose.bones[planted].head; samples.append((q-target).length)
        return ContactResult("ground", max(samples, default=0), len(samples))

    def chair(self, start, end, chair_obj=None):
        chair_obj=chair_obj or find_role("chair"); pelvis=_bone(self.arm,"pelvis","hips","Hips")
        target=target_from_object(chair_obj,"chair"); errors=[]
        for f in range(start,end+1):
            bpy.context.scene.frame_set(f); bpy.context.view_layer.update(); p=self.arm.matrix_world @ pelvis.head
            self.anchor.location += target-p; self.anchor.keyframe_insert("location",frame=f); bpy.context.view_layer.update()
            errors.append((self.arm.matrix_world @ pelvis.head-target).length)
        return ContactResult("chair",max(errors,default=0),len(errors))

    def hand(self, side, role, start, end, target_obj=None, influence=1.0):
        target_obj=target_obj or find_role(role)
        suffix="Left" if side.startswith("l") else "Right"
        hand=_bone(self.arm,f"hand_{side[0]}",f"{suffix}Hand")
        fore=_bone(self.arm,f"lowerarm_{side[0]}",f"forearm_{side[0]}",f"{suffix}ForeArm")
        if not hand or not fore: raise RuntimeError(f"{side} arm chain unavailable")
        target=_empty(f"K70_{role}_{side}_target",target_from_object(target_obj,role,side)); self.targets.append(target)
        con=fore.constraints.new("IK"); con.name=f"K70_CONTACT_{role}"; con.target=target; con.chain_count=2
        con.use_rotation=False; con.influence=0; con.keyframe_insert("influence",frame=max(1,start-3))
        con.influence=influence; con.keyframe_insert("influence",frame=start); con.keyframe_insert("influence",frame=end)
        con.influence=0; con.keyframe_insert("influence",frame=end+3)
        errors=[]
        for f in range(start,end+1):
            bpy.context.scene.frame_set(f); bpy.context.view_layer.update(); errors.append((self.arm.matrix_world @ hand.head-target.location).length)
        return ContactResult(role,max(errors,default=0),len(errors))
