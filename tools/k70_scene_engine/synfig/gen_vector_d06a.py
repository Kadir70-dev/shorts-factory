#!/usr/bin/env python3
"""Day 06 Short A -- credit card minimum-payment breakdown, real Synfig .sif
(portrait 1080x1920). Same primitive-layer pattern as gen_vector_john.py
(rectangle/circle/text layers, paint-order = XML order back->front), just
new content + a portrait canvas + a couple of amount-fade-in reveals for
pacing. gen_vector_john.py itself is left untouched.

    .venv-win/Scripts/python.exe tools/k70_scene_engine/synfig/gen_vector_d06a.py <out.sif>
"""
from __future__ import annotations

import sys
from pathlib import Path

FPS = 24
END_TIME_S = 13.0


def real(v): return f'<real value="{v:.6f}"/>'
def integer(v): return f'<integer value="{v}"/>'
def boolean(v): return f'<bool value="{"true" if v else "false"}"/>'
def vector(x, y): return f'<vector><x>{x:.6f}</x><y>{y:.6f}</y></vector>'
def color(r, g, b, a=1.0):
    return f'<color><r>{r:.6f}</r><g>{g:.6f}</g><b>{b:.6f}</b><a>{a:.6f}</a></color>'


def param(name, inner): return f'<param name="{name}">{inner}</param>'


def animated_real_waypoints(waypoints):
    wp_xml = "\n".join(
        f'<waypoint time="{t}" before="clamped" after="clamped"><real value="{v:.4f}"/></waypoint>'
        for t, v in waypoints)
    return f'<animated type="real">{wp_xml}</animated>'


def rectangle_layer(x1, y1, x2, y2, col, desc="", amount_waypoints=None):
    amount = animated_real_waypoints(amount_waypoints) if amount_waypoints else real(1)
    return f'''<layer type="rectangle" active="true" version="0.1" desc="{desc}">
    {param("z_depth", real(0))}
    {param("amount", amount)}
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


def text_layer(text, cx, cy, size, col, desc="", amount_waypoints=None):
    text_esc = text.replace("&", "&amp;").replace("<", "&lt;")
    amount = animated_real_waypoints(amount_waypoints) if amount_waypoints else real(1)
    return f'''<layer type="text" active="true" version="0.1" desc="{desc}">
    {param("z_depth", real(0))}
    {param("amount", amount)}
    {param("blend_method", integer(0))}
    {param("text", f"<string>{text_esc}</string>")}
    {param("color", color(*col))}
    {param("size", vector(size, size))}
    {param("origin", vector(cx, cy))}
    {param("orient", vector(0.5, 0.5))}
    {param("invert", boolean(False))}
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


def build_scene():
    # Portrait world units: x in [-2.53125, 2.53125], y in [-4.5, 4.5]
    # (top of frame = +y, matching gen_vector_john.py's y-up convention).
    layers = []

    # background + "bill" card
    layers.append(rectangle_layer(-2.53125, -4.5, 2.53125, 4.5, (0.96, 0.94, 0.90), "background"))
    layers.append(rectangle_layer(-2.1, 2.2, 2.1, 4.0, (1.0, 1.0, 1.0), "card_top"))

    # header: "YOUR STATEMENT" + big balance figure, present from the start
    layers.append(text_layer("YOUR STATEMENT", 0, 3.65, 0.14, (0.35, 0.35, 0.38), "hdr"))
    layers.append(text_layer("BALANCE", 0, 3.2, 0.13, (0.35, 0.35, 0.38), "balance_lbl"))
    layers.append(text_layer("$5,000", 0, 2.65, 0.42, (0.12, 0.12, 0.15), "balance_amt"))

    # minimum-payment line, fades in ~2s in
    min_fade = [("0s 0f", 0.0), ("2s 0f", 0.0), ("2s 12f", 1.0)]
    layers.append(rectangle_layer(-2.1, 1.4, 2.1, 1.95, (0.90, 0.87, 0.80), "min_row_bg", amount_waypoints=min_fade))
    layers.append(text_layer("MINIMUM PAYMENT (2%)", -0.05, 1.78, 0.115, (0.35, 0.35, 0.38), "min_lbl", amount_waypoints=min_fade))
    layers.append(text_layer("$100", 1.5, 1.62, 0.22, (0.12, 0.12, 0.15), "min_amt", amount_waypoints=min_fade))

    # APR disclosure caption, fades in ~4.5s in
    apr_fade = [("0s 0f", 0.0), ("4s 12f", 0.0), ("5s 0f", 1.0)]
    layers.append(text_layer("at a hypothetical 22% APR", 0, 1.15, 0.10, (0.45, 0.45, 0.48), "apr_note", amount_waypoints=apr_fade))

    # split breakdown bars: interest (red, big) vs to-balance (green, small),
    # fade/scale in sequentially so the point ("most of it is interest")
    # reads as a reveal, not a static wall of numbers.
    split_fade = [("0s 0f", 0.0), ("6s 0f", 0.0), ("6s 15f", 1.0)]
    layers.append(text_layer("OF THAT $100 EACH MONTH:", 0, 0.35, 0.115, (0.30, 0.30, 0.34), "split_hdr", amount_waypoints=split_fade))

    interest_fade = [("0s 0f", 0.0), ("7s 0f", 0.0), ("7s 15f", 1.0)]
    layers.append(rectangle_layer(-2.0, -0.55, 1.55, -0.15, (0.75, 0.28, 0.26), "interest_bar", amount_waypoints=interest_fade))
    layers.append(text_layer("~$92 -> INTEREST", -0.2, -0.35, 0.115, (1.0, 1.0, 1.0), "interest_lbl", amount_waypoints=interest_fade))

    principal_fade = [("0s 0f", 0.0), ("8s 12f", 0.0), ("9s 3f", 1.0)]
    layers.append(rectangle_layer(-2.0, -1.0, -1.55, -0.62, (0.22, 0.55, 0.32), "principal_bar", amount_waypoints=principal_fade))
    layers.append(text_layer("~$8 -> reduces balance", 0.05, -0.8, 0.10, (0.30, 0.30, 0.34), "principal_lbl", amount_waypoints=principal_fade))

    # closing emphasis line, last third of the clip
    close_fade = [("0s 0f", 0.0), ("10s 0f", 0.0), ("10s 15f", 1.0)]
    layers.append(text_layer("Barely touches\nwhat you owe.", 0, -2.1, 0.20, (0.12, 0.12, 0.15), "close_line", amount_waypoints=close_fade))

    return "\n".join(layers)


def main(out_path: Path):
    layers_xml = build_scene()
    end_frame = int(END_TIME_S * FPS)
    sif = f'''<?xml version="1.0"?>
<canvas version="1.2" width="1080" height="1920" xres="2834.645752" yres="2834.645752" gamma-r="1.0" gamma-g="1.0" gamma-b="1.0" view-box="-2.53125 4.5 2.53125 -4.5" antialias="1" fps="{FPS}.000" begin-time="0" end-time="{end_frame}" bgcolor="0.960000 0.940000 0.900000 1.000000">
  <name>K70 D06 Short A -- Credit Card Minimum Breakdown (Synfig)</name>
  <desc>Real Synfig-authored scene, portrait canvas, no GUI.</desc>
{layers_xml}
</canvas>
'''
    out_path.write_text(sif, encoding="utf-8")
    print(f"wrote {out_path} ({len(sif)} bytes)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
