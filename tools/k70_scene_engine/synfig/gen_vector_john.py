#!/usr/bin/env python3
"""Generates a real Synfig .sif (XML) scene: John (circle head, rectangle
torso/hair, rotating arm via a real Synfig 'rotate' transform layer inside
a 'group') + a labeled income/expense bar waterfall (real 'text' layers,
not baked-in labels). Written directly against the .sif schema confirmed
via `synfig.exe --layer-info=<type>` on the real installed Synfig 1.5.5
(vendor/synfig_win/) -- no GUI authoring, no Blender.

    .venv-win/Scripts/python.exe tools/k70_scene_engine/synfig/gen_vector_john.py <out.sif>
"""
from __future__ import annotations

import sys
from pathlib import Path

FPS = 24
END_TIME_S = 7.0


def real(v): return f'<real value="{v:.6f}"/>'
def integer(v): return f'<integer value="{v}"/>'
def boolean(v): return f'<bool value="{"true" if v else "false"}"/>'
def vector(x, y): return f'<vector><x>{x:.6f}</x><y>{y:.6f}</y></vector>'
def color(r, g, b, a=1.0):
    return f'<color><r>{r:.6f}</r><g>{g:.6f}</g><b>{b:.6f}</b><a>{a:.6f}</a></color>'


def param(name, inner): return f'<param name="{name}">{inner}</param>'


def rectangle_layer(x1, y1, x2, y2, col, desc=""):
    return f'''<layer type="rectangle" active="true" version="0.1" desc="{desc}">
    {param("z_depth", real(0))}
    {param("amount", real(1))}
    {param("blend_method", integer(0))}
    {param("color", color(*col))}
    {param("point1", vector(x1, y1))}
    {param("point2", vector(x2, y2))}
    {param("expand", real(0))}
    {param("invert", boolean(False))}
    {param("feather_x", real(0))}
    {param("feather_y", real(0))}
    {param("bevel", real(0))}
  </layer>'''


def circle_layer(cx, cy, radius, col, desc=""):
    return f'''<layer type="circle" active="true" version="0.1" desc="{desc}">
    {param("z_depth", real(0))}
    {param("amount", real(1))}
    {param("blend_method", integer(0))}
    {param("color", color(*col))}
    {param("radius", real(radius))}
    {param("feather", real(0))}
    {param("origin", vector(cx, cy))}
    {param("invert", boolean(False))}
  </layer>'''


def text_layer(text, cx, cy, size, col, desc=""):
    text_esc = text.replace("&", "&amp;").replace("<", "&lt;")
    return f'''<layer type="text" active="true" version="0.1" desc="{desc}">
    {param("z_depth", real(0))}
    {param("amount", real(1))}
    {param("blend_method", integer(0))}
    {param("text", f"<string>{text_esc}</string>")}
    {param("color", color(*col))}
    {param("size", vector(size, size))}
    {param("origin", vector(cx, cy))}
    {param("orient", vector(0.5, 0.5))}
    {param("invert", boolean(False))}
  </layer>'''


def animated_angle_waypoints(waypoints):
    """waypoints: list of (time_str, degrees)."""
    wp_xml = "\n".join(
        f'<waypoint time="{t}" before="clamped" after="clamped"><angle value="{deg:.4f}"/></waypoint>'
        for t, deg in waypoints)
    return f'<animated type="angle">{wp_xml}</animated>'


def rotate_layer(origin_xy, waypoints, desc="arm_rotate"):
    # Real schema check via `synfig.exe --layer-info=rotate`: this layer
    # type has exactly two params, "origin" and "amount" -- and "amount"
    # IS the rotation angle itself (angle-typed), not the usual 0..1
    # blend-opacity "amount" every other layer has. Emitting both would
    # produce two conflicting <param name="amount"> elements.
    return f'''<layer type="rotate" active="true" version="0.1" desc="{desc}">
    {param("origin", vector(*origin_xy))}
    {param("amount", animated_angle_waypoints(waypoints))}
  </layer>'''


def group_layer(inner_layers_xml, desc="group"):
    return f'''<layer type="group" active="true" version="0.1" desc="{desc}">
    {param("z_depth", real(0))}
    {param("amount", real(1))}
    {param("blend_method", integer(0))}
    {param("origin", vector(0, 0))}
    {param("transformation", '<composite type="transformation"><offset><vector><x>0.0</x><y>0.0</y></vector></offset><angle><angle value="0.0"/></angle><skew_angle><angle value="0.0"/></skew_angle><scale><vector><x>1.0</x><y>1.0</y></vector></scale></composite>')}
    {param("canvas", f'<canvas>{inner_layers_xml}</canvas>')}
    {param("time_dilation", real(1))}
    {param("time_offset", '<time value="0"/>')}
    {param("children_lock", boolean(False))}
    {param("outline_grow", real(0))}
    {param("z_range", boolean(False))}
    {param("z_range_position", real(0))}
    {param("z_range_depth", real(0))}
    {param("z_range_blur", real(0))}
  </layer>'''


