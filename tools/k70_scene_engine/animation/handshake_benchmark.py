from __future__ import annotations
import json,subprocess,tempfile
from pathlib import Path
from PIL import Image,ImageDraw
from ..blender.bpy_bridge import find_blender
from .mesh2motion_adapter import HUMAN_BASE
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/"data/benchmarks/cmu_visible_handshake";SCRIPT=Path(__file__).with_name("_handshake_benchmark_blender.py")
def run():
 OUT.mkdir(parents=True,exist_ok=True);frames=OUT/"frames";spec={"target":str(HUMAN_BASE),"bvh":str(ROOT/"data/assets/motions/cmu/bvh/18_01.bvh"),"frames":str(frames),"blend":str(OUT/"scene.blend"),"result":str(OUT/"result.json")}
 with tempfile.NamedTemporaryFile("w",suffix=".json",delete=False) as f:json.dump(spec,f);arg=f.name
 p=subprocess.run([str(find_blender()),"--background","--python",str(SCRIPT),"--",arg],capture_output=True,text=True,timeout=1200);Path(arg).unlink(missing_ok=True)
 if p.returncode or "K70_HANDSHAKE_OK" not in p.stdout:raise RuntimeError(p.stdout[-5000:]+p.stderr[-3000:])
 ff=next(iter((ROOT/"tools/k70_scene_engine/vendor/natron_win/extracted").rglob("ffmpeg.exe")));video=OUT/"preview.mp4";subprocess.run([str(ff),"-y","-framerate","12","-i",str(frames/"frame_%04d.png"),"-c:v","libx264","-pix_fmt","yuv420p",str(video)],check=True,capture_output=True)
 picks=(1,12,24,36,48);ims=[Image.open(frames/f"frame_{n:04d}.png").convert("RGB") for n in picks];sheet=Image.new("RGB",(2400,505),"#111");d=ImageDraw.Draw(sheet)
 for i,(im,n) in enumerate(zip(ims,picks)):sheet.paste(im,(i*480,0));d.text((i*480+8,486),f"frame {n}",fill="white")
 sheet.save(OUT/"contact_sheet.jpg",quality=92);[x.close() for x in ims];r=json.loads((OUT/"result.json").read_text());r.update({"video":str(video),"contact_sheet":str(OUT/"contact_sheet.jpg")});return r
if __name__=="__main__":print(json.dumps(run(),indent=2))
