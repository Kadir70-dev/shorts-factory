from __future__ import annotations
import json,subprocess,tempfile
from pathlib import Path
from PIL import Image,ImageDraw
from ..blender.bpy_bridge import find_blender
from .mesh2motion_adapter import HUMAN_BASE

ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/"data/benchmarks/cmu_retarget_core";SCRIPT=Path(__file__).with_name("_retarget_core_blender.py")
def ffmpeg():
 p=list((ROOT/"tools/k70_scene_engine/vendor/natron_win/extracted").rglob("ffmpeg.exe"));p.append(ROOT/"tools/k70_scene_engine/vendor/synfig_win/extracted/bin/ffmpeg.exe");return next((x for x in p if x.exists()),Path("ffmpeg"))
def run():
 OUT.mkdir(parents=True,exist_ok=True);frames=OUT/"frames";spec={"bvh":str(ROOT/"data/assets/motions/cmu/bvh/18_01.bvh"),"target":str(HUMAN_BASE),"frames":str(frames),"blend":str(OUT/"scene.blend"),"result":str(OUT/"diagnostics.json")}
 with tempfile.NamedTemporaryFile("w",suffix=".json",delete=False) as f:json.dump(spec,f);arg=f.name
 p=subprocess.run([str(find_blender()),"--background","--python",str(SCRIPT),"--",arg],capture_output=True,text=True,timeout=1200);Path(arg).unlink(missing_ok=True)
 if p.returncode or "K70_RETARGET_CORE_OK" not in p.stdout:raise RuntimeError(p.stdout[-6000:]+p.stderr[-3000:])
 video=OUT/"preview.mp4";q=subprocess.run([str(ffmpeg()),"-y","-framerate","12","-i",str(frames/"frame_%04d.png"),"-c:v","libx264","-pix_fmt","yuv420p",str(video)],capture_output=True,text=True);assert q.returncode==0,q.stderr[-2000:]
 picks=(1,12,24,36,48);ims=[Image.open(frames/f"frame_{n:04d}.png").convert("RGB") for n in picks];sheet=Image.new("RGB",(480*5,505),"#11151b");d=ImageDraw.Draw(sheet)
 for i,(im,n) in enumerate(zip(ims,picks)):sheet.paste(im,(i*480,0));d.text((i*480+8,486),f"frame {n}",fill="white")
 sheet.save(OUT/"contact_sheet.jpg",quality=92);[im.close() for im in ims]
 result=json.loads((OUT/"diagnostics.json").read_text());result.update({"video":str(video),"contact_sheet":str(OUT/"contact_sheet.jpg")});(OUT/"report.json").write_text(json.dumps(result,indent=2));return result
if __name__=="__main__":print(json.dumps(run(),indent=2))
