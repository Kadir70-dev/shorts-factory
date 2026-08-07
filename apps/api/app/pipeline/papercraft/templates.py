"""
Paper Craft — the 11 document templates.

Each function is a pure `DocumentSpec -> PageLayout` transform: it decides
fonts, palette, grid and which spec fields land where, using the SAME
primitives (`Frame`, `columns()`) every other template uses. A template is a
configuration of that shared grid engine, not a bespoke renderer — this is
the same "one Canvas, six chart kinds" relationship `dataviz.py` already has
with `raster.py`, applied to documents.
"""
from __future__ import annotations

from .layout import Frame, PageLayout, columns
from .spec import DocumentSpec

PAGE_W, PAGE_H = 612.0, 792.0   # US Letter, points


def _wrap_body(text: str) -> str:
    return text.strip()


def _split_two(text: str) -> tuple[str, str]:
    """Divide body copy roughly in half by word count for a two-column read,
    without duplicating it into both frames. Scribus's real text-flow (linked
    frames) isn't wired up in `_runner.py` — this is a plain word-count split,
    good enough for a two-column newspaper block, not real justified flow."""
    words = text.split()
    if not words:
        return "", ""
    mid = (len(words) + 1) // 2
    return " ".join(words[:mid]), " ".join(words[mid:])


def _torn_edge(layout: PageLayout, x: float, y: float, w: float, *,
              teeth: int = 24, depth: float = 3.5, color: str = "#2a2a2a") -> None:
    """A deterministic sawtooth line standing in for a torn-paper edge: short
    alternating-diagonal `line` frames, the same primitive every other rule
    line in this module already uses — no new Scribus API needed for it."""
    step = w / teeth
    for i in range(teeth):
        dy = depth if i % 2 == 0 else -depth
        layout.add(Frame(kind="line", x=x + i * step, y=y, w=step, h=dy,
                         line_color=color, line_width=0.75))


def _byline(spec: DocumentSpec) -> str:
    date = spec.dates[0] if spec.dates else ""
    return " · ".join(p for p in (date, spec.language.upper() if spec.language != "en" else "") if p)


def _citation_footer(spec: DocumentSpec, layout: PageLayout, *,
                     font: str, size: float = 7.5, color: str = "#555555") -> None:
    if not spec.citations:
        return
    lines = "  •  ".join(c.label for c in spec.citations[:4])
    layout.add(Frame(
        kind="text", x=layout.margins[0], y=layout.height - layout.margins[3] - 16,
        w=layout.width - layout.margins[0] - layout.margins[1], h=16,
        text=lines, font=font, size=size, color=color, align="center",
    ))


def _editorial_mark(spec: DocumentSpec, layout: PageLayout, *, font: str) -> None:
    """Small, always-present, never-omitted disclosure corner mark for any
    recreated document — separate from the (optional) big stamp templates
    add for dramatic effect, this one is the quiet always-on safety net."""
    if not spec.editorial_reconstruction:
        return
    layout.add(Frame(
        kind="text", x=layout.width - layout.margins[1] - 160, y=layout.height - 14,
        w=160, h=12, text="EDITORIAL RECREATION", font=font, size=6.0,
        color="#999999", align="right",
    ))


