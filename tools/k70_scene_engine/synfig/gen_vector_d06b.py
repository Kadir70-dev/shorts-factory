#!/usr/bin/env python3
"""Day 06 Short B -- time value of money explainer, real Synfig .sif
(portrait 1080x1920). Same primitive-layer pattern as gen_vector_john.py /
gen_vector_d06a.py.

    .venv-win/Scripts/python.exe tools/k70_scene_engine/synfig/gen_vector_d06b.py <out.sif>
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


def build_scene():
    layers = []
    layers.append(rectangle_layer(-2.53125, -4.5, 2.53125, 4.5, (0.96, 0.94, 0.90), "background"))
    layers.append(rectangle_layer(-2.1, 2.6, 2.1, 4.0, (1.0, 1.0, 1.0), "card_top"))

    layers.append(text_layer("TODAY", 0, 3.65, 0.14, (0.35, 0.35, 0.38), "hdr"))
    layers.append(text_layer("$100", 0, 3.05, 0.42, (0.12, 0.12, 0.15), "amt"))

    # three reveal rows, staggered fade-ins
    row1 = [("0s 0f", 0.0), ("1s 12f", 0.0), ("2s 6f", 1.0)]
    layers.append(rectangle_layer(-2.1, 1.55, 2.1, 2.05, (0.90, 0.87, 0.80), "row1_bg", amount_waypoints=row1))
    layers.append(text_layer("-> CAN EARN INTEREST", 0, 1.8, 0.14, (0.16, 0.16, 0.19), "row1", amount_waypoints=row1))

    row2 = [("0s 0f", 0.0), ("3s 6f", 0.0), ("4s 0f", 1.0)]
    layers.append(rectangle_layer(-2.1, 1.0, 2.1, 1.5, (0.90, 0.87, 0.80), "row2_bg", amount_waypoints=row2))
    layers.append(text_layer("-> CAN BE INVESTED", 0, 1.25, 0.14, (0.16, 0.16, 0.19), "row2", amount_waypoints=row2))

    row3 = [("0s 0f", 0.0), ("4s 18f", 0.0), ("5s 12f", 1.0)]
    layers.append(rectangle_layer(-2.1, 0.45, 2.1, 0.95, (0.90, 0.87, 0.80), "row3_bg", amount_waypoints=row3))
    layers.append(text_layer("-> STARTS GROWING NOW", 0, 0.7, 0.14, (0.16, 0.16, 0.19), "row3", amount_waypoints=row3))

    # inflation counter-note, lower half, appears later
    meanwhile = [("0s 0f", 0.0), ("7s 0f", 0.0), ("7s 20f", 1.0)]
    layers.append(text_layer("MEANWHILE:", 0, -0.55, 0.14, (0.35, 0.35, 0.38), "meanwhile_hdr", amount_waypoints=meanwhile))
    layers.append(rectangle_layer(-2.1, -1.9, 2.1, -1.15, (0.78, 0.30, 0.28), "inflation_bar", amount_waypoints=meanwhile))
    layers.append(text_layer("INFLATION quietly shrinks\nwhat future money can buy", 0, -1.5, 0.115, (1.0, 1.0, 1.0), "inflation_txt", amount_waypoints=meanwhile))

    close = [("0s 0f", 0.0), ("10s 0f", 0.0), ("10s 15f", 1.0)]
    layers.append(text_layer("Waiting has a real cost.", 0, -2.9, 0.19, (0.12, 0.12, 0.15), "close_line", amount_waypoints=close))

    return "\n".join(layers)


def main(out_path: Path):
    layers_xml = build_scene()
    end_frame = int(END_TIME_S * FPS)
    sif = f'''<?xml version="1.0"?>
<canvas version="1.2" width="1080" height="1920" xres="2834.645752" yres="2834.645752" gamma-r="1.0" gamma-g="1.0" gamma-b="1.0" view-box="-2.53125 4.5 2.53125 -4.5" antialias="1" fps="{FPS}.000" begin-time="0" end-time="{end_frame}" bgcolor="0.960000 0.940000 0.900000 1.000000">
  <name>K70 D06 Short B -- Time Value of Money (Synfig)</name>
  <desc>Real Synfig-authored scene, portrait canvas, no GUI.</desc>
{layers_xml}
</canvas>
'''
    out_path.write_text(sif, encoding="utf-8")
    print(f"wrote {out_path} ({len(sif)} bytes)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
