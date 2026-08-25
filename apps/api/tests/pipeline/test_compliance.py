"""Monetisation safety.

Two failure modes matter here and they pull against each other: letting risky
wording through, and mangling legitimate copy. The narration is SPOKEN, so a
rewrite that leaves an ungrammatical sentence is a real defect, not a cosmetic
one — several of these tests exist because early versions produced word salad.
"""
from __future__ import annotations

import re

import pytest

from app.pipeline import compliance as C
from app.schemas.scene import Overlay


# --------------------------------------------------------------------------- #
# The phrases the brief named explicitly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("banned", [
    "guaranteed", "risk-free", "get rich", "best stock to buy", "buy now",
    "easy money",
])
def test_named_banned_phrases_are_rewritten(banned):
    text = f"This is {banned} territory."
    out, notes = C.rewrite(text)
    assert banned.lower() not in out.lower(), f"{banned!r} survived: {out!r}"
    assert notes, f"{banned!r} was changed without recording why"


def test_rewrites_explain_themselves():
    out, notes = C.rewrite("A guaranteed, risk-free return.")
    assert len(notes) >= 2
    assert all("→" in n and "(" in n for n in notes), (
        "each note must name the substitution and its reason")


# --------------------------------------------------------------------------- #
# Not mangling legitimate copy
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("clean", [
    "Costco has kept the hot dog at $1.50 since 1985, a 37% real price cut.",
    "According to BLS data, CPI rose 3.4% year over year.",
    "Analysts say the Fed may cut rates before the end of the year.",
    "The company reported $4.2B in revenue, up 12% from last year.",
    "Between 2019 and 2024 the median home price rose from $274,600 to $419,200.",
])
def test_legitimate_finance_copy_is_untouched(clean):
    out, notes = C.rewrite(clean)
    assert out == clean, f"rewrote clean copy: {out!r}"
    assert not notes


def test_rewrites_stay_grammatical():
    """Substitutions must slot into the original's grammatical role — this output
    gets read aloud, where a broken article or a doubled hedge is obvious."""
    cases = {
        "It is a total scam.": r"^It is an alleged scam\.$",
        "This company ran a ponzi.": r"an alleged Ponzi scheme",
        "Do not miss out on this last chance.": r"^This is worth understanding\.$",
    }
    for src, pattern in cases.items():
        out, _ = C.rewrite(src)
        assert re.search(pattern, out), f"{src!r} → {out!r}"
        assert "  " not in out, f"double space in {out!r}"
        assert not re.search(r"\ba [aeiou]", out), f"broken article in {out!r}"


def test_a_rewrite_does_not_re_fire_on_its_own_output():
    out, _ = C.rewrite("It is a total scam.")
    assert out.lower().count("alleged") == 1, f"hedge applied twice: {out!r}"


# --------------------------------------------------------------------------- #
# Escalation
# --------------------------------------------------------------------------- #
def test_unrewritable_advice_is_flagged_not_patched():
    violations, _ = C.check("I recommend this stock with a price target of $400.")
    assert len(violations) >= 2
    assert any("recommend" in v for v in violations)
    assert any("price target" in v for v in violations)


def test_a_wholly_promotional_line_is_escalated(graph):
    graph.scenes[0].narration = (
        "This guaranteed, risk-free play will make you rich with easy money.")
    report = C.apply(graph, strict=False)
    assert not report.passed, (
        "a line needing this many patches should go back to the Director, not "
        "be stitched together phrase by phrase")


def test_strict_mode_raises_for_the_repair_loop(graph):
    graph.scenes[0].narration = "I recommend this stock."
    with pytest.raises(ValueError, match="compliance gate"):
        C.apply(graph, strict=True)


def test_advisories_do_not_block(graph):
    graph.scenes[0].narration = "The bank went bankrupt after the fraud case."
    report = C.apply(graph, strict=False)
    assert report.passed, "advisories are informational, not blocking"
    assert report.advisories


# --------------------------------------------------------------------------- #
# Disclaimer
# --------------------------------------------------------------------------- #
def test_disclaimer_is_attached_to_the_graph(graph):
    C.apply(graph, strict=False)
    assert "not financial advice" in graph.meta.disclaimer.lower()
    assert "educational" in graph.meta.disclaimer.lower()


def test_description_leads_with_the_disclaimer(graph):
    C.apply(graph, strict=False)
    desc = C.description_block(graph, "How a loss-making hot dog works.")
    first_line = desc.splitlines()[0]
    assert "not financial advice" in first_line.lower(), (
        "a disclaimer below the fold is one a reviewer will not read")


def test_compliance_covers_overlays_and_metadata(graph):
    graph.scenes[0].overlays.append(
        Overlay(type="headline", text="Guaranteed returns"))
    graph.meta.title = "The best stock to buy now"
    C.apply(graph, strict=False)
    assert "guaranteed" not in graph.scenes[0].overlays[-1].text.lower()
    assert "best stock to buy" not in graph.meta.title.lower()


# --------------------------------------------------------------------------- #
# AI / synthetic content disclosure
# --------------------------------------------------------------------------- #
def test_realistic_ai_people_trigger_disclosure(graph):
    s = graph.scenes[0]
    s.visual.type = "ai_image"
    s.visual.strategy = "ai_image"
    s.visual.visual_intent = "the president at a press conference, photorealistic"
    needs, reasons = C.scan_ai_disclosure(graph)
    assert needs and reasons


def test_charts_and_plates_do_not_trigger_disclosure(graph):
    for s in graph.scenes:
        s.visual.type = "dataviz"
        s.visual.strategy = "dataviz"
    needs, reasons = C.scan_ai_disclosure(graph)
    assert not needs, f"a chart is not synthetic media: {reasons}"


def test_real_footage_does_not_trigger_disclosure(graph):
    for s in graph.scenes:
        s.visual.type = "broll"
        s.visual.strategy = "real"
        s.visual.visual_intent = "a crowd of shoppers at a checkout"
    needs, _ = C.scan_ai_disclosure(graph)
    assert not needs


def test_disclosure_produces_an_actionable_reminder(graph):
    s = graph.scenes[0]
    s.visual.type = "ai_image"
    s.visual.visual_intent = "photorealistic courtroom reenactment"
    C.apply(graph, strict=False)
    checklist = C.publish_checklist(graph)
    assert checklist
    assert any("Altered or Synthetic Content" in line for line in checklist), (
        "the reminder must name the actual YouTube setting to tick")
