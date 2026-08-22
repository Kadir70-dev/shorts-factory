"""
Paper Craft — the structured input contract.

One `DocumentSpec` describes ONE printed page to be laid out by Scribus,
aged, and animated into a scene. It carries only content and editorial intent
— never layout coordinates; that's the template's job (`templates.py`), so
the same spec renders correctly whether it becomes a newspaper or a memo.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal

DocumentType = Literal[
    "modern_newspaper", "vintage_newspaper", "research_paper", "archive_dossier",
    "financial_report", "magazine_feature", "breaking_news", "evidence_board",
    "company_memo", "historical_document", "news_clipping", "evidence_card",
]

CameraMovement = Literal[
    "slow_zoom", "page_slide", "page_turn", "parallax", "macro_close_up",
    "highlight_reveal", "headline_punch_in", "source_citation_reveal", "none",
]


class Citation(BaseModel):
    """One sourced claim. Required whenever a `Fact` or `Statistic` is presented
    as real rather than editorial recreation — see `provenance.py`."""
    label: str                     # e.g. "U.S. Treasury, Minerals Yearbook 1952"
    url: str = ""
    license: str = ""


class Fact(BaseModel):
    text: str
    citation: Citation | None = None


class Statistic(BaseModel):
    label: str
    value: str                     # pre-formatted ("$3.8B", "61%") — no unit math here
    citation: Citation | None = None


class Quote(BaseModel):
    text: str
    attribution: str = ""
    citation: Citation | None = None


class ImageRef(BaseModel):
    path: str
    caption: str = ""
    credit: str = ""


class DocumentSpec(BaseModel):
    document_type: DocumentType
    title: str
    subtitle: str = ""
    body: str = ""
    dates: list[str] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    quotes: list[Quote] = Field(default_factory=list)
    statistics: list[Statistic] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)   # page-level sources
    images: list[ImageRef] = Field(default_factory=list)
    logo_path: str = ""

    # --- presentation ---------------------------------------------------- #
    visual_theme: str = "k70"          # brand id, resolved via brand.theme_for
    paper_age: Literal["pristine", "aged", "vintage", "ancient"] = "aged"
    language: str = "en"

    # --- how the exported page becomes a scene --------------------------- #
    duration_sec: float = 4.0
    camera_movement: CameraMovement = "slow_zoom"

    # --- safety (see provenance.py) --------------------------------------- #
    # True for any document whose real-world counterpart doesn't exist verbatim
    # (a recreated period newspaper page, a dramatized memo). False only for
    # documents built ENTIRELY from cited, real source text/figures.
    editorial_reconstruction: bool = True
    fictional_signature: bool = False   # a signature/stamp was invented for effect

    def is_fact_heavy(self) -> bool:
        return bool(self.facts or self.statistics or self.citations)
