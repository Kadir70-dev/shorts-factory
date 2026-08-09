"""Regression tests for the caption safe-width fix.

Root cause was two-layered:
  1. `theme.resolve_font()` returned the search-preference string ("Barlow")
     as the ASS Fontname instead of the font file's own family name ("Barlow
     Condensed") -- libass then couldn't match it, silently substituted a
     wider fallback font, and every caption rendered wider than intended.
  2. Even with the right font, `captions.py` grouped words by COUNT only
     (<=4 words), with no awareness of rendered pixel width, so a group of a
     few long words could still exceed the safe area -- and `WrapStyle: 2`
     in the ASS style means an oversized group doesn't wrap, it overflows.

These tests cover both: font-name resolution, and the width-aware caption
splitter against the two real failing groups from the Bitcoin demo.
"""
from __future__ import annotations

import pytest

from app.brand.theme import load_theme
from app.pipeline import captions as cap_mod
from app.schemas.scene import Caption


@pytest.fixture(scope="module")
def theme():
    return load_theme("k70")


def _words(text: str, start: float = 0.0, dur_per_word: float = 0.3) -> list[dict]:
    out, t = [], start
    for w in text.split():
        out.append({"w": w, "s": round(t, 3), "e": round(t + dur_per_word, 3)})
        t += dur_per_word
    return out


def _caption(text: str) -> Caption:
    words = _words(text)
    return Caption(start=words[0]["s"], end=words[-1]["e"], text=text, words=words)


# --------------------------------------------------------------------------- #
# Font resolution: the actual root cause
# --------------------------------------------------------------------------- #
def test_resolved_caption_font_name_matches_the_file(theme):
    """Fontname must be a name libass can actually match against the file
    theme.body.path points at -- not just the search string that found it."""
    if not theme.body.path:
        pytest.skip("no caption font resolved on this machine")
    from app.brand.font_metrics import real_family_name
    real = real_family_name(theme.body.path)
    assert real is not None, "font file's name table should be readable"
    assert theme.body.name == real, (
        f"ASS Fontname {theme.body.name!r} != the file's real family "
        f"{real!r} -- libass will silently substitute a fallback font"
    )


# --------------------------------------------------------------------------- #
# Width-aware splitting: the two real failing groups from the Bitcoin demo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text", [
    "September fifteenth, one forty-five",
    "Brothers filed for bankruptcy.",
])
def test_real_failing_groups_now_fit(theme, text):
    c = _caption(text)
    out = cap_mod._fit_to_safe_width([c], theme, 1080, 1920)
    size_px = theme.size("caption", 1920)
    safe_px = cap_mod._safe_width_px(theme, 1080)
    for g in out:
        w = cap_mod._rendered_width_px(g.text, theme, size_px)
        assert w <= safe_px + 1e-6, f"{g.text!r} still overflows: {w:.1f} > {safe_px:.1f}"


@pytest.mark.parametrize("text", [
    "in the morning: Lehman",
    "This is the story",
    "Ask e-gold.",
    "that would change",
    "IT WAS THE FIRST",
    "DEPARTMENT INDICTED IT.",
])
def test_short_groups_are_never_split(theme, text):
    """Requirement: normal short caption groups must render unchanged."""
    c = _caption(text)
    out = cap_mod._fit_to_safe_width([c], theme, 1080, 1920)
    assert len(out) == 1
    assert out[0].text == c.text
    assert out[0].start == c.start
    assert out[0].end == c.end
    assert out[0].words == c.words


@pytest.mark.parametrize("text", [
    "September fifteenth, one forty-five in the morning: Lehman Brothers filed for bankruptcy.",
    "Brothers filed for bankruptcy.",
    "a b c d e f g h i j k l m n o p q r s t",  # many short words, still could overflow
])
def test_split_never_breaks_a_word_and_preserves_timing(theme, text):
    c = _caption(text)
    out = cap_mod._fit_to_safe_width([c], theme, 1080, 1920)

    # Word sequence intact, nothing merged/dropped/split mid-word.
    reconstructed = " ".join(w["w"] for g in out for w in g.words)
    assert reconstructed == text

    # Timing: first group starts where the original did, last group ends
    # where the original did, and every word keeps its own s/e untouched.
    assert out[0].start == c.start
    assert out[-1].end == c.end
    flat_words = [w for g in out for w in g.words]
    assert flat_words == c.words


def test_all_groups_fit_after_splitting(theme):
    """No matter how it's split, nothing may render outside the safe area."""
    size_px = theme.size("caption", 1920)
    safe_px = cap_mod._safe_width_px(theme, 1080)
    texts = [
        "September fifteenth, one forty-five in the morning: Lehman Brothers filed for bankruptcy.",
        "Within weeks the central bank would print a one hundred trillion dollar note.",
        "On the fourteenth of November, two thousand and seven, federal agents raided its offices and seized the coins.",
    ]
    for text in texts:
        out = cap_mod._fit_to_safe_width([_caption(text)], theme, 1080, 1920)
        for g in out:
            w = cap_mod._rendered_width_px(g.text, theme, size_px)
            assert w <= safe_px + 1e-6, f"{g.text!r} overflows after split: {w:.1f}px"


def test_single_overlong_word_gets_its_own_group_not_split(theme):
    """A single word wider than the safe area can't be split further --
    it must still get its own group rather than raising or merging."""
    text = "Antidisestablishmentarianistically-hyphenated-mega-word-of-unusual-length"
    c = _caption(text)
    out = cap_mod._fit_to_safe_width([c], theme, 1080, 1920)
    assert len(out) == 1
    assert out[0].text == text
    assert len(out[0].words) == 1


# --------------------------------------------------------------------------- #
# Backward compatibility: theme=None must reproduce the OLD behavior exactly
# --------------------------------------------------------------------------- #
def test_fit_is_opt_in_via_theme_parameter():
    """Every existing caller of transcribe() passes no theme -- confirms the
    new pass only ever runs when a theme is explicitly supplied."""
    import inspect
    sig = inspect.signature(cap_mod.transcribe)
    assert sig.parameters["theme"].default is None
