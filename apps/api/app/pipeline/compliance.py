"""
Monetisation safety — the gate between "a good video" and "a video that survives
YouTube Partner Program review and keeps advertisers on it".

Three jobs, all driven by config/compliance.yaml so the policy is editable
without touching code:

  1. REWRITE risky wording automatically. "Guaranteed", "risk-free", "get rich",
     "best stock to buy", "buy now", "easy money" and their relatives are
     replaced with descriptive equivalents. Every substitution is recorded on the
     graph so a reviewer can see what changed and why — a compliance layer that
     edits silently is one you stop trusting.

  2. FLAG what must not be auto-rewritten. Deleting or reshaping a claim can
     change its meaning, so first-person recommendations and price targets FAIL
     the gate and go back through the Director's repair loop for a real rewrite.

  3. DISCLOSE. The educational disclaimer is attached for burn-in and for the
     description, and the graph is scanned for AI-generated imagery that could be
     mistaken for real people or events — which YouTube requires the uploader to
     declare. The pipeline cannot tick that box, so it makes the reminder
     impossible to miss instead.

Deliberately NOT a censor. It runs on the script the Director wrote, keeps the
meaning, and only escalates when keeping the meaning requires a human/LLM rewrite.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field

import yaml

from ..config import CONFIG_DIR
from ..schemas.scene import SceneGraph

_FILE = CONFIG_DIR / "compliance.yaml"


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern
    replace: str
    reason: str
    source: str                    # the raw pattern, for readable reporting


@dataclass
class Policy:
    disclaimer_short: str
    disclaimer_long: str
    show_early: bool
    show_on_outro: bool
    rewrites: list[Rule]
    flags: list[Rule]
    advisories: list[Rule]
    realistic_subjects: tuple[str, ...]
    photoreal_markers: tuple[str, ...]
    ai_reminder: str


@dataclass
class ComplianceReport:
    """What the pass did. Persisted next to the render as an audit artifact."""
    rewrites: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)
    ai_disclosure: bool = False
    ai_reasons: list[str] = field(default_factory=list)
    disclaimer: str = ""

    @property
    def passed(self) -> bool:
        return not self.violations

    def format(self) -> str:
        out = [f"compliance: {'PASS' if self.passed else 'BLOCKED'}"]
        if self.rewrites:
            out.append(f"  {len(self.rewrites)} automatic rewrite(s):")
            out += [f"    · {r}" for r in self.rewrites]
        if self.violations:
            out.append("  MUST be rewritten by the Director:")
            out += [f"    ✗ {v}" for v in self.violations]
        if self.advisories:
            out.append("  advertiser-suitability notes:")
            out += [f"    ! {a}" for a in self.advisories]
        if self.ai_disclosure:
            out.append("  ⚠ AI/SYNTHETIC CONTENT DISCLOSURE REQUIRED:")
            out += [f"    · {r}" for r in self.ai_reasons]
        return "\n".join(out)


# --------------------------------------------------------------------------- #
# Policy loading
# --------------------------------------------------------------------------- #
def _rules(entries, default_replace: str = "") -> list[Rule]:
    out: list[Rule] = []
    for e in entries or []:
        pat = e.get("pattern")
        if not pat:
            continue
        try:
            rx = re.compile(pat, re.IGNORECASE)
        except re.error as err:                # a bad rule must not brick the run
            print(f"[compliance] skipping invalid pattern {pat!r}: {err}",
                  flush=True)
            continue
        out.append(Rule(pattern=rx,
                        replace=e.get("replace", default_replace),
                        reason=e.get("reason") or e.get("note", ""),
                        source=pat))
    return out


@functools.lru_cache(maxsize=1)
def policy() -> Policy:
    raw = yaml.safe_load(_FILE.read_text()) if _FILE.exists() else {}
    d = raw.get("disclaimer", {}) or {}
    ai = raw.get("ai_disclosure", {}) or {}
    return Policy(
        disclaimer_short=(d.get("short")
                          or "Educational purposes only. Not financial advice."),
        disclaimer_long=(d.get("long") or d.get("short") or "").strip(),
        show_early=bool(d.get("show_early", True)),
        show_on_outro=bool(d.get("show_on_outro", True)),
        rewrites=_rules(raw.get("rewrites")),
        flags=_rules(raw.get("flags")),
        advisories=_rules(raw.get("advisories")),
        realistic_subjects=tuple(ai.get("realistic_subjects", []) or []),
        photoreal_markers=tuple(ai.get("photoreal_markers", []) or []),
        ai_reminder=(ai.get("reminder") or "").strip(),
    )


# --------------------------------------------------------------------------- #
# Text passes
# --------------------------------------------------------------------------- #
def _match_case(original: str, replacement: str) -> str:
    """Preserve the original's capitalisation shape so a rewrite doesn't leave a
    lowercase word at the start of a spoken sentence."""
    if original.isupper() and len(original) > 3:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def rewrite(text: str, pol: Policy | None = None) -> tuple[str, list[str]]:
    """Apply every rewrite rule to one string → (clean text, notes)."""
    if not text:
        return text, []
    pol = pol or policy()
    notes: list[str] = []
    out = text
    for rule in pol.rewrites:
        def _sub(m: re.Match) -> str:
            hit = m.group(0)
            try:
                repl = m.expand(rule.replace)
            except re.error:
                repl = rule.replace
            notes.append(f"{hit!r} → {repl!r} ({rule.reason})")
            return _match_case(hit, repl)
        out = rule.pattern.sub(_sub, out)
    # rewrites can leave doubled spaces where a phrase shortened
    out = re.sub(r"[ \t]{2,}", " ", out).strip()
    return _tidy(out), notes


_A_AN = re.compile(r"\b([Aa])n?\s+(?=([aeiouAEIOU]))")
_AN_A = re.compile(r"\b([Aa])n\s+(?=[^aeiouAEIOU\W\d])")


def _tidy(text: str) -> str:
    """Repair the grammar a substitution can break.

    A replacement changes the following word's initial sound, so "a scam" →
    "a alleged scam". Silent on screen, obvious in a voiceover — and the whole
    point of this module is that the output still sounds like a person wrote it.
    """
    out = _A_AN.sub(lambda m: f"{m.group(1)}n ", text)
    out = _AN_A.sub(lambda m: f"{m.group(1)} ", out)
    return re.sub(r"\s+([.,;:!?])", r"\1", out)


def check(text: str, pol: Policy | None = None) -> tuple[list[str], list[str]]:
    """Scan one string → (blocking violations, non-blocking advisories)."""
    if not text:
        return [], []
    pol = pol or policy()
    violations = [f"{m.group(0)!r}: {r.reason}"
                  for r in pol.flags for m in r.pattern.finditer(text)]
    advisories = [f"{m.group(0)!r}: {r.reason}"
                  for r in pol.advisories for m in r.pattern.finditer(text)]
    return violations, advisories


# --------------------------------------------------------------------------- #
# AI / synthetic content disclosure
# --------------------------------------------------------------------------- #
def scan_ai_disclosure(graph: SceneGraph,
                       pol: Policy | None = None) -> tuple[bool, list[str]]:
    """Decide whether this video needs YouTube's synthetic-content disclosure.

    The test is not "did we use AI" — charts, gradients and stylised plates never
    require disclosure. It is "could a viewer believe this AI-generated frame
    shows a real person or a real event", so we look for a beat that BOTH resolved
    to a generated visual AND depicts a realistic subject or was prompted for
    photorealism.
    """
    pol = pol or policy()
    reasons: list[str] = []
    for scene in graph.scenes:
        v = scene.visual
        generated = v.type in ("ai_image", "ai_video") or v.strategy in (
            "ai_image", "ai_video", "hybrid")
        gen_layers = [ly for ly in v.layers if ly.kind == "ai_image"]
        if not generated and not gen_layers:
            continue
        prompt = " ".join([v.visual_intent, v.query,
                           *(ly.prompt for ly in gen_layers)]).lower()
        subject = " ".join([prompt, scene.narration]).lower()

        hits = [s for s in pol.realistic_subjects if s in subject]
        photoreal = [m for m in pol.photoreal_markers if m in prompt]
        if hits:
            reasons.append(
                f"{scene.id}: AI visual depicting {', '.join(sorted(set(hits))[:3])}")
        elif photoreal:
            reasons.append(
                f"{scene.id}: AI visual prompted for photorealism "
                f"({photoreal[0]})")
    return bool(reasons), reasons


# --------------------------------------------------------------------------- #
# Pipeline stage
# --------------------------------------------------------------------------- #
_TEXT_FIELDS = ("title", "hook", "description", "thumbnail_text")

# A line needing this many substitutions isn't a wording slip — the whole beat was
# written in promotional register. Phrase-level patching of such a line reliably
# produces something ungrammatical, and unlike on-screen text this gets SPOKEN, so
# we escalate to a real Director rewrite instead of shipping word salad.
MAX_REWRITES_PER_LINE = 3


def apply(graph: SceneGraph, strict: bool = True) -> ComplianceReport:
    """Run the whole safety pass over a SceneGraph, in place.

    `strict` decides what a flagged phrase means: True (the Director's repair
    loop) raises so the script is genuinely rewritten; False (the render path,
    after the Director has had its chances) records the violation and continues,
    because a blocked render at 3am helps nobody when the disclaimer and rewrites
    have already been applied.
    """
    pol = policy()
    rep = ComplianceReport(disclaimer=pol.disclaimer_short)

    def scrub(text: str, where: str, spoken: bool = False) -> str:
        clean, notes = rewrite(text, pol)
        rep.rewrites += [f"{where}: {n}" for n in notes]
        v, a = check(clean, pol)
        rep.violations += [f"{where}: {x}" for x in v]
        rep.advisories += [f"{where}: {x}" for x in a]
        if spoken and len(notes) >= MAX_REWRITES_PER_LINE:
            rep.violations.append(
                f"{where}: {len(notes)} risky phrases in one spoken line — "
                "rewrite the whole beat descriptively rather than patching it")
        return clean

    for scene in graph.scenes:
        scene.narration = scrub(scene.narration, scene.id, spoken=True)
        for ov in scene.overlays:
            ov.text = scrub(ov.text, f"{scene.id}.{ov.type}")
            if ov.sub:
                ov.sub = scrub(ov.sub, f"{scene.id}.{ov.type}.sub")
        if scene.data:
            scene.data.title = scrub(scene.data.title, f"{scene.id}.chart")
            scene.data.note = scrub(scene.data.note, f"{scene.id}.chart.note")

    m = graph.meta
    for field_name in _TEXT_FIELDS:
        setattr(m, field_name, scrub(getattr(m, field_name, "") or "",
                                     f"meta.{field_name}"))
    m.tags = [scrub(t, "meta.tags") for t in m.tags]

    # disclosure + disclaimer land on the graph so the renderer and the metadata
    # builder read the SAME values — they must never disagree.
    m.disclaimer = pol.disclaimer_short
    m.compliance_notes = list(rep.rewrites)
    needs, reasons = scan_ai_disclosure(graph, pol)
    m.requires_ai_disclosure = needs
    m.ai_disclosure_reasons = reasons
    rep.ai_disclosure = needs
    rep.ai_reasons = reasons

    if strict and rep.violations:
        raise ValueError(
            "compliance gate: " + "; ".join(rep.violations[:4])
            + ". Rewrite these lines descriptively — state what happened or what "
              "others did, never what the viewer should do.")
    return rep


def description_block(graph: SceneGraph, base: str) -> str:
    """Assemble the upload description with the disclaimer FIRST.

    Above the fold matters: a disclaimer buried under hashtags is one a reviewer
    scrolling the first two lines will not see.
    """
    pol = policy()
    parts = [pol.disclaimer_short, "", base.strip()]
    if pol.disclaimer_long and pol.disclaimer_long != pol.disclaimer_short:
        parts += ["", pol.disclaimer_long]
    if graph.meta.requires_ai_disclosure:
        parts += ["", "Contains AI-generated imagery."]
    return "\n".join(p for p in parts if p is not None).strip()


def publish_checklist(graph: SceneGraph) -> list[str]:
    """Human-facing pre-publish reminders, printed at the end of a render."""
    pol = policy()
    out: list[str] = []
    if graph.meta.requires_ai_disclosure:
        out.append(pol.ai_reminder or
                   "Enable YouTube's 'Altered or Synthetic Content' disclosure.")
        out += [f"  · {r}" for r in graph.meta.ai_disclosure_reasons]
    return out
