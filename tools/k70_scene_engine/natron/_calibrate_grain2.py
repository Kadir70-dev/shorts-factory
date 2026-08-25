app = app1
INPUT = "C:/Users/Admin/shorts-factory/data/jobs/k70_vfx_director_benchmarks/financial_crisis/full/blender_pass/frame_0000.png"
OUTDIR = "C:/Users/Admin/AppData/Local/Temp/claude/C--WINDOWS-system32/774c773d-d5cc-4d80-9f3d-fde406f1b306/scratchpad/vfx_test/grain_calibrate2"
import os
os.makedirs(OUTDIR.replace("/", os.sep), exist_ok=True)

for opacity in [0.02, 0.05, 0.1, 0.2, 0.3]:
    r = app.createNode("fr.inria.openfx.ReadOIIO")
    r.getParam("filename").setValue(INPUT)
    g = app.createNode("eu.gmic.AddGrain")
    g.connectInput(0, r)
    g.getParam("Opacity").setValue(opacity)
    w = app.createNode("fr.inria.openfx.WriteOIIO")
    w.connectInput(0, g)
    w.getParam("filename").setValue(f"{OUTDIR}/grain_{opacity}.png")
    app.render(w, 0, 0)
    w.destroy()
    print(f"K70_CALIBRATE_OK opacity={opacity}")

print("K70_CALIBRATE_ALL_DONE")
