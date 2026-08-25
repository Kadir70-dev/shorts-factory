"""
Paper Craft — the declarative layout language templates compile to.

Templates (`templates.py`) never touch the `scribus` module directly — they
build a `PageLayout` of `Frame`s, and `scribus_engine.py` is the ONE place
that knows how to turn that into real Scribus scripting calls. This mirrors
`brand/text.py`'s role for ffmpeg drawtext: one compiler, many callers, so an
API-signature fix only has to happen once.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Align = Literal["left", "center", "right", "justify"]


@dataclass
class Frame:
    kind: Literal["text", "image", "rect", "line"]
    x: float
    y: float
    w: float
    h: float
    text: str = ""
    font: str = "Times New Roman Regular"
    size: float = 12.0
    align: Align = "left"
    color: str = "#000000"
    line_spacing: float | None = None      # points; None = font default
    tracking: float | None = None          # extra letter spacing, 1/1000 em
    upper: bool = False
    image_path: str = ""
    fill_color: str | None = None          # rect fill; None = no fill
    line_color: str | None = None          # rect/line stroke; None = no stroke
    line_width: float = 0.5
    rotation: float = 0.0
    name: str = ""                         # optional stable id for the frame


@dataclass
class PageLayout:
    """One page, in points (Scribus UNIT_POINTS), US Letter-ratio by default."""
    width: float = 612.0
    height: float = 792.0
    margins: tuple[float, float, float, float] = (36.0, 36.0, 36.0, 36.0)
    background: str = "#FFFFFF"
    frames: list[Frame] = field(default_factory=list)

    def add(self, frame: Frame) -> "PageLayout":
        self.frames.append(frame)
        return self


def columns(x: float, y: float, w: float, h: float, n: int, gutter: float
           ) -> list[tuple[float, float, float, float]]:
    """Split a region into `n` equal vertical columns — the one layout
    primitive every print-document template needs (newspapers, reports,
    dossiers all read as column grids, not single text blocks)."""
    col_w = (w - gutter * (n - 1)) / n
    return [(x + i * (col_w + gutter), y, col_w, h) for i in range(n)]
