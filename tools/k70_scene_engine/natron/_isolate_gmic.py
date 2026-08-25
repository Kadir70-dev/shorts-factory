"""Isolate each GMIC/OFX node on a single test frame to find which ones
actually work vs. produce broken/blank output on this Natron build.
"""
import os

app = app1
INPUT = "C:/Users/Admin/AppData/Local/Temp/claude/C--WINDOWS-system32/774c773d-d5cc-4d80-9f3d-fde406f1b306/scratchpad/vfx_test/blender_out_test/frame_0000.png"
OUTDIR = "C:/Users/Admin/AppData/Local/Temp/claude/C--WINDOWS-system32/774c773d-d5cc-4d80-9f3d-fde406f1b306/scratchpad/vfx_test/gmic_isolate"
os.makedirs(OUTDIR.replace("/", os.sep), exist_ok=True)


def test_node(tag, build_fn):
    r = app.createNode("fr.inria.openfx.ReadOIIO")
    r.setScriptName(f"read_{tag}")
    r.getParam("filename").setValue(INPUT)
    node = build_fn(r)
    w = app.createNode("fr.inria.openfx.WriteOIIO")
    w.setScriptName(f"write_{tag}")
    w.connectInput(0, node)
    w.getParam("filename").setValue(f"{OUTDIR}/{tag}.png")
    try:
        app.render(w, 0, 0)
        print(f"K70_ISOLATE_{tag}_RENDER_OK")
    except Exception as e:
        print(f"K70_ISOLATE_{tag}_RENDER_FAILED", e)
    w.destroy()  # prevents NatronRenderer's own implicit default-range render afterward


def rainsnow(inp):
    n = app.createNode("eu.gmic.RainSnow")
    n.setScriptName("rain")
    n.connectInput(0, inp)
    n.getParam("Angle").setValue(12.0)
    n.getParam("Speed").setValue(0.55)
    n.getParam("Density_").setValue(45.0)
    return n


def lightglow(inp):
    n = app.createNode("eu.gmic.LightGlow")
    n.setScriptName("glow")
    n.connectInput(0, inp)
    n.getParam("Amplitude").setValue(18.0)
    n.getParam("Density").setValue(40.0)
    return n


def addgrain(inp):
    n = app.createNode("eu.gmic.AddGrain")
    n.setScriptName("grain")
    n.connectInput(0, inp)
    n.getParam("Opacity").setValue(12.0)
    return n


def vignette(inp):
    n = app.createNode("eu.gmic.Vignette")
    n.setScriptName("vig")
    n.connectInput(0, inp)
    n.getParam("Strength").setValue(32.0)
    return n


def gradeonly(inp):
    n = app.createNode("net.sf.openfx.GradePlugin")
    n.setScriptName("grade")
    n.connectInput(0, inp)
    n.getParam("multiply").set(0.9, 0.94, 1.05, 1.0)
    return n


test_node("rain", rainsnow)
test_node("glow", lightglow)
test_node("grain", addgrain)
test_node("vignette", vignette)
test_node("grade", gradeonly)

print("K70_ISOLATE_ALL_DONE")
