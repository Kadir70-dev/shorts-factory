"""
The Director Brain. Topic -> validated SceneGraph, via a pluggable backend
(CLI on Max, or API). Flow: research -> generate -> validate -> sanity-gate ->
repair-on-failure. Backend-agnostic: it only needs `generate()` / `research()`.
"""
from __future__ import annotations

import json
import os
import re

from ..config import ChannelConfig
from ..schemas.scene import SceneGraph
from ..schemas.video_spec import VideoSpec
from . import prompts
from .backends import get_backend

MAX_REPAIRS = 3
WPS = 2.6   # words per second of speech


class Director:
    def __init__(self, channel: ChannelConfig):
        self.channel = channel
        self.backend = get_backend()
        self.research_enabled = os.getenv("DIRECTOR_RESEARCH", "1") == "1"

    async def build_scene_graph(self, spec: VideoSpec) -> SceneGraph:
        brief = ""
        if self.research_enabled:
            brief = await self.backend.research(spec.topic)

        system = prompts.system_prompt(self.channel)
        user = prompts.user_prompt(
            topic=spec.topic, tone=spec.tone, video_id=spec.id,
            channel_id=spec.channel_id, niche=spec.niche.value, research=brief,
        )
        schema = SceneGraph.model_json_schema()

        last_err = ""
        for attempt in range(MAX_REPAIRS + 1):
            u = user if attempt == 0 else (
                f"{user}\n\nYour previous attempt was REJECTED: {last_err}\n"
                "Fix it and output corrected JSON only."
            )
            raw = await self.backend.generate(system, u, schema)
            try:
                data = _extract_json(raw)
                graph = SceneGraph.model_validate(data)
                _sanity(graph, spec)
                return graph
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"

        raise ValueError(f"Director failed after {MAX_REPAIRS} repairs: {last_err}")


# --------------------------------------------------------------------------- #
# JSON extraction — tolerate fences / leading prose from the CLI path
# --------------------------------------------------------------------------- #
def _extract_json(raw: str) -> dict:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        a, b = s.find("{"), s.rfind("}")
        if a == -1 or b == -1:
            raise ValueError("no JSON object found in model output")
        return json.loads(s[a:b + 1])


# --------------------------------------------------------------------------- #
# Sanity gates — business rules Pydantic can't express. Failures -> repair.
# --------------------------------------------------------------------------- #
def _words(text: str) -> int:
    return len(text.split())


# --- fact-safety vocab (Phase 3.6 + 3.7) ---------------------------------- #
# Hedges = macro-risk language that softens a claim to its real certainty.
_HEDGES = (
    "could", "may ", "may,", "might", "expect", "forecast", "project", "estimat",
    "likely", "fear", "warn", "risk", "appear", "suggest", "reportedly",
    "potential", "would", "poised", "on track", "possibl", "seem", "set to",
    "if ", "some say", "some argue", "threaten", "on pace",
)
# Attribution = explicit sourced framing. Either a hedge OR attribution makes a
# claim "framed" (properly couched). Raw assertions have neither.
_ATTRIBUTION = (
    "according to", "analyst", "economist", "forecaster", "respondents say",
    "survey respondent", "the fed", "federal reserve", "central bank", "bls",
    "bureau of labor", "bea", "treasury", "cbo", "eia", "census", "reuters",
    "bloomberg", "wsj", "officials say", "official data", "data show",
    "data from", "report", "markets fear", "investors", "poll", "said it",
    "says it",
)
# Future / definitive certainty an unconfirmed claim must NOT use flatly.
_CERTAINTY = (
    "will ", "won't", "is going to", "are going to", "guarantee", "definitely",
    "certainly", "inevitable", "about to", "no doubt", "is set", "ensures",
)
# Causal assertions. Macro is multi-causal — these ALWAYS require attribution or
# hedging (no matter the confidence label), or the beat is rejected.
_CAUSAL = (
    "because of", "because ", "caused by", "caused the", "caused ", "causes ",
    "due to", "triggered", "led to", "leads to", "resulted in", "thanks to",
    "blamed on", "blame", "sparked by", "driven by", "drove ", "fueled by",
    "fueled ", "owing to", "traces to", "traces back to", "stems from",
    "comes down to", "boils down to", "points to", "behind the",
)
# Escalation events that must never be presented as fact unless confirmed+sourced.
_EVENTS = (
    "war", "invasion", "invaded", "nuclear", "airstrike", "missile strike",
    "collapse", "collapsed", "default", "defaulted", "bankrupt", "martial law",
    "coup", "attack on",
)
# Macro statistics / agencies — naming one implies a sourced claim.
_MACRO_ENTITIES = (
    "bls", "bureau of labor", "federal reserve", "the fed", "fed ", "treasury",
    "cpi", "ppi", "pce", "core inflation", "consumer price", "producer price",
    "michigan sentiment", "consumer sentiment", "university of michigan",
    "jobs report", "nonfarm", "unemployment rate", "jobless", "gdp",
    "oil price", "gas price", "gasoline", "crude", "barrel", "wti", "brent",
)