# --------------------------------------------------------------------------- #
def modern_newspaper(spec: DocumentSpec) -> PageLayout:
    layout = PageLayout(PAGE_W, PAGE_H, (34, 34, 34, 40), background="#FBFAF6")
    m = layout.margins
    layout.add(Frame(kind="text", x=m[0], y=m[2], w=layout.width - m[0] - m[1], h=50,
                     text=spec.title, font="Georgia Bold", size=34, align="center",
                     color="#111111", upper=True, name="masthead"))
    layout.add(Frame(kind="line", x=m[0], y=m[2] + 54, w=layout.width - m[0] - m[1], h=0,
                     line_color="#111111", line_width=2.0))
    layout.add(Frame(kind="text", x=m[0], y=m[2] + 60, w=layout.width - m[0] - m[1], h=14,
                     text=_byline(spec) or "LATEST EDITION", font="Arial Regular",
                     size=8, align="center", color="#555555"))
    y0 = m[2] + 84
    layout.add(Frame(kind="text", x=m[0], y=y0, w=layout.width - m[0] - m[1], h=64,
                     text=spec.subtitle or spec.title, font="Georgia Bold", size=20,
                     align="left", color="#1a1a1a", line_spacing=23))
    body_y = y0 + 74
    body_h = layout.height - m[3] - body_y - (18 if spec.citations else 0)
    cols = columns(m[0], body_y, layout.width - m[0] - m[1], body_h, 3, 14)
    body = _wrap_body(spec.body) or "\n\n".join(f.text for f in spec.facts)
    for i, (cx, cy, cw, ch) in enumerate(cols):
        chunk = body if i == 0 else ("\n\n".join(q.text for q in spec.quotes) if i == 1 else
                                     "\n".join(f"{s.label}: {s.value}" for s in spec.statistics))
        layout.add(Frame(kind="text", x=cx, y=cy, w=cw, h=ch, text=chunk,
                         font="Times New Roman Regular", size=10, align="justify",
                         color="#1a1a1a", line_spacing=13, name=f"col{i}"))
    _citation_footer(spec, layout, font="Arial Regular")
    _editorial_mark(spec, layout, font="Arial Regular")
    return layout


def vintage_newspaper(spec: DocumentSpec) -> PageLayout:
    layout = PageLayout(PAGE_W, PAGE_H, (30, 30, 30, 36), background="#EFE6D0")
    m = layout.margins
    layout.add(Frame(kind="rect", x=m[0] - 8, y=m[2] - 8,
                     w=layout.width - m[0] - m[1] + 16, h=layout.height - m[2] - m[3] + 16,
                     line_color="#2a2418", line_width=1.5))
    # Blackletter headline runs long at this width — budget 2 lines' worth of
    # frame height with explicit line_spacing, or a wrapped second line
    # overlaps the first instead of stacking under it (Scribus doesn't grow a
    # frame or shrink text to fit on its own).
    layout.add(Frame(kind="text", x=m[0], y=m[2] + 4, w=layout.width - m[0] - m[1], h=88,
                     text=spec.title, font="Old English Text MT Regular", size=32,
                     align="center", color="#1c1811", line_spacing=34))
    layout.add(Frame(kind="line", x=m[0], y=m[2] + 94, w=layout.width - m[0] - m[1], h=0,
                     line_color="#1c1811", line_width=2.5))
    layout.add(Frame(kind="text", x=m[0], y=m[2] + 98, w=layout.width - m[0] - m[1], h=14,
                     text=(_byline(spec) or "SINGLE COPY").upper(), font="Garamond Regular",
                     size=8, align="center", color="#3a3225"))
    body_y = m[2] + 124
    body_h = layout.height - m[3] - body_y - (16 if spec.citations else 0)
    cols = columns(m[0], body_y, layout.width - m[0] - m[1], body_h, 4, 10)
    body = _wrap_body(spec.body) or "\n\n".join(f.text for f in spec.facts)
    left, right = _split_two(body)
    quotes = "\n\n".join(q.text for q in spec.quotes)
    col_text = [left, right, quotes, ""]
    for i, (cx, cy, cw, ch) in enumerate(cols):
        layout.add(Frame(kind="text", x=cx, y=cy, w=cw, h=ch,
                         text=col_text[i],
                         font="Times New Roman Regular", size=9, align="justify",
                         color="#1c1811", line_spacing=11, name=f"col{i}"))
    _citation_footer(spec, layout, font="Garamond Regular", color="#4a4030")
    _editorial_mark(spec, layout, font="Garamond Regular")
    return layout


