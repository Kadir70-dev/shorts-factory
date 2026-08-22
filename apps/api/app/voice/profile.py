"""
The voice profile: one file that IS the channel's narrator.

config/voice/profile.yaml pins the cloned identity across every engine that can
carry it, plus the prosody and pronunciation rules that keep delivery consistent
from video #1 to video #5000. Nothing about the narrator is decided at render
time — that is the whole point. A voice that drifts is not an identity.

Three things live here:

  IDENTITY   — which engines hold a clone of this speaker, and their per-engine
               handles (an ElevenLabs voice id, a fine-tuned Piper checkpoint, a
               reference clip for zero-shot engines).

  PROSODY    — one locked speaking rate and per-engine expressiveness settings.
               Emotion in this pipeline comes from WRITING and MUSIC, not from
               swapping the narrator's character between videos.

  SPEAKABLE  — the text normalisation that turns written finance copy into
               something a TTS engine pronounces correctly and identically every
               time: "$4.2B" → "four point two billion dollars", "CPI" → "C P I",
               "2024" → "twenty twenty-four". Applied to a COPY of the narration;
               captions and overlays keep the written form.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..config import CONFIG_DIR, ROOT

# Engines that can carry a cloned identity, best-first. Order is the cascade.
CLONE_ENGINES = ("chatterbox", "openf5", "piper")
# Engines that CANNOT clone: fixed speaker embeddings, a different person from
# the enrolled narrator. Never part of `cascade()`, so `has_clone()` and every
# "(cloned)" label stay truthful. They are reachable only through
# `fallback_cascade()`, and only when the profile opts in per engine with
# `non_production: true` — a stock narrator must be a deliberate, visible choice.
NON_CLONE_ENGINES = ("kokoro",)
OPENF5_REPOSITORY = "mrfakename/OpenF5-TTS-Base"


@dataclass
class EngineBinding:
    """How one engine holds this voice."""
    name: str
    enabled: bool = True
    voice_id: str = ""                # ElevenLabs PVC id
    model_path: str = ""              # fine-tuned Piper .onnx
    reference_wav: str = ""           # zero-shot reference clip
    reference_text: str = ""          # transcript of the reference clip
    repository: str = ""
    config_path: str = ""
    vocab_path: str = ""
    voices_path: str = ""             # kokoro speaker-embedding bundle
    non_production: bool = False      # opt-in for a non-cloning stock engine
    settings: dict = field(default_factory=dict)

    def ready(self) -> tuple[bool, str]:
        """Is this binding usable right now → (ok, why not)."""
        if not self.enabled:
            return False, "disabled in profile"
        if self.name == "kokoro":
            if not self.non_production:
                return False, ("stock voice — set non_production: true to permit "
                               "a narrator who is not the enrolled identity")
            for label, value in (("model_path", self.model_path),
                                 ("voices_path", self.voices_path)):
                if not value or not _abs(value).exists():
                    return False, f"{label} missing at {_abs(value) if value else '<unset>'}"
            return True, ""
        if self.name == "piper":
            if not self.model_path:
                return False, "no model_path — fine-tune not installed"
            p = _abs(self.model_path)
            return (p.exists(), f"model missing at {p}")
        if self.name in ("chatterbox", "openf5"):
            if not self.reference_wav:
                return False, "no reference_wav"
            p = _abs(self.reference_wav)
            if not p.exists():
                return False, f"reference clip missing at {p}"
            python_bin = str(self.settings.get("python_bin", "") or "")
            if python_bin and not _abs(python_bin).is_file():
                return False, f"voice Python environment missing at {_abs(python_bin)}"
            if self.name == "openf5":
                if self.repository != OPENF5_REPOSITORY:
                    return False, ("repository must be " + OPENF5_REPOSITORY +
                                   " (the Apache-2.0 OpenF5 weights)")
                for label, value in (("model_path", self.model_path),
                                     ("config_path", self.config_path),
                                     ("vocab_path", self.vocab_path)):
                    if not value or not _abs(value).exists():
                        return False, f"{label} missing at {_abs(value) if value else '<unset>'}"
                if not self.reference_text.strip():
                    return False, "reference_text is required (ASR downloads are disabled)"
            return True, ""
        return False, "unknown engine"


@dataclass
class VoiceProfile:
    identity: str
    display_name: str
    locked: bool                      # refuse to ship a non-cloned voice
    speed: float
    engines: dict[str, EngineBinding]
    lexicon: dict[str, str]
    say_as: dict[str, str]
    sentence_pause_ms: int
    paragraph_pause_ms: int
    exists: bool = True

    # -- cascade ------------------------------------------------------------ #
    def cascade(self) -> list[str]:
        """Engines carrying THIS identity that are ready, in preference order."""
        out = []
        for name in CLONE_ENGINES:
            b = self.engines.get(name)
            if not b:
                continue
            ok, _ = b.ready()
            if ok:
                out.append(name)
        return out

    def fallback_cascade(self) -> list[str]:
        """Ready NON-cloning engines. A different speaker from the enrolled
        identity, so this is only consulted once `cascade()` is empty and the
        profile has explicitly permitted it."""
        out = []
        for name in NON_CLONE_ENGINES:
            b = self.engines.get(name)
            if b and b.ready()[0]:
                out.append(name)
        return out

    def diagnostics(self) -> list[str]:
        """Why each engine is or isn't available — the message a user needs when
        the render refuses to run."""
        lines = []
        for name in CLONE_ENGINES + NON_CLONE_ENGINES:
            b = self.engines.get(name)
            if not b:
                lines.append(f"  {name:12} not configured")
                continue
            ok, why = b.ready()
            lines.append(f"  {name:12} {'READY' if ok else 'unavailable — ' + why}")
        return lines

    def binding(self, name: str) -> EngineBinding | None:
        return self.engines.get(name)


def _abs(p: str) -> Path:
    path = Path(p).expanduser()
    return path if path.is_absolute() else (ROOT / path)


def profile_path() -> Path:
    return CONFIG_DIR / "voice" / "profile.yaml"


_EMPTY = VoiceProfile(
    identity="", display_name="", locked=True, speed=1.0, engines={}, lexicon={},
    say_as={}, sentence_pause_ms=0, paragraph_pause_ms=0, exists=False,
)


@functools.lru_cache(maxsize=1)
def load_profile() -> VoiceProfile:
    """Load config/voice/profile.yaml. Missing configuration is never synthesized."""
    path = profile_path()
    if not path.exists():
        return _EMPTY
    raw = yaml.safe_load(path.read_text()) or {}

    engines: dict[str, EngineBinding] = {}
    for name, spec in (raw.get("engines", {}) or {}).items():
        spec = spec or {}
        engines[name] = EngineBinding(
            name=name,
            enabled=bool(spec.get("enabled", True)),
            voice_id=str(spec.get("voice_id", "") or ""),
            model_path=str(spec.get("model_path", "") or ""),
            reference_wav=str(spec.get("reference_wav", "") or ""),
            reference_text=str(spec.get("reference_text", "") or ""),
            repository=str(spec.get("repository", "") or ""),
            config_path=str(spec.get("config_path", "") or ""),
            vocab_path=str(spec.get("vocab_path", "") or ""),
            voices_path=str(spec.get("voices_path", "") or ""),
            non_production=bool(spec.get("non_production", False)),
            settings=dict(spec.get("settings", {}) or {}),
        )

    prosody = raw.get("prosody", {}) or {}
    pron = raw.get("pronunciation", {}) or {}
    return VoiceProfile(
        identity=str(raw.get("identity", "") or ""),
        display_name=str(raw.get("display_name", "") or ""),
        locked=bool(raw.get("locked", True)),
        speed=float(prosody.get("speed", 1.0)),
        engines=engines,
        lexicon={str(k): str(v) for k, v in (pron.get("lexicon", {}) or {}).items()},
        say_as={str(k): str(v) for k, v in (pron.get("say_as", {}) or {}).items()},
        sentence_pause_ms=int(prosody.get("sentence_pause_ms", 0)),
        paragraph_pause_ms=int(prosody.get("paragraph_pause_ms", 0)),
    )


def has_clone() -> bool:
    p = load_profile()
    return p.exists and bool(p.cascade())


# --------------------------------------------------------------------------- #
# Speakable text
# --------------------------------------------------------------------------- #
_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]


def _int_words(n: int) -> str:
    """Spell an integer. TTS engines mostly handle digits, but they disagree with
    each other on grouping ("1,240" as twelve-forty vs one-thousand-two-hundred),
    and a narrator whose numbers change shape between engines is not one voice."""
    if n < 0:
        return "minus " + _int_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")
    if n < 1000:
        rest = f" {_int_words(n % 100)}" if n % 100 else ""
        return f"{_ONES[n // 100]} hundred{rest}"
    for scale, word in ((1_000_000_000_000, "trillion"),
                        (1_000_000_000, "billion"),
                        (1_000_000, "million"),
                        (1_000, "thousand")):
        if n >= scale:
            head = _int_words(n // scale)
            rest = f" {_int_words(n % scale)}" if n % scale else ""
            return f"{head} {word}{rest}"
    return str(n)


def _decimal_words(text: str) -> str:
    whole, _, frac = text.partition(".")
    out = _int_words(int(whole or 0))
    if frac:
        out += " point " + " ".join(_ONES[int(d)] for d in frac if d.isdigit())
    return out


_DECADE_PLURAL = {
    "twenty": "twenties", "thirty": "thirties", "forty": "forties",
    "fifty": "fifties", "sixty": "sixties", "seventy": "seventies",
    "eighty": "eighties", "ninety": "nineties", "ten": "tens",
}


def _decade_words(d: int) -> str:
    """"1980s" is "nineteen eighties", not "nineteen eightys". Naive pluralisation
    of the year words gets this wrong for every decade."""
    century, tens = divmod(d, 100)
    tens_word = _int_words(tens) if tens else ""
    plural = _DECADE_PLURAL.get(tens_word)
    if plural is None:
        # the decade IS the century: "1900s" → nineteen hundreds, but "2000s" is
        # said "two thousands", never "twenty hundreds"
        if century == 20:
            return "two thousands"
        return f"{_int_words(century)} hundreds" if century >= 10 else f"{_int_words(d)}s"
    head = (f"{_int_words(century)}" if century < 20
            else "two thousand" if century == 20 else _int_words(century))
    if century == 20:                       # 2010s → "twenty tens", not "two thousand tens"
        head = "twenty"
    return f"{head} {plural}"


def _year_words(y: int) -> str:
    """Years are spoken in pairs — "twenty twenty-four", not "two thousand and
    twenty-four" — except the 2000s decade, which genuinely is "two thousand X"."""
    if 1100 <= y <= 1999:
        return f"{_int_words(y // 100)} {_int_words(y % 100) if y % 100 else 'hundred'}"
    if 2000 <= y <= 2009:
        return f"two thousand{' ' + _int_words(y % 10) if y % 10 else ''}"
    if 2010 <= y <= 2099:
        return f"twenty {_int_words(y % 100)}"
    return _int_words(y)


