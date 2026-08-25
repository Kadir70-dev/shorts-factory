"""One-off introspection script: dumps real param scriptNames/labels for
the OFX nodes the K70 VFX Director will use, run live via NatronRenderer
(same methodology collage_scene.py used -- confirm via getScriptName()
dumps, don't guess param names blind).

    NatronRenderer.exe _introspect_params.py
"""
app = app1

PLUGIN_IDS = [
    "net.sf.openfx.ColorCorrectPlugin",
    "net.sf.openfx.GradePlugin",
    "net.sf.openfx.SaturationPlugin",
    "net.sf.openfx.GodRays",
    "net.sf.cimg.CImgBloom",
    "eu.gmic.Vignette",
    "eu.gmic.RainSnow",
    "eu.gmic.LightRays",
    "eu.gmic.LightGlow",
    "eu.gmic.AddGrain",
    "eu.gmic.ToneMappingFast",
]

for pid in PLUGIN_IDS:
    print(f"\n=== {pid} ===")
    try:
        n = app.createNode(pid)
    except Exception as e:
        print("  FAILED TO CREATE:", e)
        continue
    if n is None:
        print("  createNode returned None")
        continue
    try:
        params = n.getParams()
        for p in params:
            try:
                print(" ", p.getScriptName(), "|", p.getTypeName())
            except Exception as e:
                print("  <param introspection error>", e)
    except Exception as e:
        print("  getParams() FAILED:", e)

print("\nK70_INTROSPECT_DONE")
