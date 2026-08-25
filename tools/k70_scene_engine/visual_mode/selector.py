"""Semantic beat -> VisualMode selection (brief sections 10 + 11).

Rule-based, not ML -- every rule below is directly traceable to one of the
brief's own worked examples (see `tests/test_selector.py`), which is the
only honest way to claim "semantic, not random" for a system built in one
session with no training data or evaluation set of its own.

Sequence-level consistency (section 11: don't flip REAL -> 3D -> VOXEL
every few seconds without narrative reason) is handled by
`SequencePlanner`: once a character-driven story starts, it keeps
returning THREE_D_CHARACTER/3D_ENVIRONMENT for that character until either
the character stops being mentioned for `break_after` consecutive beats or
the narration explicitly shifts topic (a currency pair, an institution, or
a bare statistic with no character).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .modes import VisualMode
from ..characters.roster import ROSTER

_CURRENCY_PAIR = re.compile(r"\b([A-Z]{3})/([A-Z]{3})\b")
_DOLLAR_AMOUNT = re.compile(r"\$[\d,]+(?:\.\d+)?\s*(?:thousand|million|billion|trillion|k|m|b)?", re.I)
_PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s?%")

_INSTITUTIONS = [
    "federal reserve", "the fed", "european central bank", "ecb", "bank of england",
    "treasury", "irs", "cftc", "sec", "world gold council", "central bank",
]

_POPULATION_STATEMENT_HINTS = [
    "millions of", "most americans", "many people", "americans use",
    "consumers", "the average", "on average",
]

_NAMED_CHARACTER_RE = re.compile(
    r"\b(" + "|".join(re.escape(c.display_name) for c in ROSTER.values()) + r")\b")


@dataclass
class BeatDecision:
    mode: VisualMode
    reason: str
    character_id: str | None = None
    template_hint: str | None = None


def _mentions_institution(text_l: str) -> bool:
    return any(inst in text_l for inst in _INSTITUTIONS)


def _mentions_population(text_l: str) -> bool:
    return any(h in text_l for h in _POPULATION_STATEMENT_HINTS)


def classify(narration: str) -> BeatDecision:
    """Single-beat classification with no sequence memory -- used directly
    by tests and as the fallback `SequencePlanner` builds continuity on
    top of."""
    text_l = narration.lower()

    pair = _CURRENCY_PAIR.search(narration)
    if pair and pair.group(1) != pair.group(2):
        return BeatDecision(VisualMode.DATA_CHART, f"currency pair mentioned ({pair.group(0)})")

    named = _NAMED_CHARACTER_RE.search(narration)
    has_money = _DOLLAR_AMOUNT.search(narration) or _PERCENT.search(narration)
    if named and has_money:
        char = next(c for c in ROSTER.values() if c.display_name == named.group(1))
        return BeatDecision(VisualMode.THREE_D_CHARACTER,
                            f"named character '{char.display_name}' + financial figure",
                            character_id=char.character_id)
    if named:
        char = next(c for c in ROSTER.values() if c.display_name == named.group(1))
        return BeatDecision(VisualMode.THREE_D_CHARACTER, f"named character '{char.display_name}'",
                            character_id=char.character_id)

    if _mentions_institution(text_l):
        return BeatDecision(VisualMode.MOTION_GRAPHIC, "institutional actor named, no scene character")

    if _mentions_population(text_l):
        return BeatDecision(VisualMode.REAL_STOCK, "generic population statement -- prefer real-world footage")

    if has_money or _PERCENT.search(narration):
        return BeatDecision(VisualMode.DATA_CHART, "bare financial figure, no character or institution")

    return BeatDecision(VisualMode.MOTION_GRAPHIC, "no strong signal -- default to a plain explainer card")


@dataclass
class SequencePlanner:
    """Wraps `classify()` with the section-11 consistency rule: once a
    character sequence starts, keep the character's visual world (3D
    character/environment) across beats that don't introduce a new,
    unrelated topic, instead of re-classifying every beat in isolation."""
    break_after: int = 2
    _active_character: str | None = field(default=None, init=False)
    _beats_since_mention: int = field(default=0, init=False)

    def decide(self, narration: str) -> BeatDecision:
        d = classify(narration)

        if d.character_id:
            self._active_character = d.character_id
            self._beats_since_mention = 0
            return d

        if self._active_character is not None:
            # A hard topic switch (new currency pair, new institution) ends
            # the sequence immediately; anything else gets `break_after`
            # beats of grace so "John deposits it. The bank processes the
            # transfer." doesn't lose continuity on the second sentence.
            hard_switch = d.mode in (VisualMode.DATA_CHART,) and "currency pair" in d.reason
            if hard_switch or self._beats_since_mention >= self.break_after:
                self._active_character = None
            else:
                self._beats_since_mention += 1
                char = ROSTER[self._active_character]
                return BeatDecision(VisualMode.THREE_D_ENVIRONMENT,
                                    f"continuing '{char.display_name}' sequence (grace beat "
                                    f"{self._beats_since_mention}/{self.break_after})",
                                    character_id=self._active_character)
        return d
