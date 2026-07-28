"""
Phase 2A — Gemini-powered finance trend intelligence.

An ISOLATED package that answers exactly one question: *what should the next
US-finance YouTube Short be about?* It collects real external signals, normalizes
and clusters them, rejects duplicates and unsafe angles, scores every candidate
deterministically, and uses Gemini purely as a reasoning/ranking layer on top of
data that was actually collected.

It does NOT render, upload or schedule anything. The winning topic is handed to
the existing Director pipeline through `bridge.py` — the frozen render core is
untouched.

Public surface:
    from app.topic_intelligence import TopicIntelligenceService, ti_settings
"""
from __future__ import annotations

from .models import (
    NO_SAFE_TOPIC_AVAILABLE,
    EvidenceItem,
    NormalizedSignal,
    RankedTopic,
    RawTrendSignal,
    SelectionResult,
    TopicCandidate,
    TopicScores,
)
from .settings import ti_settings

__all__ = [
    "NO_SAFE_TOPIC_AVAILABLE",
    "EvidenceItem",
    "NormalizedSignal",
    "RankedTopic",
    "RawTrendSignal",
    "SelectionResult",
    "TopicCandidate",
    "TopicScores",
    "TopicIntelligenceService",
    "ti_settings",
]


def __getattr__(name: str):
    # Lazy so `import app.topic_intelligence` stays cheap and free of DB/engine
    # side effects for callers that only want the models.
    if name == "TopicIntelligenceService":
        from .service import TopicIntelligenceService

        return TopicIntelligenceService
    raise AttributeError(name)