_CURRENCY = {"$": "dollars", "€": "euros", "£": "pounds", "¥": "yen"}
_MAGS = {"k": "thousand", "m": "million", "b": "billion", "t": "trillion",
         "thousand": "thousand", "million": "million", "billion": "billion",
         "trillion": "trillion"}

# The optional space lives INSIDE the optional magnitude group. With `\s?(mag)?`
# the space is consumed even when no magnitude follows, welding the amount to the
# next word ("seventy-eight dollars forty-twoa barrel").
_RE_MONEY = re.compile(
    r"([$€£¥])\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(k|m|b|t|thousand|million|billion|trillion)\b)?", re.IGNORECASE)
_RE_PCT = re.compile(r"(\d+(?:\.\d+)?)\s?%")
_RE_MAGNUM = re.compile(
    r"\b(\d+(?:\.\d+)?)\s?(k|m|b|t)\b(?!\w)", re.IGNORECASE)
_RE_YEAR = re.compile(r"\b(1[1-9]\d{2}|20\d{2})\b")
_RE_DECADE = re.compile(r"\b(1[89]\d0|20[0-9]0)s\b")
_RE_NUM = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+\.\d+\b|\b\d{4,}\b")
_RE_ACRONYM = re.compile(r"\b([A-Z]{2,5})\b")


