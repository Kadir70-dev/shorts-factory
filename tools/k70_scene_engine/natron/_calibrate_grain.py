"""One-off calibration: render eu.gmic.AddGrain at several Opacity values
on a real HERO-resolution frame to find a genuinely SUBTLE setting (the
shipped presets' Opacity values, 1.95-16.0 on a 0-100 scale, all read as
heavy/dominant grain in visual QA -- this empirically finds a better
range instead of guessing).
"""
app = app1
INPUT = "C:/Users/Admin/shorts-factory/data/jobs/k70_vfx_director_benchmarks/financial_crisis/full/blender_pass/frame_0000.png"
OUTDIR = "C:/Users/Admin/AppData/Local/Temp/claude/C--WINDOWS-system32/774c773d-d5cc-4d80-9f3d-fde406f1b306/scratchpad/vfx_test/grain_calibrate"
import os
os.makedirs(OUTDIR.replace("/", os.sep), exist_ok=True)

for opacity in [0.5, 1.0, 2.0, 4.0, 8.0]:
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
