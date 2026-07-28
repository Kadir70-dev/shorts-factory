"""Ranker contract. A ranker turns scored candidates into ranked topics."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..config_types import ChannelBrief
from ..models import CostReport, RankedTopic, TopicCandidate


@runtime_checkable
class Ranker(Protocol):
    name: str

    async def rank(
        self, candidates: list[TopicCandidate], *, brief: ChannelBrief
    ) -> tuple[list[RankedTopic], CostReport, list[str]]:
        """Returns (ranked topics, cost report, warnings).

        MUST NOT raise. A ranker that cannot do its job returns an empty list and a
        warning; the service then falls back.
        """
        ...