# --- spoken-number normalisation (Phase 3.8) ------------------------------- #
# Spelled-out numbers used to slip past the numeric guards ("three point eight
# percent"). We canonicalise them to digits BEFORE the credibility checks so the
# detector sees "3.8 percent", "44.8", "10 million". This only affects the text
# used for VALIDATION — the spoken narration is left natural for the TTS.
_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_SCALEWORDS = ("thousand", "million", "billion", "trillion")
_NUM_TOKENS = set(_ONES) | set(_TENS) | {"hundred", "point"} | set(_SCALEWORDS)
_NUM_RE = re.compile(
    r"\b(?:" + "|".join(sorted(_NUM_TOKENS, key=len, reverse=True)) + r")"
    r"(?:[\s-]+(?:" + "|".join(sorted(_NUM_TOKENS, key=len, reverse=True)) + r"))*\b",
    re.IGNORECASE,
)


def _run_to_digits(run: str) -> str:
    toks = [t for t in re.split(r"[\s-]+", run.lower()) if t]
    # only convert a run that actually contains a counting word
    if not any(t in _ONES or t in _TENS for t in toks):
        return run
    cur, dec, mags, in_dec = 0, "", [], False
    for w in toks:
        if w == "point":
            in_dec = True
        elif w in _SCALEWORDS:
            mags.append(w)
        elif in_dec:
            if w in _ONES:
                dec += str(_ONES[w])
        elif w == "hundred":
            cur = (cur or 1) * 100
        elif w in _TENS:
            cur += _TENS[w]
        elif w in _ONES:
            cur += _ONES[w]
    out = str(cur) + (f".{dec}" if dec else "")
    if mags:
        out += " " + " ".join(mags)
    return out


def _normalize_numbers(text: str) -> str:
    return _NUM_RE.sub(lambda m: _run_to_digits(m.group(0)), text)


# Macro numbers (after normalisation): percent / $ / magnitude / bps / decimals /
# comma-grouped or 5+ digit counts. Bare 4-digit numbers (years) are NOT flagged.
_MACRO_NUM = re.compile(
    r"\$\s?\d"
    r"|\d+(?:\.\d+)?\s?%"
    r"|\d+(?:\.\d+)?\s?percent"
    r"|\d+(?:\.\d+)?\s?(?:million|billion|trillion|thousand)"
    r"|\d+(?:\.\d+)?\s?(?:bps|basis points)"
    r"|\d+(?:\.\d+)?\s?dollars?"
    r"|\d+\.\d+"
    r"|\d{1,3}(?:,\d{3})+"
    r"|\d{5,}",
    re.IGNORECASE,
)


