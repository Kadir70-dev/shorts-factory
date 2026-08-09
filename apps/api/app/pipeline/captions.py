"""
Captions. Preferred path: Whisper.cpp word-level over the master VO (exact
timings, karaoke highlight). Fallback path (no whisper binary): derive caption
segments from each scene's narration spread across its MEASURED duration. The
fallback is good enough to ship and needs zero extra tooling.

SAFE-WIDTH FITTING (both paths): a caption group is grouped by WORD COUNT
(<=4 words) or by whisper's own `--max-len` character budget — neither knows
the actual rendered pixel width of what it grouped. Combined with the ASS
caption style's `WrapStyle: 2` (no auto-wrap, see brand/overlays.py), a group
of a few unusually LONG words ("September fifteenth, one forty-five") can
render wider than the frame's safe area and overflow both edges instead of
wrapping. `_fit_to_safe_width()` re-splits any group that's actually too wide
using real glyph advance widths (brand/font_metrics.py), at word boundaries,
after either path has produced its captions -- a safety net on top of the
existing grouping rather than a rewrite of it, so ordinary short groups are
untouched. `theme` is optional and defaults to None (old behavior, unchanged)
so every other caller of `transcribe()` keeps working exactly as before;
scripts/produce.py is the one caller that now has a theme to pass.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from ..schemas.scene import Caption, SceneGraph

if TYPE_CHECKING:
    from ..brand.theme import BrandTheme

WHISPER_BIN = "/opt/whisper.cpp/main"
WHISPER_MODEL = "/opt/whisper.cpp/models/ggml-base.en.bin"
MAX_WORDS_PER_CAPTION = 4   # punchy 3-5 word caption chunks


async def transcribe(graph: SceneGraph, theme: "BrandTheme | None" = None) -> SceneGraph:
    if Path(WHISPER_BIN).exists() and graph.audio.voiceover_path:
        try:
            graph.captions = await _whisper(graph)
        except Exception:
            graph.captions = _from_script(graph)
    else:
        graph.captions = _from_script(graph)
    if theme is not None:
        graph.captions = _fit_to_safe_width(graph.captions, theme, graph.width, graph.height)
    return graph


# --------------------------- whisper path ---------------------------------- #
async def _whisper(graph: SceneGraph) -> list[Caption]:
    vo = graph.audio.voiceover_path
    out = Path(vo).parent / "captions"
    proc = await asyncio.create_subprocess_exec(
        WHISPER_BIN, "-m", WHISPER_MODEL, "-f", vo,
        "-oj", "-of", str(out), "--max-len", "24", "--split-on-word", "true",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    data = json.loads(out.with_suffix(".json").read_text())
    caps: list[Caption] = []
    for seg in data.get("transcription", []):
        o = seg["offsets"]
        caps.append(Caption(
            start=o["from"] / 1000.0, end=o["to"] / 1000.0, text=seg["text"].strip(),
            words=[{"w": t["text"].strip(), "s": t["offsets"]["from"] / 1000.0,
                    "e": t["offsets"]["to"] / 1000.0}
                   for t in seg.get("tokens", []) if t["text"].strip()],
        ))
    return caps


# --------------------------- fallback path --------------------------------- #
def _from_script(graph: SceneGraph) -> list[Caption]:
    caps: list[Caption] = []
    t = 0.0
    for scene in graph.scenes:
        words = scene.narration.split()
        if not words:
            t += scene.duration_sec
            continue
        # time-budget per word inside this scene's measured window
        per_word = scene.duration_sec / len(words)
        for i in range(0, len(words), MAX_WORDS_PER_CAPTION):
            chunk = words[i:i + MAX_WORDS_PER_CAPTION]
            start = t + i * per_word
            end = t + (i + len(chunk)) * per_word
            caps.append(Caption(
                start=round(start, 3), end=round(end, 3), text=" ".join(chunk),
                words=[{"w": w, "s": round(t + (i + j) * per_word, 3),
                        "e": round(t + (i + j + 1) * per_word, 3)}
                       for j, w in enumerate(chunk)],
            ))
        t += scene.duration_sec
    return caps


# --------------------------- safe-width fitting ----------------------------- #
def _safe_width_px(theme: "BrandTheme", width: int) -> float:
    side = float(theme.safe.get("side", 0.055)) * width
    return width - 2 * side


def _rendered_width_px(text: str, theme: "BrandTheme", size_px: float) -> float:
    """Real glyph-advance width when the caption font resolved to a real
    file; falls back to the existing character-budget heuristic
    (brand/text.py) when it didn't, so a fit decision never silently
    defaults to "assume it fits" -- that's exactly the bug being fixed."""
    from ..brand import font_metrics
    from ..brand.text import chars_for

    cased = theme.body.apply_case(text)
    w = font_metrics.text_width_px(cased, theme.body.path, size_px)
    if w is not None:
        return w
    budget_chars = chars_for(round(size_px))
    return (len(cased) / max(1, budget_chars)) * 1080.0


def _split_words_to_fit(words: list[dict], theme: "BrandTheme", size_px: float,
                        safe_px: float) -> list[list[dict]]:
    """Greedy word-boundary split: grow a group while it still fits; once
    adding the next word would overflow, close the group and start a new
    one. A single word that alone exceeds the safe width still gets its own
    group -- splitting inside a word is not an option."""
    groups: list[list[dict]] = []
    current: list[dict] = []
    for w in words:
        candidate = current + [w]
        text = " ".join(x["w"] for x in candidate)
        if not current or _rendered_width_px(text, theme, size_px) <= safe_px:
            current = candidate
        else:
            groups.append(current)
            current = [w]
    if current:
        groups.append(current)
    return groups


def _caption_from_words(words: list[dict]) -> Caption:
    return Caption(
        start=words[0]["s"], end=words[-1]["e"],
        text=" ".join(w["w"] for w in words),
        words=words,
    )


def _fit_to_safe_width(caps: list[Caption], theme: "BrandTheme",
                       width: int, height: int) -> list[Caption]:
    """Re-split any caption group whose REAL rendered width exceeds the safe
    area, at word boundaries, preserving each word's own timing. Groups that
    already fit are returned unchanged -- this only ever adds splits, never
    changes font size, spacing, or styling."""
    size_px = theme.size("caption", height)
    safe_px = _safe_width_px(theme, width)
    out: list[Caption] = []
    for c in caps:
        if not c.words or _rendered_width_px(c.text, theme, size_px) <= safe_px:
            out.append(c)
            continue
        for group in _split_words_to_fit(c.words, theme, size_px, safe_px):
            out.append(_caption_from_words(group))
    return out
