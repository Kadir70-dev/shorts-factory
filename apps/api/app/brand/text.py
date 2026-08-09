"""
ffmpeg `drawtext` construction — the one place that knows how to escape text.

drawtext's escaping rules are a genuine trap: the filtergraph parser eats commas,
colons, single quotes, backslashes and `%` sequences at DIFFERENT levels, and a
mistake shows up as a silently-dropped filter or a render that dies three stages
later. Centralising it here means the rest of the brand system builds overlays by
describing them, never by concatenating filter strings.

Also home to the word-wrapper: we measure in characters against a per-size budget
calibrated for the 1080-wide frame, because measuring real glyph advances would
need a font library we deliberately don't depend on.
"""
from __future__ import annotations

import textwrap

# Approximate characters that fit the usable width at a given font size on a
# 1080px frame with the standard side margins. Bold condensed faces run tighter
# than DejaVu, so these are deliberately conservative — better a slightly early
# wrap than an overflowing line.
_CHAR_BUDGET = [
    (170, 10), (150, 12), (120, 14), (96, 17), (76, 21), (66, 25),
    (60, 27), (52, 32), (46, 36), (40, 42), (34, 50), (30, 56), (24, 70),
]


def chars_for(size: int, frame_width: int = 1080) -> int:
    """How many characters fit one line at `size` on a `frame_width` frame."""
    budget = 70
    for threshold, chars in _CHAR_BUDGET:
        if size >= threshold:
            budget = chars
            break
    return max(6, round(budget * frame_width / 1080))


def wrap(text: str, size: int, frame_width: int = 1080,
         max_lines: int = 4) -> list[str]:
    """Word-wrap to the character budget, hard-truncating past `max_lines` so a
    runaway headline can never push captions off-screen."""
    lines = textwrap.wrap(text.strip(), width=chars_for(size, frame_width)) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .,;:") + "…"
    return lines


def escape(text: str) -> str:
    """Escape a literal string for use inside a drawtext `text='...'` value.

    This is narrower than it looks like it should be, and every part of it was
    established by rendering test strings and LOOKING at the output — ffmpeg
    reports success while drawing nothing, so "exit code 0" proves nothing here.

      \\  must be doubled, and first, or we escape our own escapes.
      :   must be escaped even inside quotes; the option-splitting pass runs
          before quote handling and a raw colon truncates the whole filter.
      '   CANNOT be escaped inside single quotes — ffmpeg offers no in-place
          escape. Rather than close/reopen the quote (which then re-exposes every
          other character), we substitute the typographic apostrophe, which is
          what a documentary caption should be using anyway.
      %   is left ALONE and neutralised by `expansion=none` in `drawtext()`.
          Escaping it as `\\%` makes drawtext render the entire string as blank —
          which is what was silently happening to every overlay containing a
          percentage.
      , ; [ ] = & $ " need nothing inside quotes; escaping them would render the
          backslash literally.
    """
    return (text.replace("\\", "\\\\")
                .replace("'", "’")
                .replace(":", "\\:"))


def escape_path(path: str) -> str:
    """Escape a filesystem path for an UNQUOTED filter option value (`fontfile=`).

    Windows paths need backslashes turned to forward slashes (ffmpeg accepts
    either, and a raw backslash is this parser's escape character) and the
    drive-letter colon escaped like any other colon. POSIX paths have neither
    character, so this is a no-op there.
    """
    return path.replace("\\", "/").replace(":", "\\:")


def drawtext(text: str, *, font: str, size: int, color: str, x: str, y: str,
             alpha: float | str = 1.0, border: int = 0,
             border_color: str = "black", shadow: int = 0,
             shadow_color: str = "black@0.75", box: bool = False,
             box_color: str = "black@0.6", box_pad: int = 18,
             enable: str = "", line_spacing: int = 0) -> str:
    """Build one drawtext filter.

    `x`/`y`/`enable` are passed through as ffmpeg EXPRESSIONS (so callers can use
    `(w-text_w)/2`, `between(t,1,2)`, …) — only `text` is escaped as a literal.

    `alpha` accepts a constant OR an ffmpeg expression (see `fade_alpha`); the
    two need different syntax, which is exactly the kind of detail this module
    exists to hide.
    """
    parts = [
        f"drawtext=text='{escape(text)}'",
        # We never use `%{...}` expansion, and leaving it on makes any literal
        # percent sign blank the entire draw. Off is the only correct setting.
        "expansion=none",
        f"fontsize={size}",
        f"fontcolor={color}",
        f"x={x}", f"y={y}",
    ]
    if isinstance(alpha, str):
        parts.append(f"alpha='{alpha}'")
    elif alpha < 1.0:
        parts.append(f"alpha={alpha:.3f}")
    if font:
        parts.insert(1, f"fontfile='{escape_path(font)}'")
    if border:
        parts += [f"borderw={border}", f"bordercolor={border_color}"]
    if shadow:
        parts += [f"shadowx={shadow}", f"shadowy={shadow}",
                  f"shadowcolor={shadow_color}"]
    if box:
        parts += ["box=1", f"boxcolor={box_color}", f"boxborderw={box_pad}"]
    if line_spacing:
        parts.append(f"line_spacing={line_spacing}")
    if enable:
        parts.append(f"enable='{enable}'")
    return ":".join(parts)


def drawtext_block(lines: list[str], *, font: str, size: int, color: str,
                   y_top: int, x: str = "(w-text_w)/2", leading: float = 1.22,
                   **kw) -> list[str]:
    """A stack of centred drawtext lines — used for every wrapped element."""
    step = int(size * leading)
    return [drawtext(ln, font=font, size=size, color=color, x=x,
                     y=str(y_top + i * step), **kw)
            for i, ln in enumerate(lines) if ln]


def fade_alpha(t_in: float, t_out: float, fade: float = 0.25) -> str:
    """An alpha EXPRESSION that fades an element in at `t_in` and out at `t_out`.

    Passed to drawtext as `alpha=<expr>`; used for lower thirds and the end card
    so branded elements arrive and leave, never pop.
    """
    f = max(0.05, fade)
    return (f"if(lt(t,{t_in:.3f}),0,"
            f"if(lt(t,{t_in + f:.3f}),(t-{t_in:.3f})/{f:.3f},"
            f"if(lt(t,{max(t_in + f, t_out - f):.3f}),1,"
            f"if(lt(t,{t_out:.3f}),({t_out:.3f}-t)/{f:.3f},0))))")
