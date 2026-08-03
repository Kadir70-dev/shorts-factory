"""
Theme → ffmpeg. Every branded element the renderer composites lives here.

Split by WHERE it applies, because the renderer builds scene clips first and only
later concatenates them:

  per-scene   — headline / stat / source typography, lower thirds. Built into the
                individual scene clip so timing is scene-relative.
  full-frame  — watermark bug, disclaimer band, intro wipe, end card, captions.
                Applied over the concatenated timeline where absolute time is
                meaningful.

Two return shapes, and the distinction matters:

  * `list[str]`      — drawtext/drawbox fragments. Pure filters, no extra inputs,
                       and drawtext's `alpha` accepts a time EXPRESSION so these
                       can fade themselves.
  * `ImageOverlay`   — a PNG plate that needs its own ffmpeg input. `overlay` has
                       no alpha expression, so timed opacity is expressed as
                       declarative fade fields and the renderer builds the
                       labelled `fade=…:alpha=1` chain. Returning half-built
                       filter strings for these is how label collisions happen.

The caption ASS generator carries the five ANIMATION variants the brand rotates
between. They differ only in motion; the type system (face, size, outline, band
position, keyword colour) is identical across all five — visible variety, one
recognisable channel.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..schemas.scene import Caption, Scene, SceneGraph
from . import text as tx
from .theme import BrandTheme

CAPTION_ANIMATIONS = ["word_pop", "karaoke_fill", "line_rise", "keyword_flash",
                      "block_cut"]

# Words that never deserve the keyword highlight — emphasising "the" reads as a
# bug, not a design choice.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "it",
    "its", "this", "that", "these", "those", "you", "your", "we", "our", "they",
    "their", "he", "she", "his", "her", "not", "no", "so", "if", "than", "then",
    "into", "over", "just", "more", "most", "up", "out", "about",
}


@dataclass
class ImageOverlay:
    """A PNG plate composited over the frame at a position, optionally timed.

    Declarative on purpose: the renderer owns filtergraph labelling, so this
    describes intent and never emits `[label]` syntax of its own.
    """
    path: Path
    x: str = "0"                    # ffmpeg overlay expression
    y: str = "0"
    scale_w: int | None = None      # scale plate to this width (keep aspect)
    opacity: float = 1.0            # constant opacity
    start: float | None = None      # visible window (None = whole timeline)
    end: float | None = None
    fade: float = 0.25              # in/out fade seconds within the window


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #
def _ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _keyword_index(words: list[str]) -> int:
    """Pick the word that carries the beat: a figure if present, else the longest
    non-stopword. Returns -1 when nothing is worth emphasising."""
    best, best_score = -1, 0
    for i, w in enumerate(words):
        clean = "".join(ch for ch in w if ch.isalnum() or ch in ".%$-")
        if not clean:
            continue
        if any(ch.isdigit() for ch in clean):
            return i                           # numbers always win
        if clean.lower() in _STOPWORDS or len(clean) < 5:
            continue
        if len(clean) > best_score:
            best, best_score = i, len(clean)
    return best


def _caption_event(cap: Caption, theme: BrandTheme, animation: str,
                   width: int, height: int) -> str:
    """One ASS Dialogue body, styled by the chosen animation variant."""
    words = cap.text.split()
    if not words:
        return ""
    body = theme.body.apply_case(cap.text)
    hl = theme.ass(theme.captions.get("highlight_color", "primary"))
    cx = width // 2
    cy = int(float(theme.captions.get("y", 0.775)) * height)

    if animation == "karaoke_fill":
        # \k fills word-by-word: PrimaryColour paints the sung part and Secondary
        # the rest, so the STYLE must set Secondary to the resting ink colour.
        parts = []
        cased = theme.body.apply_case(" ".join(words)).split()
        for i, w in enumerate(cased):
            src = cap.words[i] if i < len(cap.words) else None
            dur = ((src.get("e", 0.0) - src.get("s", 0.0)) if src
                   else (cap.end - cap.start) / len(words))
            parts.append(f"{{\\k{max(1, int(dur * 100))}}}{w} ")
        return "{\\fad(70,60)}" + "".join(parts).rstrip()

    if animation == "word_pop":
        return ("{\\fad(60,50)\\fscx88\\fscy88"
                "\\t(0,110,\\fscx104\\fscy104)"
                "\\t(110,190,\\fscx100\\fscy100)}" + body)

    if animation == "line_rise":
        rise = round(height * 0.022)
        return f"{{\\fad(90,70)\\move({cx},{cy + rise},{cx},{cy},0,150)}}" + body

    if animation == "keyword_flash":
        idx = _keyword_index(words)
        cased = theme.body.apply_case(" ".join(words)).split()
        if idx < 0:
            return "{\\fad(60,50)}" + body
        cased[idx] = (f"{{\\c{hl}\\t(0,140,\\fscx108\\fscy108)"
                      f"\\t(140,240,\\fscx100\\fscy100)}}{cased[idx]}"
                      f"{{\\c{theme.ass('ink')}\\fscx100\\fscy100}}")
        return "{\\fad(60,50)}" + " ".join(cased)

    return body                                # block_cut — documentary restraint


def caption_ass(graph: SceneGraph, theme: BrandTheme, animation: str = "word_pop",
                mute_windows: list[tuple[float, float]] | None = None) -> str:
    """Full ASS document for the timeline's captions.

    `mute_windows` are spans where another element owns the frame (a hero stat, a
    full-frame chart, the end card) — the one-dominant-element rule the channel
    already follows, now applied to charts and the outro too.
    """
    width, height = graph.width, graph.height
    caps = theme.captions
    size = theme.size("caption", height)
    outline = int(caps.get("outline_px", 5))
    shadow = int(caps.get("shadow_px", 3))
    margin_v = max(10, height - int(float(caps.get("y", 0.775)) * height))
    side = int(float(theme.safe.get("side", 0.055)) * width)

    karaoke = animation == "karaoke_fill"
    primary = theme.ass(caps.get("highlight_color", "primary")) if karaoke \
        else theme.ass("ink")
    secondary = theme.ass("ink") if karaoke else theme.ass("ink_dim")

    head = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Cap,{theme.body.name},{size},{primary},{secondary},"
        f"{theme.ass('shadow')},{theme.ass('shadow', 120)},"
        f"-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,"
        f"{side},{side},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Text\n"
    )

    mute = mute_windows or []
    lines = [head]
    for c in graph.captions:
        mid = (c.start + c.end) / 2
        if any(s <= mid < e for s, e in mute):
            continue
        body = _caption_event(c, theme, animation, width, height)
        if not body:
            continue
        lines.append(f"Dialogue: 0,{_ass_time(c.start)},{_ass_time(c.end)},"
                     f"Cap,0,0,0,{body}\n")
    return "".join(lines)


# --------------------------------------------------------------------------- #
# Per-scene typography
# --------------------------------------------------------------------------- #
_EMPH = {"normal": "ink", "alert": "warn", "positive": "positive",
         "negative": "negative"}


def scene_overlay_filters(scene: Scene, theme: BrandTheme, width: int,
                          height: int, hook: bool = False) -> list[str]:
    """Headline / stat / source typography in the brand's type system.

    Keeps the ONE-DOMINANT-ELEMENT rule: a hero number owns the frame, otherwise a
    single headline does. Everything else reduces to a small credit. A scene whose
    visual is already a full-frame chart skips the stat — the chart IS the number.
    """
    stat = next((o for o in scene.overlays if o.type == "stat" and o.sub), None)
    headline = next((o for o in scene.overlays if o.type == "headline"), None)
    source = next((o for o in scene.overlays if o.type == "source"), None)
    chart_owns_number = scene.visual.type == "dataviz"
    out: list[str] = []

    if headline and (hook or not stat or chart_owns_number):
        size = theme.size("hook" if hook else "headline", height)
        color = theme.ff(_EMPH.get(headline.emphasis, "ink"))
        body = theme.display.apply_case(headline.text)
        out += tx.drawtext_block(
            tx.wrap(body, size, width, max_lines=3), font=theme.display.path,
            size=size, color=color, y_top=int(headline.y * height), shadow=4,
            box=True, box_color=f"{theme.ff('bg')}@0.55", box_pad=round(20 * width / 1080),
        )

    if stat and not chart_owns_number:
        y = int(stat.y * height)
        num_size = theme.size("stat_number", height)
        lbl_size = theme.size("stat_label", height)
        color = theme.ff(_EMPH.get(stat.emphasis, "primary"))
        # the figure gets the mono face — tabular digits, no wobble
        out.append(tx.drawtext(
            stat.sub, font=theme.mono.path, size=num_size, color=color,
            x="(w-text_w)/2", y=str(y), border=round(5 * width / 1080),
            border_color=theme.ff("bg"), shadow=4,
        ))
        out += tx.drawtext_block(
            tx.wrap(theme.body.apply_case(stat.text), lbl_size, width, max_lines=2),
            font=theme.body.path, size=lbl_size, color=theme.ff("ink"),
            y_top=y + round(num_size * 1.12), shadow=3,
        )

    if source:
        out.append(tx.drawtext(
            source.text, font=theme.body.path, size=theme.size("source", height),
            color=theme.ff("ink_dim"), x="(w-text_w)/2",
            y=str(int(float(theme.safe.get("top", 0.09)) * height * 0.75)),
            alpha=0.9, shadow=2,
        ))
    return out


def lower_third_filters(theme: BrandTheme, title: str, sub: str, width: int,
                        height: int, start: float, duration: float,
                        plate: Path | None = None
                        ) -> tuple[list[ImageOverlay], list[str]]:
    """Animated lower third → (image overlays, drawtext filters).

    The plate slides in from the left edge and holds; the type fades with it.
    """
    if not title:
        return [], []
    lt = theme.lower_third
    h = round(int(lt.get("height_px", 150)) * height / 1920)
    y = int(float(lt.get("y", 0.615)) * height)
    t_in = float(lt.get("in_sec", 0.42))
    end = start + duration

    plates: list[ImageOverlay] = []
    if plate and plate.exists():
        plates.append(ImageOverlay(
            path=plate,
            # slide: x travels from -W to 0 over t_in, then holds
            x=(f"if(lt(t,{start:.3f}),-w,"
               f"if(lt(t,{start + t_in:.3f}),"
               f"-w*(1-(t-{start:.3f})/{t_in:.3f}),0))"),
            y=str(y), scale_w=width, start=start, end=end, fade=0.18,
        ))

    pad = (round(int(lt.get("accent_bar_px", 10)) * width / 1080)
           + round(float(theme.safe.get("side", 0.055)) * width)
           + round(26 * width / 1080))
    alpha = tx.fade_alpha(start, end, fade=max(t_in, 0.2))
    # The vector plate is also expressed as filters so scene-local renderers do
    # not need another input merely to preserve the shared lower-third style.
    bar = round(int(lt.get("accent_bar_px", 10)) * width / 1080)
    bg_alpha = float(lt.get("bg_opacity", .86))
    enable = f"enable='between(t,{start:.3f},{end:.3f})'"
    filters = [
        f"drawbox=x=0:y={y}:w={width}:h={h}:color={theme.ff('bg_soft')}@{bg_alpha:.2f}:t=fill:{enable}",
        f"drawbox=x=0:y={y}:w={bar}:h={h}:color={theme.ff('primary')}@1:t=fill:{enable}",
        tx.drawtext(
        theme.body.apply_case(title), font=theme.display.path,
        size=theme.size("lower_third", height), color=theme.ff("ink"),
        x=str(pad), y=str(y + round(h * 0.20)), alpha=alpha, shadow=3,
    )]
    if sub:
        filters.append(tx.drawtext(
            sub, font=theme.body.path,
            size=theme.size("lower_third_sub", height),
            color=theme.ff("primary"), x=str(pad),
            y=str(y + round(h * 0.62)), alpha=alpha, shadow=2,
        ))
    return plates, filters


# --------------------------------------------------------------------------- #
# Full-timeline elements
# --------------------------------------------------------------------------- #
def intro_filters(theme: BrandTheme, width: int, height: int) -> list[str]:
    """The brand stamp over the hook: an accent rule that wipes across, plus the
    wordmark. Under a second, then gone — restraint reads as authority."""
    intro = theme.intro
    if not intro.get("enabled", True) or intro.get("style") == "none":
        return []
    dur = float(intro.get("duration_sec", 0.7))
    wipe = max(0.15, dur * 0.55)
    # Upper third, NOT the centre: the hook's headline block is centred around
    # 0.44, and a brand stamp that lands on top of the first line of the video is
    # worse than no brand stamp.
    y = int(height * 0.26)
    accent = theme.title_card.get("eyebrow_color", "primary")
    out = [
        # drawbox evaluates w per frame, so the rule genuinely wipes across.
        # `iw`, not `w`: inside drawbox's own `w` expression, `w` IS the box width
        # being computed, so referencing it is self-referential and errors out.
        f"drawbox=x=0:y={y}:w='min(iw,iw*t/{wipe:.3f})':"
        f"h={max(4, height // 320)}:color={theme.ff(accent)}@0.95:t=fill:"
        f"enable='between(t,0,{dur:.3f})'"
    ]
    if intro.get("show_wordmark", True) and theme.watermark.get("text"):
        size = theme.size("headline", height)
        out.append(tx.drawtext(
            theme.watermark["text"], font=theme.display.path, size=size,
            color=theme.ff("ink"), x="(w-text_w)/2",
            y=str(y - round(size * 1.35)),
            alpha=tx.fade_alpha(0.05, dur, fade=0.18), shadow=4,
        ))
    return out


def outro_filters(theme: BrandTheme, width: int, height: int, total: float,
                  cta: str, disclaimer: str, endcard: Path | None = None
                  ) -> tuple[list[ImageOverlay], list[str], tuple[float, float]]:
    """End card over the final beat → (overlays, filters, muted window).

    The muted window is handed to `caption_ass` so captions yield to the card —
    otherwise the CTA and the caption line fight for the same eye.
    """
    o = theme.outro
    if not o.get("enabled", True) or o.get("style") == "none" or total <= 0:
        return [], [], (0.0, 0.0)
    dur = min(float(o.get("duration_sec", 1.4)), max(0.6, total * 0.35))
    start = max(0.0, total - dur)

    plates: list[ImageOverlay] = []
    if endcard and endcard.exists():
        plates.append(ImageOverlay(path=endcard, x="0", y="0", scale_w=width,
                                   start=start, end=total, fade=0.3))

    alpha = tx.fade_alpha(start + 0.12, total + 0.5, fade=0.26)
    filters: list[str] = []
    if o.get("show_cta", True) and cta:
        size = theme.size("headline", height)
        cta_style = theme.cta
        filters += tx.drawtext_block(
            tx.wrap(theme.display.apply_case(cta), size, width,
                    max_lines=int(cta_style.get("max_lines", 3))),
            font=theme.display.path, size=size,
            color=theme.ff(cta_style.get("text_color", "ink")),
            y_top=int(height * 0.40), alpha=alpha, shadow=4,
        )
    if o.get("show_disclaimer", True) and disclaimer:
        size = theme.size("disclaimer", height)
        filters += tx.drawtext_block(
            tx.wrap(disclaimer, size, width, max_lines=2),
            font=theme.body.path, size=size, color=theme.ff("ink_dim"),
            y_top=int(height * 0.68), alpha=alpha, shadow=2,
        )
    return plates, filters, (start, total)


def disclaimer_filters(theme: BrandTheme, width: int, height: int, text: str,
                       start: float = 1.2, duration: float = 3.0,
                       strip: Path | None = None
                       ) -> tuple[list[ImageOverlay], list[str]]:
    """The early compliance band → (overlays, filters).

    Shown near the top of the video so the disclosure lands BEFORE any claim does,
    not only in the description. Quiet by design.
    """
    if not text:
        return [], []
    end = start + duration
    y = int(height * 0.885)
    plates: list[ImageOverlay] = []
    if strip and strip.exists():
        plates.append(ImageOverlay(path=strip, x="0", y=str(y), scale_w=width,
                                   start=start, end=end, fade=0.25))
    filters = [tx.drawtext(
        text, font=theme.body.path, size=theme.size("disclaimer", height),
        color=theme.ff("ink_dim"), x="(w-text_w)/2",
        y=str(y + round(22 * height / 1920)),
        alpha=tx.fade_alpha(start, end, fade=0.25), shadow=2,
    )]
    return plates, filters


def watermark_overlay(theme: BrandTheme, width: int, height: int,
                      plate: Path | None, hide_after: float | None = None,
                      total: float | None = None
                      ) -> tuple[list[ImageOverlay], list[str]]:
    """Persistent channel bug → (overlays, drawtext filters).

    The plate carries the accent rule; the LETTERING is drawtext so it stays crisp
    at any scale and can fade for the end card without regenerating the asset.
    """
    wm = theme.watermark
    if not wm.get("text") and not (plate and plate.exists()):
        return [], []
    margin = round(int(wm.get("margin_px", 46)) * width / 1080)
    plate_w = round(int(wm.get("width_px", 190)) * width / 1080)
    plate_h = round(plate_w * 0.42)
    pos = str(wm.get("position", "top_right"))
    opacity = float(wm.get("opacity", 0.62))

    ov_x = f"W-w-{margin}" if pos.endswith("right") else f"{margin}"
    ov_y = f"{margin}" if pos.startswith("top") else f"H-h-{margin}"
    txt_x = (f"w-{margin + plate_w}" if pos.endswith("right") else f"{margin}")
    txt_y = margin if pos.startswith("top") else height - margin - plate_h

    plates: list[ImageOverlay] = []
    if plate and plate.exists():
        plates.append(ImageOverlay(
            path=plate, x=ov_x, y=ov_y, scale_w=plate_w, opacity=opacity,
            start=0.0, end=(hide_after if hide_after is not None else total),
            fade=0.2,
        ))

    alpha: float | str = opacity
    if hide_after is not None and wm.get("hide_on_outro", True):
        alpha = (f"if(lt(t,{hide_after:.3f}),{opacity:.3f},"
                 f"max(0,{opacity:.3f}*(1-(t-{hide_after:.3f})/0.4)))")

    filters: list[str] = []
    if wm.get("text"):
        main = max(22, round(plate_h * 0.52))
        filters.append(tx.drawtext(
            wm["text"], font=theme.display.path, size=main, color=theme.ff("ink"),
            x=f"{txt_x}+{round(plate_w * 0.06)}",
            y=str(txt_y + round(plate_h * 0.18)), alpha=alpha, shadow=2,
            border=2, border_color=theme.ff("bg"),
        ))
        if wm.get("sub"):
            filters.append(tx.drawtext(
                wm["sub"], font=theme.body.path,
                size=max(13, round(plate_h * 0.23)), color=theme.ff("primary"),
                x=f"{txt_x}+{round(plate_w * 0.07)}",
                y=str(txt_y + round(plate_h * 0.76)), alpha=alpha, shadow=1,
                border=2, border_color=theme.ff("bg"),
            ))
    return plates, filters


def build_image_overlay_chain(overlays: list[ImageOverlay], base_label: str,
                              first_input_index: int) -> tuple[list[str], list[str], str]:
    """Turn ImageOverlays into (ffmpeg inputs, filter chain, final video label).

    This is the one place that knows the filtergraph labelling convention, so
    callers never invent label names and collide. Timed opacity is expressed with
    `fade=…:alpha=1` on the plate stream (overlay itself has no alpha expression);
    constant opacity uses `colorchannelmixer`.
    """
    inputs: list[str] = []
    chain: list[str] = []
    label = base_label
    idx = first_input_index

    for i, ov in enumerate(overlays):
        if not ov.path.exists():
            continue
        inputs += ["-loop", "1", "-i", str(ov.path)]
        steps = ["format=rgba"]
        if ov.scale_w:
            steps.append(f"scale={ov.scale_w}:-1")
        if ov.opacity < 1.0:
            steps.append(f"colorchannelmixer=aa={ov.opacity:.3f}")
        if ov.start is not None and ov.fade > 0:
            steps.append(f"fade=t=in:st={ov.start:.3f}:d={ov.fade:.3f}:alpha=1")
        if ov.end is not None and ov.fade > 0:
            steps.append(
                f"fade=t=out:st={max(0.0, ov.end - ov.fade):.3f}:"
                f"d={ov.fade:.3f}:alpha=1")
        chain.append(f"[{idx}:v]{','.join(steps)}[bov{i}]")

        enable = ""
        if ov.start is not None and ov.end is not None:
            enable = f":enable='between(t,{ov.start:.3f},{ov.end:.3f})'"
        out_label = f"bl{i}"
        chain.append(f"[{label}][bov{i}]overlay=x={ov.x}:y={ov.y}"
                     f":shortest=0{enable}[{out_label}]")
        label = out_label
        idx += 1

    return inputs, chain, label
