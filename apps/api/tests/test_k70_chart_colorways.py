"""Regression tests for opt-in K70 chart colorways.

The original k70.yaml remains the default, and finance-documentary palettes
must not be silently changed by the new Data Visualization colors.
"""
from __future__ import annotations

import re

import pytest

from app.brand.theme import load_theme
from app.pipeline.dataviz import _bar_category_color, _line_color, _point_color
from app.schemas.scene import DataPoint, DataViz


@pytest.mark.parametrize("colorway", ["aurora", "sunset", "ocean"])
def test_chart_colorway_has_safe_text_and_valid_palette(colorway: str) -> None:
    classic = load_theme("k70")
    theme = load_theme(f"k70_chart_{colorway}")
    assert theme.id == f"k70_chart_{colorway}"
    assert theme.fingerprint != classic.fingerprint
    assert theme.palette["bg"] != classic.palette["bg"]
    for role in ("bg", "bg_soft", "ink", "ink_dim", "primary", "secondary",
                 "positive", "negative", "warn", "grid", "shadow"):
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", theme.palette[role])
    colors = theme.chart["category_colors"]
    assert len(colors) == 6
    assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}", color) for color in colors)
    assert len(set(colors)) == len(colors)


@pytest.mark.parametrize("colorway", ["aurora", "sunset", "ocean"])
def test_comparison_bars_are_colored_without_faking_direction(colorway: str) -> None:
    theme = load_theme(f"k70_chart_{colorway}")
    p = DataPoint(label="Company A", value=100)
    colors = theme.chart["category_colors"]
    assert _bar_category_color(theme, p, 0, False, True) == theme.rgb(colors[0])
    assert _bar_category_color(theme, p, 1, False, False) == theme.rgb(colors[1])
    assert _bar_category_color(theme, p, 2, True, False) == theme.rgb("primary")
    negative = DataPoint(label="Loss", value=-5, emphasis="negative")
    assert _bar_category_color(theme, negative, 0, False, None) == theme.rgb("negative")


def test_classic_k70_still_uses_original_bar_colors() -> None:
    theme = load_theme("k70")
    p = DataPoint(label="A", value=10)
    assert not theme.chart.get("category_colors")
    for index in range(3):
        assert _bar_category_color(theme, p, index, False, True) == (
            _point_color(theme, p, False, True)
        )


def test_line_color_follows_highlight_emphasis_but_defaults_to_direction() -> None:
    theme = load_theme("k70_chart_aurora")
    auto = DataViz(kind="line_trend", points=[DataPoint(label="a", value=1), DataPoint(label="b", value=2)])
    assert _line_color(theme, auto) == theme.rgb("positive")          # unchanged default: rising = up
    falling = DataViz(kind="line_trend", points=[DataPoint(label="a", value=2), DataPoint(label="b", value=1)])
    assert _line_color(theme, falling) == theme.rgb("negative")
    cost = DataViz(kind="line_trend", points=[DataPoint(label="a", value=1), DataPoint(label="b", value=2, emphasis="negative")])
    assert _line_color(theme, cost) == theme.rgb("negative")          # rising prices are not green
    level = DataViz(kind="line_trend", highlight=0, points=[DataPoint(label="a", value=1, emphasis="primary"), DataPoint(label="b", value=2)])
    assert _line_color(theme, level) == theme.rgb("primary")