def research_paper(spec: DocumentSpec) -> PageLayout:
    layout = PageLayout(PAGE_W, PAGE_H, (72, 72, 72, 72), background="#FFFFFF")
    m = layout.margins
    layout.add(Frame(kind="text", x=m[0], y=m[2], w=layout.width - m[0] - m[1], h=48,
                     text=spec.title, font="Cambria Bold", size=16, align="center",
                     color="#000000", line_spacing=19))
    layout.add(Frame(kind="text", x=m[0], y=m[2] + 52, w=layout.width - m[0] - m[1], h=14,
                     text=spec.subtitle or _byline(spec), font="Times New Roman Italic",
                     size=10, align="center", color="#333333"))
    y = m[2] + 78
    if spec.body:
        layout.add(Frame(kind="text", x=m[0], y=y, w=layout.width - m[0] - m[1], h=70,
                         text="Abstract — " + spec.body[:420], font="Times New Roman Italic",
                         size=9, align="justify", color="#111111", line_spacing=12))
        y += 84
    body_h = layout.height - m[3] - y - (60 if spec.citations else 0)
    layout.add(Frame(kind="text", x=m[0], y=y, w=layout.width - m[0] - m[1], h=body_h,
                     text="\n\n".join([f.text for f in spec.facts] +
                                      [f"{s.label}: {s.value}" for s in spec.statistics]),
                     font="Times New Roman Regular", size=10.5, align="justify",
                     color="#111111", line_spacing=15))
    if spec.citations:
        refs = "\n".join(f"[{i + 1}] {c.label}" for i, c in enumerate(spec.citations))
        layout.add(Frame(kind="text", x=m[0], y=layout.height - m[3] - 52,
                         w=layout.width - m[0] - m[1], h=52, text="References\n" + refs,
                         font="Times New Roman Regular", size=8, align="left",
                         color="#222222", line_spacing=10))
    _editorial_mark(spec, layout, font="Times New Roman Regular")
    return layout


def archive_dossier(spec: DocumentSpec) -> PageLayout:
    layout = PageLayout(PAGE_W, PAGE_H, (40, 40, 44, 40), background="#F2EFE6")
    m = layout.margins
    layout.add(Frame(kind="rect", x=m[0], y=m[2], w=layout.width - m[0] - m[1], h=26,
                     fill_color="#1a1a1a"))
    layout.add(Frame(kind="text", x=m[0] + 8, y=m[2] + 5, w=layout.width - m[0] - m[1] - 16,
                     h=18, text="ARCHIVE FILE", font="Courier New Bold", size=13,
                     align="left", color="#F2EFE6"))
    layout.add(Frame(kind="text", x=m[0] + 8, y=m[2] + 5, w=layout.width - m[0] - m[1] - 16,
                     h=18, text=(spec.dates[0] if spec.dates else ""), font="Courier New Bold",
                     size=11, align="right", color="#F2EFE6"))
    layout.add(Frame(kind="text", x=m[0], y=m[2] + 40, w=layout.width - m[0] - m[1], h=44,
                     text=spec.title, font="Courier New Bold", size=20, align="left",
                     color="#1a1a1a"))
    y = m[2] + 92
    layout.add(Frame(kind="text", x=m[0], y=y, w=layout.width - m[0] - m[1], h=260,
                     text=_wrap_body(spec.body) or "\n".join(f.text for f in spec.facts),
                     font="Courier New Regular", size=10, align="left", color="#1a1a1a",
                     line_spacing=15))
    y += 280
    for s in spec.statistics[:6]:
        layout.add(Frame(kind="text", x=m[0], y=y, w=200, h=14,
                         text=f"{s.label}:", font="Courier New Bold", size=9,
                         color="#1a1a1a"))
        layout.add(Frame(kind="text", x=m[0] + 200, y=y, w=180, h=14,
                         text=s.value, font="Courier New Regular", size=9,
                         color="#1a1a1a"))
        y += 16
    _citation_footer(spec, layout, font="Courier New Regular", color="#555555")
    _editorial_mark(spec, layout, font="Courier New Regular")
    return layout


