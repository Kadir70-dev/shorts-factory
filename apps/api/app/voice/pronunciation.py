"""
Pronunciation dictionary — the layer that keeps the narrator's vocabulary stable.

Neural TTS engines guess at proper nouns, and they guess DIFFERENTLY from each
other. Chatterbox and F5 will not agree on "NVDA", "EBITDA" or "Jensen Huang",
which means the same script read by two engines produces two narrators. Since the
whole point of this pipeline is one consistent cloned voice, pronunciation has to
be resolved BEFORE the audio engine sees the text — not left to whichever model
happened to render a given short.

Applied to a COPY of the narration. The written form is untouched, so the screen
still shows "$NVDA" and "EBITDA" while the voice says "en-vidia" and "ee-bit-dah".

Section order is deliberate and longest-match-first within each section:

    phrases → companies → people → tickers → terms → letters

with an EXCLUSION SET carried between them: once a span of text has been rewritten
by an earlier section, later sections cannot touch it. Without that, "S&P 500"
becomes "S and P five hundred" and then the bare-ticker pass tries to read the
"P" as a symbol.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..config import CONFIG_DIR

_FILE = CONFIG_DIR / "voice" / "pronunciation.yaml"

# $AAPL / $BRK.B  ·  NASDAQ:AAPL / NYSE:BRK.B
_RE_CASHTAG = re.compile(r"\$([A-Z]{1,5})(?:\.([A-Z]))?\b")
_RE_EXCHANGE = re.compile(
    r"\b(?:NASDAQ|NYSE|AMEX|LSE|TSX|BSE|NSE)\s*:\s*([A-Z]{1,5})(?:\.([A-Z]))?\b")
# A bare uppercase run is only a ticker if it is whitelisted — otherwise "CEO",
# "GDP" and "USA" all get read as stock symbols.
_RE_BARE = re.compile(r"\b([A-Z]{2,5})\b")


@dataclass
class Dictionary:
    phrases: dict[str, str] = field(default_factory=dict)
    companies: dict[str, str] = field(default_factory=dict)
    people: dict[str, str] = field(default_factory=dict)
    tickers: dict[str, str] = field(default_factory=dict)
    terms: dict[str, str] = field(default_factory=dict)
    letters: dict[str, str] = field(default_factory=dict)
    ticker_whitelist: set[str] = field(default_factory=set)
    exists: bool = True

    def entry_count(self) -> int:
        return sum(len(d) for d in (self.phrases, self.companies, self.people,
                                    self.tickers, self.terms, self.letters))

    # -- lookups ---------------------------------------------------------- #
    def say_ticker(self, symbol: str, cls: str = "") -> str:
        """How to speak a symbol. Unlisted symbols go letter-by-letter, which is
        right for most of them ('PLTR' → 'P L T R')."""
        base = self.tickers.get(symbol.upper())
        if base is None:
            base = " ".join(symbol.upper())
        if cls:
            base = f"{base} class {cls.upper()}"
        return base


def _lower_keys(d: dict | None) -> dict[str, str]:
    return {str(k): str(v) for k, v in (d or {}).items()}


@functools.lru_cache(maxsize=1)
def load(path: Path | None = None) -> Dictionary:
    """Load config/voice/pronunciation.yaml. A missing file is not fatal — the
    pipeline just loses pronunciation control, which degrades quality rather than
    breaking the render."""
    p = path or _FILE
    if not p.exists():
        return Dictionary(exists=False)
    raw = yaml.safe_load(p.read_text()) or {}
    return Dictionary(
        phrases=_lower_keys(raw.get("phrases")),
        companies=_lower_keys(raw.get("companies")),
        people=_lower_keys(raw.get("people")),
        tickers=_lower_keys(raw.get("tickers")),
        terms=_lower_keys(raw.get("terms")),
        letters=_lower_keys(raw.get("letters")),
        ticker_whitelist={str(t).upper() for t in (raw.get("ticker_whitelist") or [])},
    )


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
class _Guard:
    """Tracks which character spans have already been rewritten.

    Phrase-level substitution without this is subtly broken: an earlier rule
    produces text that a later rule then matches inside, and the result is a
    double-translation nobody wrote. The guard makes each span authoritative once
    it has been claimed.
    """

    def __init__(self, text: str):
        self.text = text
        self.claimed: list[tuple[int, int]] = []

    def free(self, start: int, end: int) -> bool:
        return not any(s < end and start < e for s, e in self.claimed)

    def substitute(self, pattern: re.Pattern, repl) -> int:
        """Apply `repl` to every non-overlapping, unclaimed match. Returns the
        number of substitutions made."""
        out: list[str] = []
        cursor = 0
        n = 0
        new_claims: list[tuple[int, int]] = []
        for m in pattern.finditer(self.text):
            if not self.free(m.start(), m.end()):
                continue
            replacement = repl(m)
            if replacement is None:
                continue
            out.append(self.text[cursor:m.start()])
            start_in_new = sum(len(x) for x in out)
            out.append(replacement)
            new_claims.append((start_in_new, start_in_new + len(replacement)))
            cursor = m.end()
            n += 1
        if not n:
            return 0
        out.append(self.text[cursor:])
        # Claims are recorded against the NEW string, so recompute the old ones
        # by walking the same offsets — simplest correct approach is to rebuild.
        self.text = "".join(out)
        self.claimed = _merge(self.claimed_shifted(new_claims))
        return n

    def claimed_shifted(self, new_claims: list[tuple[int, int]]) -> list[tuple[int, int]]:
        return sorted(new_claims)


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _word_pattern(term: str) -> re.Pattern:
    """Whole-word match that tolerates the punctuation these terms actually carry
    ('S&P 500', '401(k)', 'P/E', '10-K'). `\\b` alone fails on all of them."""
    escaped = re.escape(term)
    lead = r"(?<![\w&$])" if term[:1].isalnum() else r"(?<![\w])"
    trail = r"(?![\w])" if term[-1:].isalnum() else ""
    return re.compile(lead + escaped + trail, re.IGNORECASE)


@dataclass
class Applied:
    text: str
    hits: dict[str, int] = field(default_factory=dict)   # section → count
    terms_used: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.hits.values())


def apply(text: str, dictionary: Dictionary | None = None) -> Applied:
    """Rewrite one line into its spoken form → (text, what fired).

    The report is returned rather than logged because voice QA uses it to check
    that terms which SHOULD have been translated actually were — a silent miss
    here is a mispronounced ticker in a published video.
    """
    d = dictionary or load()
    if not text or not d.exists:
        return Applied(text=text)

    guard = _Guard(text)
    hits: dict[str, int] = {}
    used: list[str] = []

    def run_section(name: str, mapping: dict[str, str]) -> None:
        count = 0
        # Longest first: "S&P 500" must win over "S&P".
        for term in sorted(mapping, key=len, reverse=True):
            spoken = mapping[term]
            n = guard.substitute(_word_pattern(term), lambda m, s=spoken: s)
            if n:
                count += n
                used.append(term)
        if count:
            hits[name] = count

    run_section("phrases", d.phrases)
    run_section("companies", d.companies)
    run_section("people", d.people)

    # --- tickers -------------------------------------------------------- #
    tick = 0
    tick += guard.substitute(
        _RE_EXCHANGE, lambda m: d.say_ticker(m.group(1), m.group(2) or ""))
    tick += guard.substitute(
        _RE_CASHTAG, lambda m: d.say_ticker(m.group(1), m.group(2) or ""))

    def _bare(m: re.Match) -> str | None:
        sym = m.group(1)
        if sym.upper() not in d.ticker_whitelist:
            return None          # not a ticker — leave for terms/letters
        return d.say_ticker(sym)

    tick += guard.substitute(_RE_BARE, _bare)
    if tick:
        hits["tickers"] = tick

    run_section("terms", d.terms)
    run_section("letters", d.letters)

    return Applied(text=guard.text, hits=hits, terms_used=used)


def find_untranslated(text: str, dictionary: Dictionary | None = None) -> list[str]:
    """Uppercase tokens left after the dictionary ran.

    These are the pronunciation risks: a symbol or acronym the dictionary has
    never seen, which each engine will improvise differently. Voice QA reports
    them so the dictionary can grow from real scripts instead of guesswork.
    """
    d = dictionary or load()
    known = set()
    for mapping in (d.phrases, d.companies, d.people, d.tickers, d.terms, d.letters):
        known |= {k.upper() for k in mapping}
    known |= d.ticker_whitelist

    out: list[str] = []
    for m in re.finditer(r"\b([A-Z]{2,6})\b", text):
        tok = m.group(1)
        if tok.upper() in known or tok in out:
            continue
        out.append(tok)
    return out