def _fact_safety(graph: SceneGraph) -> None:
    """Macro-credibility gate (Bloomberg / WSJ / Reuters, not TikTok conspiracy).
    Failures raise -> the engine's repair loop re-prompts the Director to rewrite
    the offending beat automatically."""
    for s in graph.scenes:
        conf = getattr(s, "confidence", "confirmed")
        # normalise spoken numbers FIRST so spelled-out figures can't slip past
        n = _normalize_numbers(s.narration.lower())
        hedged = any(h in n for h in _HEDGES)
        attributed = any(a in n for a in _ATTRIBUTION)
        framed = hedged or attributed          # claim is properly couched
        has_causal = any(c in n for c in _CAUSAL)
        has_certainty = any(c in n for c in _CERTAINTY)
        has_event = any(e in n for e in _EVENTS)
        has_source = any(o.type == "source" for o in s.overlays)
        has_stat = any(o.type == "stat" and o.sub for o in s.overlays)

        # 1) CAUSALITY — never imply cause unless attributed or hedged. Applies at
        #    EVERY confidence level: a sourced number does not license a raw cause.
        if has_causal and not framed:
            raise ValueError(
                f"scene {s.id} implies causality without sourcing. Macro is "
                "multi-causal — attribute it ('according to BLS', 'analysts say "
                "X may be contributing') or hedge it; never state cause as fact.")

        # 2) speculative claims MUST attribute/hedge the uncertainty
        if conf == "speculative" and not framed:
            raise ValueError(
                f"scene {s.id} is speculative but stated flatly. Use macro-risk "
                "framing — 'analysts warn' / 'markets fear' / 'economists expect' "
                "/ 'may' / 'could' — or downgrade the claim.")

        # 3) non-confirmed certainty/event claims must be framed
        if conf != "confirmed" and (has_certainty or has_event) and not framed:
            raise ValueError(
                f"scene {s.id} asserts a certain or geopolitical claim it can't "
                "confirm. Hedge/attribute it or only mark confirmed if sourced.")

        # 4) a confirmed major EVENT must be attributed (never fake a confirmed war)
        if conf == "confirmed" and has_event and not has_source and not attributed:
            raise ValueError(
                f"scene {s.id} states a major/geopolitical event as confirmed with "
                "no source. Cite a named source (overlay or 'according to ...') or "
                "set confidence to speculative and hedge it.")

        # 5) UNSUPPORTED NUMBERS — a %/$/bps figure needs a source overlay OR
        #    explicit attribution in the line ('according to BLS').
        if _MACRO_NUM.search(n) and not has_source and not attributed:
            raise ValueError(
                f"scene {s.id} states a macro number with no support. Add a named "
                "`source` overlay or attribute it in the line ('according to BLS').")

        # 6) confirmed stat overlay must be sourced
        if conf == "confirmed" and has_stat and not has_source:
            raise ValueError(
                f"scene {s.id} cites a confirmed number with no `source` overlay. "
                "Add a named source, or set confidence to 'probable' and phrase it "
                "as a forecast.")

        # 7) MACRO ENTITIES — naming a stat/agency (BLS, Fed, CPI, sentiment,
        #    oil/gas prices …) requires sourcing: a source overlay or attribution
        #    in the line (naming the Fed/BLS counts), or honest hedging.
        if any(e in n for e in _MACRO_ENTITIES) and not (has_source or framed):
            raise ValueError(
                f"scene {s.id} cites a macro statistic/agency (BLS, Fed, CPI, "
                "sentiment, oil/gas prices …) without support. Attribute it "
                "('according to BLS', 'the Fed said') or add a `source` overlay.")


def _sanity(graph: SceneGraph, spec: VideoSpec) -> None:
    sc = graph.scenes
    n = len(sc)
    total_words = sum(_words(s.narration) for s in sc)
    est_dur = total_words / WPS

    # pacing: scene count — fewer, longer beats (documentary, not rapid-fire)
    if not (4 <= n <= 7):
        raise ValueError(f"need 4-7 scenes for documentary pacing, got {n}")

    # length: real spoken estimate from word count (more honest than scene est.)
    if not (18 <= est_dur <= 50):
        raise ValueError(
            f"script is ~{est_dur:.0f}s ({total_words} words); target 20-45s. "
            f"Aim for {int(20*WPS)}-{int(45*WPS)} words total.")

    # word budgets
    if total_words < 45:
        raise ValueError(f"script too thin ({total_words} words); add substance")
    # per-scene word budgets. Non-hook beats need ~9 words (~3.5s at 2.6 w/s) so
    # strong b-roll HOLDS like a documentary instead of cutting fast. The hook
    # stays snappier (fast open), the body breathes.
    for i, s in enumerate(sc):
        w = _words(s.narration)
        if w > 34:
            raise ValueError(f"scene {s.id} is a monologue ({w} words); split it")
        floor = 4 if i == 0 else 9
        if w < floor:
            raise ValueError(
                f"scene {s.id} too short ({w} words); emotional/b-roll beats must "
                f"hold ~3.5s+ — give it at least {floor} words")

    # transition restraint: at most one whip/slide pivot in the whole video
    flashy = sum(1 for s in sc if s.transition_in in ("whip", "slide_l"))
    if flashy > 1:
        raise ValueError(
            f"{flashy} whip/slide transitions; use at most ONE deliberate pivot "
            "and `cut` (or one `fade`) everywhere else — no transition spam")

    # pacing: per-scene duration estimates
    if any(s.duration_sec > 7.0 for s in sc):
        raise ValueError("a scene exceeds 7s; shorten for retention")
    if _words(sc[0].narration) / WPS > 5.5:
        raise ValueError("opening scene is too long; hook must be fast (<=5.5s)")

    # hook
    hook = graph.meta.hook.strip()
    if not hook:
        raise ValueError("missing meta.hook")
    if _words(hook) > 10:
        raise ValueError(f"hook too long ({_words(hook)} words); <=10")

    # metadata
    if not graph.meta.title.strip():
        raise ValueError("missing meta.title")
    if len(graph.meta.title) > 100:
        raise ValueError("meta.title > 100 chars")

    # factual reliability (Phase 3.6) — runs last; failures trigger auto-rewrite
    _fact_safety(graph)