def financial_report(spec: DocumentSpec) -> PageLayout:
    layout = PageLayout(PAGE_W, PAGE_H, (44, 44, 40, 40), background="#FFFFFF")
    m = layout.margins
    layout.add(Frame(kind="rect", x=0, y=0, w=layout.width, h=64, fill_color="#0E2A47"))
    layout.add(Frame(kind="text", x=m[0], y=18, w=layout.width - m[0] - m[1], h=30,
                     text=spec.title, font="Cambria Bold", size=20, align="left",
                     color="#FFFFFF"))
    layout.add(Frame(kind="text", x=m[0], y=70, w=layout.width - m[0] - m[1], h=16,
                     text=spec.subtitle or _byline(spec), font="Arial Regular", size=9,
                     align="left", color="#555555"))
    y = 96
    for s in spec.statistics[:5]:
        layout.add(Frame(kind="rect", x=m[0], y=y, w=layout.width - m[0] - m[1], h=30,
                         fill_color="#F0F3F7"))
        layout.add(Frame(kind="text", x=m[0] + 10, y=y + 6, w=300, h=18,
                         text=s.label, font="Arial Regular", size=10, color="#333333"))
        layout.add(Frame(kind="text", x=layout.width - m[1] - 150, y=y + 4, w=140, h=20,
                         text=s.value, font="Cambria Bold", size=13, align="right",
                         color="#0E2A47"))
        y += 36
    y += 10
    layout.add(Frame(kind="text", x=m[0], y=y, w=layout.width - m[0] - m[1],
                     h=layout.height - m[3] - y - (16 if spec.citations else 0),
                     text=_wrap_body(spec.body) or "\n\n".join(f.text for f in spec.facts),
                     font="Times New Roman Regular", size=10, align="justify",
                     color="#1a1a1a", line_spacing=14))
    _citation_footer(spec, layout, font="Arial Regular")
    _editorial_mark(spec, layout, font="Arial Regular")
    return layout


def magazine_feature(spec: DocumentSpec) -> PageLayout:
    layout = PageLayout(PAGE_W, PAGE_H, (30, 30, 34, 36), background="#FFFFFF")
    m = layout.margins
    y = m[2]
    if spec.images:
        layout.add(Frame(kind="image", x=m[0], y=y, w=layout.width - m[0] - m[1], h=220,
                         image_path=spec.images[0].path, name="hero"))
        y += 232
    # Same class of bug as breaking_news's banner label: a frame too short for
    # a wrapped 2-line title doesn't clip visibly, Scribus drops the overflow
    # line from the export outright. h=60 only fit ~1.9 lines at
    # line_spacing=31; budget a full 2 lines plus a little headroom.
    layout.add(Frame(kind="text", x=m[0], y=y, w=layout.width - m[0] - m[1], h=76,
                     text=spec.title, font="Georgia Bold", size=28, align="left",
                     color="#111111", line_spacing=31))
    y += 84
    if spec.subtitle:
        layout.add(Frame(kind="text", x=m[0], y=y, w=layout.width - m[0] - m[1], h=30,
                         text=spec.subtitle, font="Georgia Italic", size=13,
                         color="#444444", line_spacing=16))
        y += 38
    body_h = layout.height - m[3] - y - (16 if spec.citations else 0)
    cols = columns(m[0], y, layout.width - m[0] - m[1], body_h, 2, 18)
    body = _wrap_body(spec.body) or "\n\n".join(f.text for f in spec.facts)
    layout.add(Frame(kind="text", x=cols[0][0], y=cols[0][1], w=cols[0][2], h=cols[0][3],
                     text=body, font="Times New Roman Regular", size=10.5, align="justify",
                     color="#1a1a1a", line_spacing=14))
    quote = spec.quotes[0].text if spec.quotes else ""
    if quote:
        layout.add(Frame(kind="text", x=cols[1][0], y=cols[1][1] + 20, w=cols[1][2], h=140,
                         text=f"“{quote}”", font="Georgia Italic", size=17,
                         align="left", color="#0E2A47", line_spacing=21))
        if spec.quotes[0].attribution:
            layout.add(Frame(kind="text", x=cols[1][0], y=cols[1][1] + 165, w=cols[1][2], h=16,
                             text="— " + spec.quotes[0].attribution, font="Georgia Regular",
                             size=10, color="#555555"))
    _citation_footer(spec, layout, font="Arial Regular")
    _editorial_mark(spec, layout, font="Arial Regular")
    return layout


