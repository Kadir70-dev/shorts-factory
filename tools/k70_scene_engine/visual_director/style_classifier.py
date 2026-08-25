"""K70 Visual Engine V2 -- Visual Director classification layer (brief
2026-08-23, "ARCHITECTURE" section).

This is the beat -> style mapping layer sitting ABOVE the existing
`visual_mode.selector.classify()` (which already handles the narrower
REAL_STOCK/THREE_D_CHARACTER/MOTION_GRAPHIC/DATA_CHART split used by the
production pipeline today). It does NOT replace that selector -- it adds
the 6 new V2 style categories from the brief's own worked example table,
and reuses selector's existing regex heuristics (currency, dollar amounts,
institutions, character names) rather than re-deriving them.

Honesty note: true semantic classification of arbitrary narration text into
9 categories is a real NLP problem this one pass does not solve generally.
What IS real here: a rule-based `BEAT_TYPE_DEFAULTS` table directly
transcribed from the brief's own example mapping, plus a best-effort
`infer_beat_type()` heuristic for when the caller doesn't already know the
beat type. Per the brief's own words ("these are defaults, not rigid
rules"), callers that already know the beat type (e.g. a human-authored
storyboard, or a future LLM-based beat splitter) should pass it directly
rather than relying on the heuristic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..visual_mode.modes import VisualMode
from ..visual_mode.selector import (
    _CURRENCY_PAIR, _DOLLAR_AMOUNT, _PERCENT, _mentions_institution,
    _mentions_population, _NAMED_CHARACTER_RE,
)

# Transcribed directly from the brief's "Example classification" block.
BEAT_TYPE_DEFAULTS: dict[str, VisualMode] = {
    "story_character_action": VisualMode.THREE_D_CHARACTER,       # -> VOXEL CINEMATIC
    "simple_financial_explanation": VisualMode.VECTOR_2D,          # -> PREMIUM 2D VECTOR
    "history_news_archival": VisualMode.PAPER_COLLAGE,             # -> PAPER COLLAGE
    "physical_metaphor": VisualMode.CLAY_MINIATURE,                # -> CLAY / MINIATURE
    "emotional_abstract": VisualMode.ILLUSTRATED_2_5D,             # -> 2.5D ILLUSTRATED
    "system_economy_money_flow": VisualMode.ISOMETRIC_MINIATURE,   # -> ISOMETRIC MINIATURE
    "formula_complex_concept": VisualMode.SKETCH_HANDDRAWN,        # -> HAND-DRAWN SKETCH
    "real_world_evidence": VisualMode.REAL_STOCK,                  # -> REAL FOOTAGE
    "hard_numbers": VisualMode.DATA_CHART,                         # -> CHART / DATA GRAPHICS
}

_FORMULA_RE = re.compile(r"[\d,]+\s*[x×*]\s*[\d.]+%?\s*=", re.I)
_METAPHOR_HINTS = ["like a", "think of it as", "imagine", "picture a", "similar to"]
_SYSTEM_HINTS = ["flows into", "flows through", "money moves", "the economy", "supply chain",
                 "banking system", "moves between", "circulates"]
_EMOTIONAL_HINTS = ["feels like", "the weight of", "hope", "fear", "anxiety", "relief", "dream"]
_HISTORY_HINTS = ["in 19", "in 20", "historically", "decades ago", "the 1970s", "the 2008",
                  "world war", "the great depression", "archival"]


@dataclass
class StyleDecision:
    mode: VisualMode
    beat_type: str
    reason: str


def infer_beat_type(narration: str) -> str:
    """Best-effort heuristic only -- see module docstring. Order matters:
    checked most-specific-signal-first so a beat naming both a character
    AND a formula (e.g. "John's $10,000 at 8%...") still favors the
    concrete teachable formula over the character's mere presence, matching
    the brief's own SKETCH test case ($10,000 x 8% = $800)."""
    t = narration.lower()

    if _FORMULA_RE.search(narration):
        return "formula_complex_concept"
    if _PERCENT.search(narration) and _DOLLAR_AMOUNT.search(narration) and "=" in narration:
        return "formula_complex_concept"
    if any(h in t for h in _HISTORY_HINTS):
        return "history_news_archival"
    if any(h in t for h in _SYSTEM_HINTS):
        return "system_economy_money_flow"
    if any(h in t for h in _METAPHOR_HINTS):
        return "physical_metaphor"
    if any(h in t for h in _EMOTIONAL_HINTS):
        return "emotional_abstract"
    if _mentions_population(t) or _mentions_institution(t):
        return "real_world_evidence"
    if _CURRENCY_PAIR.search(narration) or (_PERCENT.search(narration) and not _NAMED_CHARACTER_RE.search(narration)):
        return "hard_numbers"
    if _NAMED_CHARACTER_RE.search(narration):
        return "story_character_action"
    if _DOLLAR_AMOUNT.search(narration):
        return "simple_financial_explanation"
    return "story_character_action"  # voxel cinematic stays the hero/default mode


def classify_beat(narration: str, beat_type: str | None = None) -> StyleDecision:
    bt = beat_type or infer_beat_type(narration)
    mode = BEAT_TYPE_DEFAULTS.get(bt)
    if mode is None:
        raise ValueError(f"unknown beat_type '{bt}', expected one of {list(BEAT_TYPE_DEFAULTS)}")
    reason = f"beat_type={bt}" + ("" if beat_type else " (heuristically inferred, not asserted)")
    return StyleDecision(mode=mode, beat_type=bt, reason=reason)
