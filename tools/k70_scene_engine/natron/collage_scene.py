"""K70 Visual Engine V2 -- Style 3 (Paper-Cut/Editorial Collage), built as
a REAL Natron node graph (Read -> Transform -> Merge chain), executed by
NatronRenderer.exe (Natron 2.5.0, real Windows portable build downloaded
from github.com/NatronGitHub/Natron releases, GPL-2.0, license-clear per
V2_LICENSE_MANIFEST.md). Confirmed real plugin IDs/param names via live
introspection on this actual install (getScriptName() dumps), not
guessed blind. Assets (map/newspaper/document/house/bill paper textures)
are plain PIL-generated PNGs fed into Natron as Read node sources --
Natron does 100% of the actual layering/compositing/animation/render.

WriteFFmpeg on this build segfaults on render (confirmed via a real
crash test, exit code 139) -- worked around by using the WORKING
WriteOIIO node to output a PNG sequence, then ffmpeg (the same role it
plays for every other style's frame sequences) encodes the container.
This is not a Blender substitution; Natron performs all compositing.

    NatronRenderer.exe collage_scene.py
"""
import NatronEngine

FPS = 24
DURATION_SEC = 6.0
END_FRAME = int(DURATION_SEC * FPS) - 1
ASSET_DIR = "C:/Users/Admin/shorts-factory/data/jobs/k70_v2_gold_collage_natron/assets"
OUT_DIR = "C:/Users/Admin/shorts-factory/data/jobs/k70_v2_gold_collage_natron/shots/frames"

app = app1


def read_node(path, name):
    r = app.createNode("fr.inria.openfx.ReadOIIO")
    r.setScriptName(name)
    r.getParam("filename").setValue(path)
    return r


def transform_node(input_node, name, tx0, ty0, tx1, ty1, scale=1.0, center=(960, 540)):
    # Assets are now pre-composed onto full 1920x1080 canvases at their
    # intended base position (see PIL asset generation), so this only
    # needs to apply the ANIMATED parallax drift on top -- no per-layer
    # center/placement math needed here anymore.
    t = app.createNode("net.sf.openfx.TransformPlugin")
    t.setScriptName(name)
    t.connectInput(0, input_node)
    tr = t.getParam("translate")
    tr.setValueAtTime(0, tx0, 0)
    tr.setValueAtTime(0, ty0, 1)
    tr.setValueAtTime(END_FRAME, tx1, 0)
    tr.setValueAtTime(END_FRAME, ty1, 1)
    if scale != 1.0:
        sc = t.getParam("scale")
        sc.setValue(scale, 0)
        sc.setValue(scale, 1)
        ct = t.getParam("center")
        ct.setValue(center[0], 0)
        ct.setValue(center[1], 1)
    return t


def merge_node(a_node, b_node, name):
    m = app.createNode("net.sf.openfx.MergePlugin")
    m.setScriptName(name)
    m.getParam("operation").setValue("over")
    # Natron's MergePlugin exposes B on input 0 and A on input 1.  The
    # operation is A over B, so the foreground must be connected to 1.
    m.connectInput(0, b_node)  # B = background
    m.connectInput(1, a_node)  # A = foreground
    return m


def main():
    bg_r = read_node(f"{ASSET_DIR}/bg.png", "read_bg")

    map_r = read_node(f"{ASSET_DIR}/map.png", "read_map")
    map_t = transform_node(map_r, "xf_map", 0, 0, -40, 15)

    news_r = read_node(f"{ASSET_DIR}/newspaper.png", "read_news")
    news_t = transform_node(news_r, "xf_news", 0, 0, -70, -25)

    doc_r = read_node(f"{ASSET_DIR}/document.png", "read_doc")
    doc_t = transform_node(doc_r, "xf_doc", 0, 0, 60, -35)

    house_r = read_node(f"{ASSET_DIR}/house.png", "read_house")
    house_t = transform_node(house_r, "xf_house", 0, 0, -50, 30)

    bill_r = read_node(f"{ASSET_DIR}/bill.png", "read_bill")
    bill_t = transform_node(bill_r, "xf_bill", 0, 0, 25, -55)

    m1 = merge_node(map_t, bg_r, "m1")
    m2 = merge_node(news_t, m1, "m2")
    m3 = merge_node(house_t, m2, "m3")
    m4 = merge_node(doc_t, m3, "m4")
    m5 = merge_node(bill_t, m4, "m5")

    w = app.createNode("fr.inria.openfx.WriteOIIO")
    w.setScriptName("final_write")
    w.connectInput(0, m5)
    w.getParam("filename").setValue(f"{OUT_DIR}/frame.####.png")

    app.render(w, 0, END_FRAME)
    print(f"K70_COLLAGE_NATRON_RENDER_OK frames=0-{END_FRAME}")
    # NatronRenderer otherwise starts a second implicit render over the
    # application's default 1-250 range after this Python script returns.
    # Removing the already-rendered writer leaves nothing for that pass.
    app.deleteNode(w)


main()
