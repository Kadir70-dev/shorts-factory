"""The visual ladder, the chart engine and the brand system.

The behaviour under test is the brief's central visual rule: numbers get real
charts, specific subjects get specific footage, and generic stock is a rescue
rather than a default. Several assertions are deliberately about what does NOT
happen — the old pipeline's failure was reaching for stock too eagerly, and that
is invisible unless you assert against it.
"""
from __future__ import annotations

import asyncio

import pytest

from app.brand import load_theme
from app.brand import overlays as ov
from app.brand import text as tx
from app.pipeline import dataviz, scene_director as sd
from app.schemas.scene import DataPoint, DataViz, Overlay, Scene
from app.schemas.video_spec import Niche, VideoSpec


@pytest.fixture
def spec():
    return VideoSpec(channel_id="k70_business", niche=Niche.business,
                     topic="test", allow_ai_image=False)


# --------------------------------------------------------------------------- #
# Number handling — the engine must never invent data
# --------------------------------------------------------------------------- #
def test_a_beat_with_no_figure_gets_no_chart():
    s = Scene(id="s1", narration="The hot dog was never really the product.")
    assert dataviz.from_scene(s) is None, (
        "a chart with invented numbers is worse than no chart")


def test_a_stat_overlay_is_promoted_to_a_chart():
    s = Scene(id="s1", narration="Renewal rates stayed high.",
              overlays=[Overlay(type="stat", text="of members renew", sub="92%"),
                        Overlay(type="source", text="Costco 10-K")])
    viz = dataviz.from_scene(s)
    assert viz is not None
    assert viz.points[0].value == pytest.approx(92.0)
    assert viz.suffix == "%"
    assert viz.source == "Costco 10-K", "the attribution must travel with the chart"


def test_authored_data_is_preferred_over_the_overlay():
    authored = DataViz(kind="line_trend", title="CPI",
                       points=[DataPoint(label=str(2020 + i), value=v)
                               for i, v in enumerate([1.4, 4.7, 8.0, 4.1])],
                       suffix="%")
    s = Scene(id="s1", narration="CPI moved.", data=authored,
              overlays=[Overlay(type="stat", text="peak", sub="8%")])
    assert dataviz.from_scene(s) is authored


@pytest.mark.parametrize("text,expected", [
    ("$4.2 billion", 4.2e9), ("3.4%", 3.4), ("$1.50", 1.5),
    ("1,240", 1240.0), ("25 bps", 25.0),
])
def test_number_parsing(text, expected):
    parsed = dataviz.parse_number(text)
    assert parsed is not None
    assert parsed[0] == pytest.approx(expected)


def test_number_parsing_rejects_prose():
    assert dataviz.parse_number("no digits here") is None


@pytest.mark.parametrize("value,kw,expected", [
    (1.5, {"prefix": "$", "decimals": 2, "abbreviate": False}, "$1.50"),
    (37.0, {"suffix": "%", "decimals": 0, "abbreviate": False}, "37%"),
    (4.2e9, {"prefix": "$", "decimals": 1}, "$4.2B"),
    (274600, {"prefix": "$", "decimals": 0}, "$274.6K"),
])
def test_value_formatting(value, kw, expected):
    viz = DataViz(points=[DataPoint(label="x", value=value)], **kw)
    assert dataviz.format_value(value, viz) == expected


def test_axis_range_anchors_at_zero_for_positive_series():
    """A truncated y-axis makes a small move look like a cliff. On a finance
    channel that is a misleading graphic, not a styling choice."""
    lo, _ = dataviz._y_range([100.0, 102.0, 104.0])
    assert lo <= 0.0


def test_invalid_data_is_refused():
    viz = DataViz(kind="bar_compare", points=[])
    assert not viz.valid()
    theme = load_theme("k70")
    with pytest.raises(ValueError, match="no real data"):
        asyncio.run(dataviz.render(viz, theme, __import__("pathlib").Path("/tmp/x.mp4"),
                                   1080, 1920, 30, 3.0))


# --------------------------------------------------------------------------- #
# The ladder
# --------------------------------------------------------------------------- #
def _graph_of(scenes):
    from app.schemas.scene import SceneGraph, SceneMeta
    return SceneGraph(
        meta=SceneMeta(video_id="v", channel_id="c", niche="usa_business",
                       title="t", hook="h"),
        scenes=scenes)


def test_every_authored_figure_becomes_a_chart(spec):
    """The brief's most explicit instruction. Capping this would silently drop a
    chart the Director asked for and substitute footage."""
    scenes = []
    for i in range(4):
        scenes.append(Scene(
            id=f"s{i}", narration=f"Revenue grew in year {i}.",
            data=DataViz(kind="counter", title=f"Metric {i}",
                         points=[DataPoint(label="x", value=10.0 + i)],
                         source="10-K")))
    graph = _graph_of(scenes)
    report = sd.decide(graph, spec)
    assert report.counts[sd.DATAVIZ] == 4
    assert all(s.visual.type == "dataviz" for s in graph.scenes)


def test_a_specific_subject_gets_subject_specific_footage(spec):
    s = Scene(id="s1",
              narration="Brazil lifted the World Cup trophy in Mexico in 1970.")
    s.visual.broll_keywords = ["brazil 1970 world cup final",
                               "pele trophy celebration"]
    graph = _graph_of([s, Scene(id="s2", narration="Follow for more.")])
    sd.decide(graph, spec)
    assert graph.scenes[0].visual.strategy in (sd.REAL, sd.HYBRID, sd.AI_IMAGE)
    assert "specific subject" in graph.scenes[0].visual.decision_reason


