"""Headless CMU-BVH import and reusable Blender Action cache."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
BVH_ROOT=ROOT/"data/assets/motions/cmu/bvh"
CACHE=ROOT/"data/assets/motions/cache/cmu_bvh"
EXPECTED={
 "18_08":("explain_hands","conversation - explain with hand gestures",120),
 "79_85":("type_laptop","typing on a laptop",60),
 "18_01":("handshake","walk, shake hands - subject A",120),
 "13_01":("sit_down_stand_up","sit on high stool, stand up",120),
}

def verify_files():
    CACHE.mkdir(parents=True,exist_ok=True); rows=[]
    for key,(action,description,fps) in EXPECTED.items():
        path=BVH_ROOT/f"{key}.bvh"; text=path.read_text(encoding="ascii",errors="strict")
        if not text.startswith("HIERARCHY") or "MOTION" not in text or "Frames:" not in text:
            raise ValueError(f"invalid BVH {path}")
        frames=int(text.split("Frames:",1)[1].splitlines()[0].strip())
        row={"cmu_id":key,"action":action,"description":description,"fps":fps,"frames":frames,
             "path":str(path.relative_to(ROOT)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
             "source":"https://github.com/una-dinosauria/cmu-mocap"}
        (CACHE/f"{key}.json").write_text(json.dumps(row,indent=2),encoding="utf-8"); rows.append(row)
    return rows

def import_action(path, *, name=None, frame_start=1, global_scale=.025):
    """Run inside Blender. Returns the imported armature and reusable Action."""
    import bpy
    before=set(bpy.data.objects)
    bpy.ops.import_anim.bvh(filepath=str(path),frame_start=frame_start,rotate_mode="NATIVE",global_scale=global_scale)
    arm=next(o for o in bpy.data.objects if o not in before and o.type=="ARMATURE")
    action=arm.animation_data.action; action.name=name or Path(path).stem
    action.use_fake_user=True
    return arm,action