def breaking_news(spec: DocumentSpec) -> PageLayout:
    layout = PageLayout(PAGE_W, PAGE_H, (28, 28, 30, 34), background="#FFFFFF")
    m = layout.margins
    layout.add(Frame(kind="rect", x=0, y=0, w=layout.width, h=46, fill_color="#B00E0E"))
    # h=26 was too tight for 20pt Arial Black — Scribus silently dropped the
    # text (not just an aging/finishing artifact: it's absent from the raw PDF
    # export too), rather than clipping or shrinking it. Give it real headroom.
    layout.add(Frame(kind="text", x=m[0], y=8, w=layout.width - m[0] - m[1], h=32,
                     text="BREAKING NEWS", font="Arial Black", size=20, align="left",
                     color="#FFFFFF"))
    layout.add(Frame(kind="text", x=m[0], y=58, w=layout.width - m[0] - m[1], h=90,
                     text=spec.title, font="Arial Black", size=32, align="left",
                     color="#111111", line_spacing=34))
    layout.add(Frame(kind="line", x=m[0], y=154, w=layout.width - m[0] - m[1], h=0,
                     line_color="#B00E0E", line_width=3.0))
    layout.add(Frame(kind="text", x=m[0], y=162, w=layout.width - m[0] - m[1], h=14,
                     text=_byline(spec) or "DEVELOPING STORY", font="Arial Bold", size=9,
                     color="#B00E0E"))
    y = 184
    body_h = layout.height - m[3] - y - (16 if spec.citations else 0)
    layout.add(Frame(kind="text", x=m[0], y=y, w=layout.width - m[0] - m[1], h=body_h,
                     text=_wrap_body(spec.body) or "\n\n".join(f.text for f in spec.facts),
                     font="Arial Regular", size=11.5, align="left", color="#1a1a1a",
                     line_spacing=15))
    _citation_footer(spec, layout, font="Arial Regular")
    _editorial_mark(spec, layout, font="Arial Regular")
    return layout


def evidence_board(spec: DocumentSpec) -> PageLayout:
    layout = PageLayout(PAGE_W, PAGE_H, (36, 36, 40, 40), background="#E9E3D3")
    m = layout.margins
    layout.add(Frame(kind="rect", x=m[0], y=m[2], w=layout.width - m[0] - m[1], h=24,
                     fill_color="#7A1414"))
    layout.add(Frame(kind="text", x=m[0] + 8, y=m[2] + 4, w=300, h=18,
                     text="EVIDENCE", font="Courier New Bold", size=13, color="#F2EFE6"))
    layout.add(Frame(kind="text", x=m[0], y=m[2] + 34, w=layout.width - m[0] - m[1], h=36,
                     text=spec.title, font="Courier New Bold", size=18, color="#1a1a1a"))
    y = m[2] + 78
    for i, f in enumerate(spec.facts[:6]):
        layout.add(Frame(kind="text", x=m[0], y=y, w=layout.width - m[0] - m[1], h=16,
                         text=f"{i + 1}. {f.text}", font="Courier New Regular", size=9.5,
                         color="#1a1a1a"))
        y += 18
    y += 8
    layout.add(Frame(kind="text", x=m[0], y=y, w=layout.width - m[0] - m[1],
                     h=layout.height - m[3] - y - (16 if spec.citations else 0),
                     text=_wrap_body(spec.body), font="Courier New Regular", size=9.5,
                     color="#1a1a1a", line_spacing=14))
    _citation_footer(spec, layout, font="Courier New Regular", color="#555555")
    _editorial_mark(spec, layout, font="Courier New Regular")
    return layout


def company_memo(spec: DocumentSpec) -> PageLayout:
    layout = PageLayout(PAGE_W, PAGE_H, (60, 60, 60, 60), background="#FFFFFF")
    m = layout.margins
    layout.add(Frame(kind="text", x=m[0], y=m[2], w=layout.width - m[0] - m[1], h=26,
                     text="MEMORANDUM", font="Arial Bold", size=16, align="left",
                     color="#111111"))
    layout.add(Frame(kind="line", x=m[0], y=m[2] + 28, w=layout.width - m[0] - m[1], h=0,
                     line_color="#111111", line_width=1.0))
    fields_y = m[2] + 38
    labels = [("RE:", spec.title), ("DATE:", spec.dates[0] if spec.dates else ""),
              ("FROM:", spec.subtitle or "")]
    for label, value in labels:
        layout.add(Frame(kind="text", x=m[0], y=fields_y, w=60, h=14, text=label,
                         font="Arial Bold", size=9, color="#111111"))
        layout.add(Frame(kind="text", x=m[0] + 64, y=fields_y, w=layout.width - m[0] - m[1] - 64,
                         h=14, text=value, font="Arial Regular", size=9, color="#1a1a1a"))
        fields_y += 16
    y = fields_y + 12
    layout.add(Frame(kind="line", x=m[0], y=y, w=layout.width - m[0] - m[1], h=0,
                     line_color="#cccccc", line_width=0.75))
    y += 14
    layout.add(Frame(kind="text", x=m[0], y=y, w=layout.width - m[0] - m[1],
                     h=layout.height - m[3] - y - (16 if spec.citations else 0),
                     text=_wrap_body(spec.body) or "\n\n".join(f.text for f in spec.facts),
                     font="Times New Roman Regular", size=10.5, align="left",
                     color="#1a1a1a", line_spacing=15))
    _citation_footer(spec, layout, font="Arial Regular")
    _editorial_mark(spec, layout, font="Arial Regular")
    return layout