def test_generic_keywords_do_not_count_as_a_subject(spec):
    """Vague keywords are the signal that there is nothing to film. Treating them
    as a subject is exactly how every upload ended up with the same stock."""
    s = Scene(id="s1", narration="Companies must adapt to survive competition.")
    s.visual.broll_keywords = ["business meeting", "corporate handshake",
                               "financial growth"]
    graph = _graph_of([s, Scene(id="s2", narration="Follow for more.")])
    sd.decide(graph, spec)
    assert graph.scenes[0].visual.strategy != sd.REAL


def test_a_wordy_beat_becomes_motion_graphics_not_stock(spec):
    s = Scene(id="s1", narration="The hot dog was never really the product.",
              beat_role="mechanism",
              overlays=[Overlay(type="headline",
                                text="The hot dog was never the product")])
    graph = _graph_of([s, Scene(id="s2", narration="Follow for more.")])
    sd.decide(graph, spec)
    assert graph.scenes[0].visual.strategy == sd.MOTION_GFX
    assert graph.scenes[0].visual.type == "motion_gfx"


def test_a_branded_plate_is_a_genuine_last_resort(spec):
    """Only a beat with nothing to film AND nothing worth setting in type should
    land on a plate; a run of plates would be worse than the stock it replaced."""
    scenes = [Scene(id=f"s{i}",
                    narration="It changed everything about how they operated "
                              "and continued to shape decisions for many years "
                              "afterwards across the entire industry worldwide.",
                    beat_role="context")
              for i in range(4)]
    graph = _graph_of(scenes)
    report = sd.decide(graph, spec)
    assert report.counts[sd.BRANDED] <= len(scenes)
    # and with a short, showable line they become graphics instead
    for s in graph.scenes:
        s.narration = "The mechanism was hidden in plain sight."
        s.visual.type = "broll"
        s.visual.strategy = "real"
    report = sd.decide(graph, spec)
    assert report.counts[sd.MOTION_GFX] >= 1
    assert report.counts[sd.BRANDED] == 0


def test_everyday_realism_still_vetoes_ai(spec):
    spec.allow_ai_image = True
    s = Scene(id="s1", narration="Shoppers at the grocery checkout felt it first.")
    s.visual.broll_keywords = ["grocery checkout usa", "worried shoppers 2024"]
    graph = _graph_of([s, Scene(id="s2", narration="Follow for more.")])
    sd.decide(graph, spec)
    assert graph.scenes[0].visual.strategy != sd.AI_IMAGE, (
        "generated grocery aisles look uncanny; this is what stock is good at")


def test_decisions_explain_themselves(spec, graph):
    sd.decide(graph, spec)
    for s in graph.scenes:
        assert s.visual.decision_reason, f"{s.id} has no rationale"


# --------------------------------------------------------------------------- #
# Brand
# --------------------------------------------------------------------------- #
def test_theme_resolves_real_font_files():
    theme = load_theme("k70")
    for face in (theme.display, theme.body, theme.mono):
        assert face.path, "no font resolved; drawtext would fall back silently"
        assert face.path.endswith((".ttf", ".otf"))
        assert "[" not in face.path, (
            "a variable font renders its DEFAULT weight — asking for bold gets "
            "regular, silently")


def test_palette_conversions():
    theme = load_theme("k70")
    assert theme.ff("primary").startswith("0x")
    # ASS is byte-reversed with alpha first; getting this wrong swaps red and blue
    assert theme.ass("primary") == "&H0001B3F5"
    assert theme.rgb("primary") == (245, 179, 1)


@pytest.mark.parametrize("text", [
    "37%", "up 12% (2024)", "it's here", "US: the cost", "a,b split",
    "AT&T = big", "cost $1,240", "[tag] x;y", "100% of Wall St's bets",
])
def test_drawtext_escaping_survives_real_copy(text):
    """Every character here broke drawtext at some point. `%` was the worst: it
    blanked the ENTIRE draw while ffmpeg still reported success."""
    filt = tx.drawtext(text, font="/tmp/f.ttf", size=40, color="0xFFFFFF",
                       x="0", y="0")
    assert "expansion=none" in filt, "without this a literal % blanks the text"
    assert "\\%" not in filt, "escaping % is what caused the blanking"
    assert "'" not in filt.split("text='")[1].split("':")[0].replace("’", "")


def test_caption_animations_all_produce_valid_ass(graph):
    theme = load_theme("k70")
    from app.pipeline import captions
    asyncio.run(captions.transcribe(graph))
    for anim in ov.CAPTION_ANIMATIONS:
        doc = ov.caption_ass(graph, theme, animation=anim)
        assert "[V4+ Styles]" in doc and "[Events]" in doc
        assert doc.count("Dialogue:") == len(graph.captions)
        assert theme.body.name in doc


def test_caption_mute_windows_yield_the_frame(graph):
    theme = load_theme("k70")
    from app.pipeline import captions
    asyncio.run(captions.transcribe(graph))
    full = ov.caption_ass(graph, theme).count("Dialogue:")
    muted = ov.caption_ass(graph, theme,
                           mute_windows=[(0.0, 999.0)]).count("Dialogue:")
    assert muted == 0 < full


def test_word_wrap_never_overflows():
    long = "A very long headline that would certainly overflow a vertical frame " \
           "if nothing wrapped it at all"
    lines = tx.wrap(long, 76, 1080, max_lines=3)
    assert len(lines) <= 3
    assert lines[-1].endswith("…") or len(lines) < 3