def _money(m: re.Match) -> str:
    unit = _CURRENCY.get(m.group(1), "dollars")
    amount = m.group(2).replace(",", "")
    mag = (m.group(3) or "").lower()
    words = _decimal_words(amount)
    if mag:
        return f"{words} {_MAGS.get(mag, mag)} {unit}"
    # cents: "$1.50" is "one dollar fifty", not "one point five zero dollars"
    if "." in amount:
        whole, frac = amount.split(".", 1)
        if len(frac) == 2 and int(whole or 0) < 1000:
            w = int(whole or 0)
            head = f"{_int_words(w)} {'dollar' if w == 1 else unit}"
            return head if frac == "00" else f"{head} {_int_words(int(frac))}"
    return f"{words} {unit}"


def speakable(text: str, profile: VoiceProfile | None = None) -> str:
    """Written finance copy → the exact words the narrator should say.

    Runs on a COPY: captions, overlays and the description keep the written form
    ("$4.2B"), while the voice says "four point two billion dollars". Doing this
    in the pipeline rather than leaving it to each engine's internal normaliser is
    what makes pronunciation identical across ElevenLabs and Piper — otherwise the
    same script is read two different ways depending on which tier ran.
    """
    p = profile or load_profile()
    # The repository-wide dictionary is shared by every engine. Profile entries
    # remain supported as channel-specific overrides layered on top.
    from .pronunciation import apply
    out = apply(text).text

    # 1) Explicit per-channel overrides win over every rule below.
    for src, dst in sorted(p.lexicon.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(rf"\b{re.escape(src)}\b", dst, out, flags=re.IGNORECASE)

    # 2) Money, percentages, magnitudes.
    out = _RE_MONEY.sub(_money, out)
    out = _RE_PCT.sub(lambda m: f"{_decimal_words(m.group(1))} percent", out)
    out = _RE_MAGNUM.sub(
        lambda m: f"{_decimal_words(m.group(1))} {_MAGS[m.group(2).lower()]}", out)

    # 3) Decades and years before generic numbers, so "1980s" isn't read digit-wise.
    out = _RE_DECADE.sub(lambda m: _decade_words(int(m.group(1))), out)
    out = _RE_YEAR.sub(lambda m: _year_words(int(m.group(1))), out)

    # 4) Remaining long or grouped numbers.
    def _num(m: re.Match) -> str:
        raw = m.group(0).replace(",", "")
        return _decimal_words(raw) if "." in raw else _int_words(int(raw))
    out = _RE_NUM.sub(_num, out)

    # 5) Acronyms the profile wants spelled out ("CPI" → "C P I"). Only those
    #    listed: blanket letter-spacing would wreck "NASA" and "OPEC".
    if p.say_as:
        def _acr(m: re.Match) -> str:
            return p.say_as.get(m.group(1), m.group(0))
        out = _RE_ACRONYM.sub(_acr, out)

    # 6) Pacing. A trailing period gives the engine a clean closing cadence.
    out = re.sub(r"\s+", " ", out).strip()
    if out and out[-1] not in ".!?":
        out += "."
    return out
