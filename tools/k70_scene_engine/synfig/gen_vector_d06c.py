#!/usr/bin/env python3
"""Day 06 Short C -- bank funding-cost breakdown, real Synfig .sif
(portrait 1080x1920). Same primitive-layer pattern as gen_vector_john.py.

    .venv-win/Scripts/python.exe tools/k70_scene_engine/synfig/gen_vector_d06c.py <out.sif>
"""
from __future__ import annotations

import sys
from pathlib import Path

FPS = 24
END_TIME_S = 15.0


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
    layers.append(rectangle_layer(-2.53125, -4.5, 2.53125, 4.5, (0.13, 0.14, 0.17), "background"))

    layers.append(text_layer("A BANK'S BUSINESS", 0, 3.85, 0.16, (0.95, 0.95, 0.97), "hdr"))

    # EARNS row -- appears first
    earns = [("0s 0f", 0.0), ("0s 10f", 0.0), ("1s 0f", 1.0)]
    layers.append(rectangle_layer(-2.15, 2.95, 2.15, 3.55, (0.22, 0.55, 0.32), "earns_bg", amount_waypoints=earns))
    layers.append(text_layer("EARNS: interest on loans & securities", 0, 3.25, 0.105, (1.0, 1.0, 1.0), "earns_txt", amount_waypoints=earns))

    layers.append(text_layer("BUT IT ALSO:", 0, 2.35, 0.13, (0.75, 0.75, 0.78), "but_hdr", amount_waypoints=[("0s 0f", 0.0), ("2s 0f", 0.0), ("2s 15f", 1.0)]))

    rows = [
        ("PAYS interest to depositors", "2s 20f", "3s 15f"),
        ("COVERS operating costs", "4s 10f", "5s 5f"),
        ("ABSORBS credit losses on unpaid loans", "6s 0f", "6s 20f"),
        ("HOLDS capital & reserves (required)", "7s 15f", "8s 10f"),
    ]
    y0 = 1.75
    for i, (label, t_start, t_full) in enumerate(rows):
        y = y0 - i * 0.62
        wp = [("0s 0f", 0.0), (t_start, 0.0), (t_full, 1.0)]
        layers.append(rectangle_layer(-2.15, y - 0.24, 2.15, y + 0.24, (0.30, 0.24, 0.14), f"row{i}_bg", amount_waypoints=wp))
        layers.append(text_layer(label, 0, y, 0.10, (0.95, 0.85, 0.55), f"row{i}_txt", amount_waypoints=wp))

    close = [("0s 0f", 0.0), ("11s 0f", 0.0), ("11s 15f", 1.0)]
    layers.append(text_layer("Earn more than it pays --\nwhile managing the risk.", 0, -2.5, 0.16, (0.95, 0.95, 0.97), "close_line", amount_waypoints=close))

    return "\n".join(layers)


def main(out_path: Path):
    layers_xml = build_scene()
    end_frame = int(END_TIME_S * FPS)
    sif = f'''<?xml version="1.0"?>
<canvas version="1.2" width="1080" height="1920" xres="2834.645752" yres="2834.645752" gamma-r="1.0" gamma-g="1.0" gamma-b="1.0" view-box="-2.53125 4.5 2.53125 -4.5" antialias="1" fps="{FPS}.000" begin-time="0" end-time="{end_frame}" bgcolor="0.130000 0.140000 0.170000 1.000000">
  <name>K70 D06 Short C -- Bank Funding Costs (Synfig)</name>
  <desc>Real Synfig-authored scene, portrait canvas, no GUI.</desc>
{layers_xml}
</canvas>
'''
    out_path.write_text(sif, encoding="utf-8")
    print(f"wrote {out_path} ({len(sif)} bytes)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