def historical_document(spec: DocumentSpec) -> PageLayout:
    layout = PageLayout(PAGE_W, PAGE_H, (54, 54, 54, 54), background="#E4D6B0")
    m = layout.margins
    layout.add(Frame(kind="rect", x=m[0] - 10, y=m[2] - 10,
                     w=layout.width - m[0] - m[1] + 20, h=layout.height - m[2] - m[3] + 20,
                     line_color="#5a4a2a", line_width=2.0))
    layout.add(Frame(kind="text", x=m[0], y=m[2], w=layout.width - m[0] - m[1], h=50,
                     text=spec.title, font="Garamond Bold", size=26, align="center",
                     color="#3a2f18"))
    if spec.dates:
        layout.add(Frame(kind="text", x=m[0], y=m[2] + 52, w=layout.width - m[0] - m[1], h=16,
                         text=spec.dates[0], font="Garamond Italic", size=11, align="center",
                         color="#5a4a2a"))
    y = m[2] + 84
    layout.add(Frame(kind="text", x=m[0] + 12, y=y, w=layout.width - m[0] - m[1] - 24,
                     h=layout.height - m[3] - y - (18 if spec.citations else 0) - 12,
                     text=_wrap_body(spec.body) or "\n\n".join(f.text for f in spec.facts),
                     font="Garamond Regular", size=12, align="justify", color="#2e2510",
                     line_spacing=17))
    _citation_footer(spec, layout, font="Garamond Regular", color="#5a4a2a")
    _editorial_mark(spec, layout, font="Garamond Regular")
    return layout


def news_clipping(spec: DocumentSpec) -> PageLayout:
    """A short, single-column clipped snippet — deliberately smaller and
    plainer than the front-page templates: a torn-edge strip for beats that
    want a quoted excerpt pasted onto the frame, not a whole newspaper page."""
    layout = PageLayout(PAGE_W, PAGE_H, (46, 46, 60, 60), background="#D8D2BE")
    m = layout.margins
    clip_x, clip_w = m[0], layout.width - m[0] - m[1]
    clip_y0, clip_y1 = m[2], layout.height - m[3]
    layout.add(Frame(kind="rect", x=clip_x, y=clip_y0, w=clip_w, h=clip_y1 - clip_y0,
                     fill_color="#F7F3E7"))
    _torn_edge(layout, clip_x, clip_y0, clip_w)
    _torn_edge(layout, clip_x, clip_y1, clip_w)
    layout.add(Frame(kind="text", x=clip_x + 20, y=clip_y0 + 18, w=clip_w - 40, h=14,
                     text=(_byline(spec) or "WIRE REPORT").upper(), font="Georgia Bold",
                     size=8, color="#7a6f52", tracking=60))
    layout.add(Frame(kind="text", x=clip_x + 20, y=clip_y0 + 36, w=clip_w - 40, h=56,
                     text=spec.title, font="Georgia Bold", size=19, align="left",
                     color="#141414", line_spacing=22))
    body_y = clip_y0 + 100
    body_h = clip_y1 - m[3] - body_y - (16 if spec.citations else 0) - 20
    layout.add(Frame(kind="text", x=clip_x + 20, y=body_y, w=clip_w - 40, h=max(body_h, 20),
                     text=_wrap_body(spec.body) or "\n\n".join(f.text for f in spec.facts),
                     font="Times New Roman Regular", size=9.5, align="justify",
                     color="#1a1a1a", line_spacing=13))
    _citation_footer(spec, layout, font="Georgia Regular", size=7.0, color="#8a8168")
    _editorial_mark(spec, layout, font="Georgia Regular")
    return layout
