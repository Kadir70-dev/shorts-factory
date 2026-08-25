"""
Paper Craft — safety and provenance metadata.

Every rendered document ships a provenance record answering, in writing:
what is this, is it a real document or a recreation, what claims in it are
sourced, and where do those sources come from. This is what stands between
"documentary visual aid" and "fabricated evidence" — the distinction the task
explicitly requires never gets blurred.

Rule enforced here, not just documented: a `Fact` or `Statistic` with no
`Citation` cannot be marked as anything other than an editorial recreation.
`build()` raises rather than silently shipping an uncited claim as if it were
sourced.
"""
from __future__ import annotations

from .spec import DocumentSpec


class UnsourcedClaimError(ValueError):
    """A fact/statistic was presented without a citation on a document NOT
    marked as an editorial reconstruction. Never silently downgrade this —
    the caller must either add the citation or set editorial_reconstruction."""


def build(spec: DocumentSpec, cache_key: str, *, cache_hit: bool,
          frames: int = 0) -> dict:
    uncited = [f.text for f in spec.facts if f.citation is None] + \
              [s.label for s in spec.statistics if s.citation is None]

    if uncited and not spec.editorial_reconstruction:
        raise UnsourcedClaimError(
            f"{spec.document_type}: {len(uncited)} fact(s)/statistic(s) have no "
            "citation and editorial_reconstruction is False. Either cite them "
            "or mark the document as a recreation."
        )

    return {
        "engine": "scribus_papercraft",
        "cache_key": cache_key,
        "cache_hit": cache_hit,
        "document_type": spec.document_type,
        "title": spec.title,
        "editorial_reconstruction": spec.editorial_reconstruction,
        "fictional_signature": spec.fictional_signature,
        "label": _label(spec),
        "citations": [c.model_dump() for c in spec.citations],
        "sourced_facts": [f.model_dump() for f in spec.facts if f.citation],
        "sourced_statistics": [s.model_dump() for s in spec.statistics
                                if s.citation],
        "uncited_claims": uncited,
        "frames_rendered": frames,
        "animation": {
            "camera_movement": spec.camera_movement,
            "duration_sec": spec.duration_sec,
        },
    }


def _label(spec: DocumentSpec) -> str:
    """The on-screen/metadata disclosure line — surfaced by the same
    'Before publishing' QA block `qa.py`/`finalize_short.py` already print
    for AI-generated imagery, so Paper Craft recreations get the same
    visibility, not a quieter path."""
    if not spec.editorial_reconstruction:
        return ""
    tag = "Editorial Reconstruction"
    if spec.fictional_signature:
        tag += " — includes a fictionalised signature/stamp for illustrative purposes"
    return tag
