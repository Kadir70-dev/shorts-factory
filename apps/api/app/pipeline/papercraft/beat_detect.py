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

import re

from ...schemas.scene import Scene, SceneGraph, StoryboardScene
from ..dataviz import format_value
from .spec import Citation, DocumentSpec, Fact, Quote, Statistic

_HEADLINE_CHARS = 92  # fits ~3-4 wrapped lines in every template's title frame

# A bare 4-digit year in the narration itself ("...in 1952, the Treasury...").
# `Scene` carries no year/date field of its own — only `StoryboardScene` does
# (`location`/`year`), and that's only populated when the gated storyboard
# engine ran. This is the fallback for when it didn't.
_YEAR_RE = re.compile(r"\b(1[5-9]\d{2}|20[0-2]\d)\b")


def _storyboard_meta(scene: Scene, graph: SceneGraph) -> StoryboardScene | None:
    """The matching `StoryboardScene`, if the storyboard engine ran for this
    beat — it, not `Scene`, is where `year`/`location` actually live."""
    if graph.storyboard is None:
        return None
    return next((b for b in graph.storyboard.scenes if b.source_scene_id == scene.id), None)


def _beat_year(scene: Scene, graph: SceneGraph) -> int | None:
    beat = _storyboard_meta(scene, graph)
    if beat and beat.year:
        return beat.year
    match = _YEAR_RE.search(scene.narration or "")
    return int(match.group()) if match else None

# Keyword signals per document type — matched against narration + entity/loc,
# not an ML classifier. Cheap, deterministic, auditable; matches the rest of
# this pipeline's editorial-heuristic style (see broll.py's _INTENT_TERMS).
_SIGNALS: dict[str, tuple[str, ...]] = {
    "financial_report": ("billion", "trillion", "percent", "rate", "inflation",
                         "deficit", "reserve", "gold", "dollar", "market", "$"),
    "breaking_news": ("announced", "breaking", "today", "confirmed", "emergency"),
    "archive_dossier": ("classified", "secret", "investigation", "raid", "federal",
                        "doj", "fbi", "case", "indictment", "indicted",
                        "justice department", "pleaded guilty", "prosecut"),
    "research_paper": ("study", "research", "according to", "data show", "economist"),
    "company_memo": ("memo", "internal", "company", "corporation", "board"),
    "evidence_board": ("evidence", "arrest", "charged", "court", "testimony"),
    "historical_document": ("declaration", "treaty", "founding", "constitution",
                            "colonial", "revolution", "manuscript", "proclamation",
                            "monarchy", "empire"),
    "magazine_feature": ("profile", "feature story", "interview", "spotlight",
                         "behind the scenes", "in-depth", "portrait", "lifestyle"),
    "modern_newspaper": ("reported", "spokesperson", "press conference",
                        "officials said", "newspaper", "editorial"),
    "news_clipping": ("clipping", "clipped", "wire report", "dispatch",
                      "excerpt", "bulletin"),
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


def classify(scene: Scene, graph: SceneGraph) -> str:
    """Which of the 11 templates fits this beat best.

    Every template is reachable: 9 have direct keyword signals above;
    `vintage_newspaper` and `historical_document` are reached by taking a
    beat that already scored as `modern_newspaper`/`archive_dossier` and
    swapping in the period-appropriate sibling when the beat's own year
    (storyboard metadata, or else a bare 4-digit year in the narration) is
    well before living memory, rather than duplicating near-identical
    keywords under a second key. Falls back to `financial_report` when the
    beat carries chart data, `news_clipping` for a very short beat (a full
    front page reads oddly empty for one line), else `modern_newspaper` — a
    plain, generic "printed page" look."""
    text = (scene.narration or "").lower()
    scores = {doc_type: sum(1 for kw in kws if kw in text)
             for doc_type, kws in _SIGNALS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        if scene.data is not None:
            best = "financial_report"
        else:
            word_count = len((scene.narration or "").split())
            best = "news_clipping" if word_count <= 25 else "modern_newspaper"

    year = _beat_year(scene, graph)
    if year and year < 1970:
        if best == "modern_newspaper":
            best = "vintage_newspaper"
        elif best == "archive_dossier":
            best = "historical_document"
    return best


def _headline_from(narration: str, limit: int = _HEADLINE_CHARS) -> str:
    """A title-frame-safe headline: cut at the last WHOLE word inside `limit`,
    never mid-word. The full narration always survives separately as the body
    paragraph, so this only has to be a short label, not a complete sentence —
    a hard `narration[:80]` slice both read as truncated garbage ("...produced
    tw") AND was too long for every template's title frame to hold without
    Scribus silently dropping the overflow line (see templates.py/animate.py
    fixes from this same review)."""
    text = narration.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(".,;:")
    return cut or text[:limit]


def build_spec(scene: Scene, graph: SceneGraph, document_type: str) -> DocumentSpec:
    source_overlay = next((o for o in scene.overlays if o.type == "source"), None)
    quote_overlay = next((o for o in scene.overlays if o.type == "quote"), None)
    stat_overlay = next((o for o in scene.overlays if o.type == "stat"), None)
    headline = next((o.text for o in scene.overlays if o.type in ("headline", "lower_third")),
                    _headline_from(scene.narration))

    citations = [Citation(label=source_overlay.text)] if source_overlay else []
    facts = [Fact(text=scene.narration,
                  citation=citations[0] if citations else None)]
    statistics = []
    # A director-authored `stat` overlay (e.g. "Z$100,000,000,000,000") is
    # the single most important figure in the beat by construction — it was
    # NOT being read at all, so a beat's headline evidence number could be
    # completely absent from the rendered document. Added first so it leads.
    if stat_overlay:
        statistics.append(Statistic(
            label=stat_overlay.sub or "", value=stat_overlay.text,
            citation=citations[0] if citations else None))
    # Only "counter" DataViz points are a genuine label+value pair worth a
    # document statistic row ("Revenue: $3.8B"). Other kinds (delta,
    # bar_compare, line_trend, ...) use `label` as the human-readable axis
    # tick and `value` as its plotting coordinate — for a "delta" year-gap
    # beat that's the SAME year twice ("1866" next to the formatted "1,866"),
    # which reads as a broken duplicate, not a fact. The narration already
    # states the real takeaway; no stat row is more honest than a wrong one.
    if scene.data is not None and scene.data.kind == "counter":
        for p in getattr(scene.data, "points", [])[:6]:
            label = getattr(p, "label", "")
            value = format_value(p.value, scene.data) if hasattr(p, "value") else ""
            if label:
                statistics.append(Statistic(
                    label=str(label), value=value,
                    citation=citations[0] if citations else None))
    quotes = []
    if quote_overlay:
        quotes.append(Quote(text=quote_overlay.text, attribution=quote_overlay.sub or ""))

    beat = _storyboard_meta(scene, graph)
    year = _beat_year(scene, graph)

    return DocumentSpec(
        document_type=document_type,        # type: ignore[arg-type]
        title=headline,
        subtitle=(beat.location if beat else "") or "",
        body=scene.narration,
        dates=[str(year)] if year else [],
        facts=facts,
        quotes=quotes,
        statistics=statistics,
        citations=citations,
        duration_sec=scene.duration_sec,
        camera_movement="slow_zoom",
        editorial_reconstruction=True,       # a recreated period document by default
    )
