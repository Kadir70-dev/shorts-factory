from __future__ import annotations
import json,subprocess,tempfile
from pathlib import Path
from PIL import Image,ImageDraw
from ..blender.bpy_bridge import find_blender
from .bvh_adapter import BVH_ROOT,verify_files
from .mesh2motion_adapter import HUMAN_BASE

ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/"data/benchmarks/cmu_contact";SCRIPT=Path(__file__).with_name("_contact_bvh_benchmark.py")
def ffmpeg():
    paths=list((ROOT/"tools/k70_scene_engine/vendor/natron_win/extracted").rglob("ffmpeg.exe"));paths.append(ROOT/"tools/k70_scene_engine/vendor/synfig_win/extracted/bin/ffmpeg.exe");return next((p for p in paths if p.exists()),Path("ffmpeg"))
def one(kind):
    out=OUT/f"test_{kind.lower()}";frames=out/"frames";out.mkdir(parents=True,exist_ok=True)
    spec={"kind":kind,"bvh_root":str(BVH_ROOT),"target":str(HUMAN_BASE),"frames":str(frames),"blend":str(out/"scene.blend"),"result":str(out/"structural.json")}
    with tempfile.NamedTemporaryFile("w",suffix=".json",delete=False) as f:json.dump(spec,f);arg=f.name
    p=subprocess.run([str(find_blender()),"--background","--python",str(SCRIPT),"--",arg],capture_output=True,text=True,timeout=1200);Path(arg).unlink(missing_ok=True)
    if p.returncode or "K70_CONTACT_BENCHMARK_OK" not in p.stdout:raise RuntimeError(p.stdout[-5000:]+p.stderr[-3000:])
    video=out/"benchmark.mp4";q=subprocess.run([str(ffmpeg()),"-y","-framerate","12","-i",str(frames/"frame_%04d.png"),"-c:v","libx264","-pix_fmt","yuv420p",str(video)],capture_output=True,text=True)
    if q.returncode:raise RuntimeError(q.stderr[-2000:])
    picks=(1,12,24,36,48);ims=[Image.open(frames/f"frame_{n:04d}.png").convert("RGB") for n in picks];sheet=Image.new("RGB",(480*5,295),"#11151b");d=ImageDraw.Draw(sheet)
    for i,(im,n) in enumerate(zip(ims,picks)):sheet.paste(im,(480*i,0));d.text((480*i+8,276),f"frame {n}",fill="white")
    sheet.save(out/"contact_sheet.jpg",quality=92);[im.close() for im in ims]
    result=json.loads((out/"structural.json").read_text());result.update({"video":str(video),"contact_sheet":str(out/"contact_sheet.jpg")});return result
def run():
    OUT.mkdir(parents=True,exist_ok=True);verified=verify_files();result={k:one(k) for k in "ABCD"};report={"verified":verified,"benchmarks":result};(OUT/"report.json").write_text(json.dumps(report,indent=2));return report
if __name__=="__main__":print(json.dumps(run(),indent=2))