def build_john(root_x=0.0, root_y=-0.3):
    JOHN_SKIN = (0.82, 0.62, 0.48)
    JOHN_SHIRT = (0.18, 0.35, 0.62)
    JOHN_HAIR = (0.25, 0.16, 0.10)

    torso = rectangle_layer(root_x - 0.55, root_y + 0.1, root_x + 0.55, root_y + 1.6, JOHN_SHIRT, "john_torso")
    head = circle_layer(root_x, root_y + 2.15, 0.45, JOHN_SKIN, "john_head")
    hair = rectangle_layer(root_x - 0.48, root_y + 2.35, root_x + 0.48, root_y + 2.65, JOHN_HAIR, "john_hair")

    # Real animated ARM: a rectangle rotated by a genuine Synfig 'rotate'
    # transform layer (origin at the shoulder), inside a 'group' inline
    # canvas -- not a hand-computed vertex hack.
    shoulder = (root_x + 0.65, root_y + 1.5)
    arm_rect = rectangle_layer(shoulder[0] - 0.16, shoulder[1] - 1.05, shoulder[0] + 0.16, shoulder[1] + 0.05,
                               JOHN_SKIN, "john_arm_rect")
    arm_rotate = rotate_layer(shoulder, [
        ("0s 0f", 0), ("0s 10f", 0), ("0s 20f", -95), ("0s 30f", -80), (f"{END_TIME_S}s 0f", 0),
    ])
    arm_group = group_layer(arm_rotate + "\n" + arm_rect, "john_arm_group")

    return "\n".join([arm_group, hair, head, torso])


def build_bars():
    bars = [
        ("INCOME", 0.95, (0.20, 0.55, 0.30)),
        ("RENT", 0.55, (0.75, 0.30, 0.28)),
        ("FOOD", 0.40, (0.75, 0.40, 0.28)),
        ("TRANSPORT", 0.30, (0.75, 0.50, 0.28)),
        ("BILLS", 0.35, (0.75, 0.55, 0.28)),
        ("LEFT", 0.15, (0.85, 0.70, 0.15)),
    ]
    n = len(bars)
    out = []
    for i, (label, h, col) in enumerate(bars):
        x = -(0.55 * (n - 1)) + i * 1.1
        out.append(rectangle_layer(x - 0.22, -1.2, x + 0.22, -1.2 + h, col, f"bar_{label}"))
        out.append(text_layer(label, x, -1.35, 0.11, (0.15, 0.15, 0.18), f"label_{label}"))
    return "\n".join(out)


def main(out_path: Path):
    bg = rectangle_layer(-4.5, -2.6, 4.5, 2.6, (0.96, 0.94, 0.90), "background")
    card = rectangle_layer(-3.6, -1.55, 3.6, 1.9, (1.0, 1.0, 1.0), "card")
    bars_xml = build_bars()
    john_xml = build_john(root_x=-2.6, root_y=-0.3)

    # Real bug found and fixed via a minimal 2-rectangle isolation test:
    # .sif layer order is PAINT order (first XML element painted first,
    # ends up at the BACK; LAST element painted last, ends up in FRONT)
    # -- the opposite of what a "layers panel, top = front" assumption
    # would suggest. Confirmed empirically: a red foreground rectangle
    # listed before a full-canvas background rectangle was completely
    # hidden until this order was reversed. So background goes FIRST,
    # John (frontmost) goes LAST.
    layers = "\n".join([bg, card, bars_xml, john_xml])

    end_frame = int(END_TIME_S * FPS)
    sif = f'''<?xml version="1.0"?>
<canvas version="1.2" width="1920" height="1080" xres="2834.645752" yres="2834.645752" gamma-r="1.0" gamma-g="1.0" gamma-b="1.0" view-box="-4.5 2.53125 4.5 -2.53125" antialias="1" fps="{FPS}.000" begin-time="0" end-time="{end_frame}" bgcolor="0.960000 0.940000 0.900000 1.000000">
  <name>K70 Vector John -- Synfig</name>
  <desc>Real Synfig-authored scene, generated programmatically against the .sif schema (no GUI).</desc>
{layers}
</canvas>
'''
    out_path.write_text(sif, encoding="utf-8")
    print(f"wrote {out_path} ({len(sif)} bytes)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
