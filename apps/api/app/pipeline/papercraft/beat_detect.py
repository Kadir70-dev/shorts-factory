"""
Paper Craft — SceneGraph beat detection.

Deliberately narrow in scope: this does NOT introduce a new budget channel
(`pipeline/visual_budget.py`'s `CHANNELS` bands are proven-in-production and
out of scope for this change). Instead it looks at beats the allocator has
ALREADY assigned to "official" (real-document-shaped content) or "charts"
(figures/statistics) and asks a narrower question: given what this beat
ACTUALLY says, would a real laid-out document communicate it better than a
generic chart or an archival-photo search? If so, it builds the `DocumentSpec`
and the caller (`broll.py`) substitutes the renderer — the beat still counts
against the same budget share it was already allocated, so the report
percentages produced by `visual_budget.allocate()` don't move.
"""
from __future__ import annotations

from ..schemas.scene import Scene, SceneGraph
from .spec import Citation, DocumentSpec, Fact, Quote, Statistic

# Keyword signals per document type — matched against narration + entity/loc,
# not an ML classifier. Cheap, deterministic, auditable; matches the rest of
# this pipeline's editorial-heuristic style (see broll.py's _INTENT_TERMS).
_SIGNALS: dict[str, tuple[str, ...]] = {
    "financial_report": ("billion", "trillion", "percent", "rate", "inflation",
                         "deficit", "reserve", "gold", "dollar", "market", "$"),
    "breaking_news": ("announced", "breaking", "today", "confirmed", "emergency"),
    "archive_dossier": ("classified", "secret", "investigation", "raid", "federal",
                        "doj", "fbi", "case", "indictment"),
    "research_paper": ("study", "research", "according to", "data show", "economist"),
    "company_memo": ("memo", "internal", "company", "corporation", "board"),
    "evidence_board": ("evidence", "arrest", "charged", "court", "testimony"),
}


def is_eligible(scene: Scene) -> bool:
    """Only ever called for beats already on the 'official' or 'charts'
    channel — see the module docstring. Returns True when the beat's own
    content (a cited source, real numbers, or a strong document-type keyword
    signal) makes a document a better fit than that channel's default
    renderer."""
    if scene.overlays and any(o.type == "source" for o in scene.overlays):
        return True
    if scene.data is not None and getattr(scene, "nums", None):
        return True
    text = (scene.narration or "").lower()
    return any(kw in text for kw in
              (w for kws in _SIGNALS.values() for w in kws))


def classify(scene: Scene) -> str:
    """Which of the 10 templates fits this beat best. Falls back to
    `archive_dossier` — a generic official-document look — when no keyword
    signal is strong enough to pick a more specific one."""
    text = (scene.narration or "").lower()
    scores = {doc_type: sum(1 for kw in kws if kw in text)
             for doc_type, kws in _SIGNALS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "financial_report" if (scene.data is not None) else "archive_dossier"
    return best


def build_spec(scene: Scene, graph: SceneGraph, document_type: str) -> DocumentSpec:
    source_overlay = next((o for o in scene.overlays if o.type == "source"), None)
    quote_overlay = next((o for o in scene.overlays if o.type == "quote"), None)
    headline = next((o.text for o in scene.overlays if o.type in ("headline", "lower_third")),
                    scene.narration[:80])

    citations = [Citation(label=source_overlay.text)] if source_overlay else []
    facts = [Fact(text=scene.narration,
                  citation=citations[0] if citations else None)]
    statistics = []
    if scene.data is not None:
        for p in getattr(scene.data, "points", [])[:6]:
            label = getattr(p, "label", "")
            value = getattr(p, "value", "")
            if label:
                statistics.append(Statistic(
                    label=str(label), value=str(value),
                    citation=citations[0] if citations else None))
    quotes = []
    if quote_overlay:
        quotes.append(Quote(text=quote_overlay.text, attribution=quote_overlay.sub or ""))

    return DocumentSpec(
        document_type=document_type,        # type: ignore[arg-type]
        title=headline,
        subtitle=getattr(scene, "location", "") or "",
        body=scene.narration,
        dates=[str(scene.year)] if getattr(scene, "year", None) else [],
        facts=facts,
        quotes=quotes,
        statistics=statistics,
        citations=citations,
        duration_sec=scene.duration_sec,
        camera_movement="slow_zoom",
        editorial_reconstruction=True,       # a recreated period document by default
    )
